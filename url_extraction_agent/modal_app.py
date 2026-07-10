"""Modal deployment: one isolated URL-research agent per paper."""

import asyncio
import time
from pathlib import Path

import modal

from url_extraction_agent.schema import AgentAttempt, PaperCandidate

APP_NAME = "paperswithcode-url-extraction"
MAX_CONTAINERS = 20
FUNCTION_TIMEOUT_SECONDS = 15 * 60

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "git", "ripgrep")
    .pip_install(
        "claude-agent-sdk==0.2.115",
        "huggingface-hub>=1.13.0",
        "pydantic>=2.0.0",
    )
    .add_local_python_source("url_extraction_agent", copy=True)
    .add_local_dir(
        "url_extraction_agent/prompts",
        remote_path="/root/url_extraction_agent/prompts",
        copy=True,
    )
    .add_local_dir(
        ".agents/skills/hf-cli",
        remote_path="/root/project/.agents/skills/hf-cli",
        copy=True,
    )
)

app = modal.App(APP_NAME)


def _is_transient(attempt: AgentAttempt) -> bool:
    reason = (attempt.failure_reason or "").lower()
    return any(
        marker in reason
        for marker in (
            "429",
            "rate limit",
            "temporarily unavailable",
            "timeout",
            "timed out",
            "502",
            "503",
            "504",
        )
    )


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("anthropic")],
    env={"IS_SANDBOX": "1"},
    cpu=1.0,
    memory=1024,
    max_containers=MAX_CONTAINERS,
    timeout=FUNCTION_TIMEOUT_SECONDS,
    single_use_containers=True,
)
def extract_paper(candidate_data: dict) -> dict:
    from url_extraction_agent.agent import run_agent

    candidate = PaperCandidate.model_validate(candidate_data)
    attempt: AgentAttempt | None = None
    for retry in range(3):
        attempt = asyncio.run(run_agent(candidate, cwd=Path("/root/project")))
        if not _is_transient(attempt) or retry == 2:
            break
        time.sleep(2**retry * 5)

    assert attempt is not None
    return attempt.model_dump(mode="json")
