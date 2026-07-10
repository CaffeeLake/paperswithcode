"""Minimal Claude Agent SDK researcher for official paper URLs."""

import argparse
import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from claude_agent_sdk import (
    ClaudeAgentOptions,
    HookMatcher,
    ResultMessage,
    query,
)

from url_extraction_agent.schema import (
    AgentAttempt,
    PaperCandidate,
    ToolEvent,
    URLFindings,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SYSTEM_PROMPT = (Path(__file__).parent / "prompts" / "system_prompt.txt").read_text()
ALLOWED_TOOLS = ["Skill", "Bash", "Read", "Grep", "Glob", "WebFetch"]
DEFAULT_MAX_TURNS = 20
MAX_BUDGET_USD = 3.0


def _log(arxiv_id: str, message: str) -> None:
    print(f"[{arxiv_id}] {message}", flush=True)


def _short_tool_input(tool_input: dict[str, Any]) -> str:
    return json.dumps(tool_input, default=str, ensure_ascii=True)[:800]


def _user_prompt(candidate: PaperCandidate) -> str:
    requested = []
    if candidate.missing_github:
        requested.append("GitHub repository")
    if candidate.missing_project_page:
        requested.append("project page")
    return "\n".join(
        [
            f"Paper ID: {candidate.arxiv_id}",
            f"Title: {candidate.title}",
            f"Abstract: {candidate.abstract}",
            f"Find only: {', '.join(requested)}",
            f"Known GitHub URL: {candidate.known_github_url or 'none'}",
            f"Known project page URL: {candidate.known_project_page_url or 'none'}",
        ]
    )


def _successful_bash(events: list[ToolEvent], fragment: str) -> bool:
    fragment = fragment.lower()
    return any(
        event.success
        and event.tool_name == "Bash"
        and fragment in str(event.tool_input.get("command", "")).lower()
        for event in events
    )


def _successful_arxiv_fetch(
    events: list[ToolEvent], arxiv_id: str, paths: tuple[str, ...]
) -> bool:
    return any(
        event.success
        and event.tool_name == "WebFetch"
        and "arxiv.org" in str(event.tool_input.get("url", "")).lower()
        and arxiv_id.lower() in str(event.tool_input.get("url", "")).lower()
        and any(path in str(event.tool_input.get("url", "")).lower() for path in paths)
        for event in events
    )


def _successful_page_fetch(events: list[ToolEvent], url: str) -> bool:
    url = url.rstrip("/").lower()
    for event in events:
        if not event.success:
            continue
        if event.tool_name == "WebFetch":
            fetched_url = str(event.tool_input.get("url", "")).rstrip("/").lower()
            if fetched_url == url:
                return True
        if event.tool_name == "Bash":
            command = str(event.tool_input.get("command", "")).lower()
            if "curl" in command and url in command:
                return True
    return False


def _tool_response_succeeded(response: Any) -> bool:
    """Interpret common Claude Code tool response failure fields."""
    if not isinstance(response, dict):
        return True
    if response.get("is_error") is True or response.get("success") is False:
        return False
    exit_code = response.get("exit_code", response.get("exitCode"))
    if exit_code is not None and exit_code != 0:
        return False
    status = str(response.get("status", "")).lower()
    return status not in {"error", "failed", "failure"}


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    try:
        return json.dumps(response, default=str)
    except TypeError:
        return str(response)


def _bash_response_succeeded(command: str, response: str) -> bool:
    if not command.strip().lower().startswith("hf papers"):
        return True
    lowered = response.lower()
    return not any(
        marker in lowered
        for marker in (
            "paper not found",
            "not found on the hub",
            "error:",
            "traceback (most recent call last)",
            "command not found",
        )
    )


def _is_project_page_access(tool_name: str, tool_input: dict[str, Any]) -> bool:
    if tool_name == "WebFetch":
        url = str(tool_input.get("url", ""))
    elif tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if "curl" not in command.lower():
            return False
        match = re.search(r"https?://[^\s\"']+", command)
        url = match.group(0) if match else ""
    else:
        return False
    host = urlparse(url).netloc.lower().removeprefix("www.")
    allowed_research_hosts = {
        "api.github.com",
        "github.com",
        "huggingface.co",
        "arxiv.org",
        "google.com",
        "paperswithcode.com",
    }
    return bool(host) and host not in allowed_research_hosts


def _masks_hf_exit_status(tool_name: str, tool_input: dict[str, Any]) -> bool:
    if tool_name != "Bash":
        return False
    command = str(tool_input.get("command", "")).strip().lower()
    if not command.startswith(("hf papers info ", "hf papers read ")):
        return False
    return any(operator in command for operator in ("|", ";", "&&"))


def derive_attempt_complete(
    candidate: PaperCandidate,
    findings: URLFindings,
    events: list[ToolEvent],
) -> tuple[bool, str | None]:
    """Classify research health from observed tool execution, not model claims."""
    metadata_checked = _successful_bash(
        events, f"hf papers info {candidate.arxiv_id}"
    ) or _successful_arxiv_fetch(events, candidate.arxiv_id, ("/abs/",))
    if not metadata_checked:
        return False, "paper metadata was not successfully inspected"

    unresolved = (candidate.missing_github and findings.github_url is None) or (
        candidate.missing_project_page and findings.project_page_url is None
    )
    paper_checked = _successful_bash(
        events, f"hf papers read {candidate.arxiv_id}"
    ) or _successful_arxiv_fetch(events, candidate.arxiv_id, ("/html/", "/pdf/"))
    if unresolved and not paper_checked:
        return False, "paper content was not successfully inspected"

    if candidate.missing_github and findings.github_url is None:
        project_url = findings.project_page_url or candidate.known_project_page_url
        if project_url and not _successful_page_fetch(events, str(project_url)):
            return False, "project page was not inspected for a GitHub link"

    return True, None


async def run_agent(
    candidate: PaperCandidate,
    *,
    max_turns: int = DEFAULT_MAX_TURNS,
    cwd: Path = REPO_ROOT,
) -> AgentAttempt:
    events: list[ToolEvent] = []
    state = {"github_discovered": False}

    async def guard_project_fetch(
        hook_input: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        _log(
            candidate.arxiv_id,
            f"Tool call: {hook_input['tool_name']} "
            f"{_short_tool_input(hook_input['tool_input'])}",
        )
        if _masks_hf_exit_status(hook_input["tool_name"], hook_input["tool_input"]):
            _log(
                candidate.arxiv_id,
                "Tool denied: hf papers command masks or truncates its exit status",
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "Run hf papers info/read directly without pipes, command "
                        "chaining, or truncation so the orchestrator can verify it"
                    ),
                }
            }
        if state["github_discovered"] and _is_project_page_access(
            hook_input["tool_name"], hook_input["tool_input"]
        ):
            _log(
                candidate.arxiv_id,
                "Tool denied: project-page fetch after GitHub discovery",
            )
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": (
                        "GitHub is already known; project-page content must not be fetched"
                    ),
                }
            }
        return {}

    async def record_success(
        hook_input: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        response = hook_input.get("tool_response")
        response_text = _response_text(response)
        succeeded = _tool_response_succeeded(response)
        if hook_input["tool_name"] == "Bash":
            succeeded = succeeded and _bash_response_succeeded(
                str(hook_input["tool_input"].get("command", "")),
                response_text,
            )
        if succeeded and re.search(
            r"https://github\.com/[\w.-]+/[\w.-]+",
            response_text,
            re.IGNORECASE,
        ):
            state["github_discovered"] = True
        _log(
            candidate.arxiv_id,
            f"Tool {'succeeded' if succeeded else 'failed'}: {hook_input['tool_name']}",
        )
        events.append(
            ToolEvent(
                tool_name=hook_input["tool_name"],
                tool_input=hook_input["tool_input"],
                success=succeeded,
                error=None if succeeded else str(response)[:1000],
                response=response_text[:2000] or None,
            )
        )
        return {}

    async def record_failure(
        hook_input: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        _log(
            candidate.arxiv_id,
            f"Tool failed: {hook_input['tool_name']} - "
            f"{str(hook_input.get('error', 'unknown error'))[:500]}",
        )
        events.append(
            ToolEvent(
                tool_name=hook_input["tool_name"],
                tool_input=hook_input["tool_input"],
                success=False,
                error=hook_input.get("error"),
            )
        )
        return {}

    options = ClaudeAgentOptions(
        system_prompt=SYSTEM_PROMPT,
        max_turns=max_turns,
        max_budget_usd=MAX_BUDGET_USD,
        allowed_tools=ALLOWED_TOOLS,
        permission_mode="bypassPermissions",
        cwd=cwd,
        setting_sources=["project", "user"],
        skills=["hf-cli"],
        output_format={
            "type": "json_schema",
            "schema": URLFindings.model_json_schema(),
        },
        hooks={
            "PreToolUse": [HookMatcher(hooks=[guard_project_fetch])],
            "PostToolUse": [HookMatcher(hooks=[record_success])],
            "PostToolUseFailure": [HookMatcher(hooks=[record_failure])],
        },
    )

    result: ResultMessage | None = None
    _log(candidate.arxiv_id, f"Starting URL research for {candidate.title[:120]}")
    try:
        async for message in query(prompt=_user_prompt(candidate), options=options):
            if isinstance(message, ResultMessage):
                result = message
    except Exception as exc:
        return AgentAttempt(
            paper_id=candidate.paper_id,
            arxiv_id=candidate.arxiv_id,
            failure_reason=f"{type(exc).__name__}: {exc}",
            tool_events=events,
        )

    if result is None:
        return AgentAttempt(
            paper_id=candidate.paper_id,
            arxiv_id=candidate.arxiv_id,
            failure_reason="Agent SDK returned no ResultMessage",
            tool_events=events,
        )

    if result.subtype != "success" or result.structured_output is None:
        errors = "; ".join(result.errors or [])
        return AgentAttempt(
            paper_id=candidate.paper_id,
            arxiv_id=candidate.arxiv_id,
            result_subtype=result.subtype,
            cost_usd=result.total_cost_usd or 0.0,
            failure_reason=errors or f"Agent result subtype: {result.subtype}",
            tool_events=events,
        )

    try:
        findings = URLFindings.model_validate(result.structured_output)
    except Exception as exc:
        return AgentAttempt(
            paper_id=candidate.paper_id,
            arxiv_id=candidate.arxiv_id,
            result_subtype=result.subtype,
            cost_usd=result.total_cost_usd or 0.0,
            failure_reason=f"Invalid structured output: {exc}",
            tool_events=events,
        )

    complete, failure_reason = derive_attempt_complete(candidate, findings, events)
    _log(
        candidate.arxiv_id,
        f"Finished: complete={complete}, github={bool(findings.github_url)}, "
        f"project_page={bool(findings.project_page_url)}, "
        f"cost_usd={result.total_cost_usd or 0.0:.4f}",
    )
    return AgentAttempt(
        paper_id=candidate.paper_id,
        arxiv_id=candidate.arxiv_id,
        findings=findings,
        attempt_complete=complete,
        failure_reason=failure_reason,
        result_subtype=result.subtype,
        cost_usd=result.total_cost_usd or 0.0,
        tool_events=events,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Discover official paper URLs")
    parser.add_argument("--candidate-json", required=True)
    parser.add_argument("--max-turns", type=int, default=DEFAULT_MAX_TURNS)
    args = parser.parse_args()

    candidate = PaperCandidate.model_validate_json(args.candidate_json)
    result = await run_agent(candidate, max_turns=args.max_turns)
    print(json.dumps(result.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    os.environ.setdefault("IS_SANDBOX", "1")
    asyncio.run(main())
