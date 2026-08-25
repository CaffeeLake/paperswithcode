"""Run hostile synthetic qualification through the per-job Sandbox transport.

The command is staging-only and emits no manuscript data, diagnostics, provider
job IDs, URLs, envelopes, or credentials. A successful local run is not a live
qualification: the configured private Sandbox must actually execute it.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid

import httpx

from backend.config import Settings, get_settings
from backend.scripts.qualify_latex_compiler_space import (
    QualificationCase,
    qualification_cases,
    report,
)
from backend.services.latex_compiler_service import (
    LatexCompilerTransport,
    compiler_transport_from_settings,
)
from latex_compiler_contract import CompilerJobState

CONFIRMATION = "QUALIFY_PRIVATE_LATEX_COMPILER_SANDBOX"
POLL_SECONDS = 0.5
_CANCELLATION_BUNDLE = qualification_cases()[0].bundle


def run_case(
    case: QualificationCase, compiler: LatexCompilerTransport
) -> tuple[str, int]:
    """Submit one fixed synthetic case without printing its source or handle."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    try:
        status = compiler.submit(
            job_id=job_id, bundle=case.bundle, entrypoint="main.tex"
        )
    except httpx.HTTPStatusError as error:
        if error.response.status_code == 422:
            return "rejected", int((time.monotonic() - started) * 1000)
        raise
    deadline = time.monotonic() + 135
    while time.monotonic() < deadline:
        if status.state in {
            CompilerJobState.SUCCEEDED,
            CompilerJobState.FAILED,
            CompilerJobState.CANCELED,
        }:
            # Read and validate the terminal response so the disposable VM is
            # released by the transport. Do not expose its content.
            compiler.result(job_id)
            return status.state.value, int((time.monotonic() - started) * 1000)
        time.sleep(POLL_SECONDS)
        status = compiler.status(job_id)
    try:
        compiler.cancel(job_id)
    except (httpx.HTTPError, RuntimeError):
        pass
    return "timeout", int((time.monotonic() - started) * 1000)


def run_cancellation_case(compiler: LatexCompilerTransport) -> tuple[str, int]:
    """Exercise immediate, idempotent disposal using an empty synthetic archive."""
    job_id = str(uuid.uuid4())
    started = time.monotonic()
    compiler.submit(job_id=job_id, bundle=_CANCELLATION_BUNDLE, entrypoint="main.tex")
    status = compiler.cancel(job_id)
    return status.state.value, int((time.monotonic() - started) * 1000)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--case", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION}")
    settings: Settings = get_settings()
    if settings.environment != "staging":
        raise SystemExit("Qualification requires PWC_ENVIRONMENT=staging")
    if not settings.chat_latex_compiler_jobs_enabled:
        raise SystemExit("Compiler kill switch is enabled; refusing qualification")
    selected = [
        case
        for case in qualification_cases()
        if not args.case or case.name in args.case
    ]
    if not selected or (args.case and len(selected) != len(set(args.case))):
        raise SystemExit("Select one or more known qualification cases")
    try:
        compiler = compiler_transport_from_settings(settings)
        results = [(case, *run_case(case, compiler)) for case in selected]
        results.append(
            (
                QualificationCase("cancellation", b"", "canceled"),
                *run_cancellation_case(compiler),
            )
        )
    except RuntimeError as error:
        raise SystemExit(str(error)) from error
    payload = report(results)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
