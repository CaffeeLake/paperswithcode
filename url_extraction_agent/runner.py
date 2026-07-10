"""Dispatch a bounded candidate batch of papers to the deployed Modal agent.

Based on Modal's batch processing feature: https://modal.com/docs/guide/batch-processing.
"""

import argparse
import json
from pathlib import Path

import modal

from url_extraction_agent.modal_app import APP_NAME
from url_extraction_agent.schema import AgentAttempt, PaperCandidate

MAX_PAPERS = 100


def load_candidates(path: Path) -> list[PaperCandidate]:
    payload = json.loads(path.read_text())
    if not isinstance(payload, list):
        raise ValueError("candidate artifact must contain a JSON list")
    if len(payload) > MAX_PAPERS:
        raise ValueError(f"candidate artifact exceeds {MAX_PAPERS} papers")
    return [PaperCandidate.model_validate(item) for item in payload]


def run_batch(candidates: list[PaperCandidate]) -> list[AgentAttempt]:
    if not candidates:
        return []

    function = modal.Function.from_name(APP_NAME, "extract_paper")
    inputs = [candidate.model_dump(mode="json") for candidate in candidates]
    attempts: dict[int, AgentAttempt] = {}

    for result in function.map(
        inputs,
        order_outputs=False,
        return_exceptions=True,
    ):
        if isinstance(result, BaseException):
            continue
        attempt = AgentAttempt.model_validate(result)
        attempts[attempt.paper_id] = attempt

    for candidate in candidates:
        if candidate.paper_id not in attempts:
            attempts[candidate.paper_id] = AgentAttempt(
                paper_id=candidate.paper_id,
                arxiv_id=candidate.arxiv_id,
                failure_reason="Modal container failed without a structured result",
            )

    return [attempts[candidate.paper_id] for candidate in candidates]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run URL extraction on Modal")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    candidates = load_candidates(args.input)
    attempts = run_batch(candidates)
    args.output.write_text(
        json.dumps(
            [attempt.model_dump(mode="json") for attempt in attempts],
            indent=2,
        )
        + "\n"
    )
    complete = sum(attempt.attempt_complete for attempt in attempts)
    print(f"Modal URL extraction completed: {complete}/{len(attempts)} conclusive")


if __name__ == "__main__":
    main()
