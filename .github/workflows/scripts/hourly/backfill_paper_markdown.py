"""Copy available HF paper Markdown and dispatch Chandra for remaining gaps."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from huggingface_hub import HfApi, HfFileSystem, Volume
from huggingface_hub.errors import HfHubHTTPError
from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper
from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_snapshot,
)
from scripts.utils.cron_helpers import CronJobBase

ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")
ACTIVE_STAGES = {"PENDING", "RUNNING", "STARTING", "QUEUED", "SCHEDULING"}
SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "backend"
    / "scripts"
    / "generate_missing_paper_markdown.py"
)
COVERAGE_HISTORY_NAME = "paper_markdown_coverage.jsonl"


def normalize_arxiv_id(value: str | None) -> str | None:
    match = ARXIV_ID.fullmatch((value or "").strip())
    return match.group("base") if match else None


def markdown_key(arxiv_id: str) -> str:
    return f"{arxiv_id[:4]}/{arxiv_id}.md"


def chunks[T](values: list[T], size: int) -> list[list[T]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def job_stage(job: object) -> str:
    status = getattr(job, "status", None)
    stage = getattr(job, "stage", None) or getattr(status, "stage", status)
    return str(getattr(stage, "value", stage) or "").upper()


def status_disposition(
    status: dict[str, object], *, now: datetime | None = None, max_attempts: int = 3
) -> str:
    """Return a persisted retry disposition without parsing free-form errors."""
    state = str(status.get("status") or "").lower()
    try:
        attempts = max(0, int(status.get("attempt_count") or 0))
    except (TypeError, ValueError):
        return "permanent_failure"
    if state in {"succeeded", "already_exists"}:
        return "completed"
    # Legacy failed records predate structured retry metadata. Admit each once
    # so the worker can persist a classified v2 record without error-string
    # inference in the scheduler.
    if state == "failed" and not status.get("schema_version"):
        return "retryable_due"
    if attempts >= max_attempts:
        return "attempts_exhausted"
    # Worker releases before the bounded arXiv-version fallback could classify a
    # stale requested version as a permanent 404. Re-admit those records once;
    # the corrected worker records that it tried the fallback chain.
    if (
        state == "failed"
        and status.get("error_class") == "arxiv_http_404"
        and status.get("version_fallback_attempted") is not True
    ):
        return "retryable_due"
    if status.get("retryable") is not True:
        return "permanent_failure"
    retry_at = status.get("next_retry_at")
    if not retry_at:
        return "retryable_due"
    try:
        due_at = datetime.fromisoformat(str(retry_at).replace("Z", "+00:00"))
        if due_at.tzinfo is None:
            due_at = due_at.replace(tzinfo=UTC)
    except ValueError:
        return "retryable_deferred"
    return (
        "retryable_due"
        if due_at <= (now or datetime.now(UTC))
        else "retryable_deferred"
    )


def append_coverage_history(payload: dict[str, object]) -> None:
    """Keep append-only local evidence for seven-day coverage deltas."""
    log_dir = Path(
        os.environ.get("PWC_CRON_LOG_DIR", Path(__file__).resolve().parents[1] / "logs")
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / COVERAGE_HISTORY_NAME).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


class PaperMarkdownBackfillJob(CronJobBase):
    def __init__(
        self,
        *,
        full: bool,
        execute: bool,
        confirm: bool,
        max_jobs: int | None,
        batch_size: int | None,
    ):
        super().__init__("paper_markdown_backfill")
        self.settings = get_settings()
        self.full = full
        self.should_execute = execute
        self.confirm = confirm
        self.max_jobs = max_jobs
        self.batch_size = batch_size
        self.budget_projected_usd: float | None = None
        self.budget_ceiling_usd: float | None = None
        self.budget_desired_jobs = 0
        self.budget_affordable_jobs = 0
        self.api = HfApi(token=self.settings.hf_token or None)
        self.filesystem = HfFileSystem(token=self.settings.hf_token or None)

    def _papers(self) -> list[dict[str, object]]:
        with db_manager.session_local() as db:
            query = select(Paper).where(
                Paper.is_latest_version,
                Paper.source == "arxiv",
                Paper.arxiv_id.is_not(None),
            )
            if not self.full:
                query = query.where(
                    Paper.created_at >= datetime.now(UTC) - timedelta(days=14)
                )
                query = query.order_by(Paper.created_at.desc(), Paper.id.desc())
            else:
                query = query.order_by(Paper.id)
            rows = db.execute(query).scalars()
            papers: dict[str, dict[str, object]] = {}
            for paper in rows:
                arxiv_id = normalize_arxiv_id(paper.arxiv_id)
                if arxiv_id is None:
                    continue
                version = str(paper.version or "v1")
                if not version.startswith("v"):
                    version = f"v{version}"
                papers[arxiv_id] = {
                    "arxiv_id": arxiv_id,
                    "version": version,
                    "title": paper.title,
                    "output_key": markdown_key(arxiv_id),
                }
            return list(papers.values())

    def _existing_paths(self, bucket: str, paths: list[str]) -> dict[str, object]:
        found: dict[str, object] = {}
        for batch in chunks(paths, 1000):
            for entry in self.api.get_bucket_paths_info(
                bucket, batch, token=self.settings.hf_token or None
            ):
                found[entry.path] = entry
        return found

    def _status_records(self, paths: list[str]) -> dict[str, dict[str, object]]:
        existing = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id, paths
        )

        def read(path: str) -> tuple[str, dict[str, object]]:
            bucket_path = (
                f"hf://buckets/{self.settings.paper_markdown_hf_bucket_id}/{path}"
            )
            try:
                with self.filesystem.open(bucket_path, "rb", block_size=0) as handle:
                    raw = handle.read(64 * 1024 + 1)
                if len(raw) > 64 * 1024:
                    return path, {"status": "oversized", "retryable": False}
                payload = json.loads(raw)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, HfHubHTTPError):
                return path, {"status": "unreadable", "retryable": False}
            if isinstance(payload, dict):
                return path, payload
            return path, {"status": "invalid", "retryable": False}

        with ThreadPoolExecutor(max_workers=8) as executor:
            return dict(executor.map(read, existing))

    def _copy_upstream(
        self, missing: list[dict[str, object]]
    ) -> tuple[list[dict[str, object]], int]:
        paths = [str(item["output_key"]) for item in missing]
        upstream = self._existing_paths(
            self.settings.paper_markdown_upstream_bucket_id, paths
        )
        copy_items: list[tuple[str, str, str, str]] = []
        copied_paths: set[str] = set()
        for path, entry in upstream.items():
            xet_hash = getattr(entry, "xet_hash", None)
            if not xet_hash:
                continue
            copy_items.append(
                (
                    "bucket",
                    self.settings.paper_markdown_upstream_bucket_id,
                    xet_hash,
                    path,
                )
            )
            copied_paths.add(path)
        if self.should_execute:
            for batch in chunks(copy_items, 100):
                self.api.batch_bucket_files(
                    self.settings.paper_markdown_hf_bucket_id,
                    copy=batch,
                    token=self.settings.hf_token or None,
                )
        remaining = [
            item for item in missing if str(item["output_key"]) not in copied_paths
        ]
        return remaining, len(copied_paths)

    def _remote_jobs(self) -> list[object]:
        return list(
            self.api.list_jobs(
                labels={"app": "pwc-paper-markdown"},
                namespace=self.settings.paper_markdown_hf_namespace,
                token=self.settings.hf_token or None,
            )
        )

    def _active_jobs(self, jobs: list[object]) -> list[object]:
        mode = "backfill" if self.full else "live"
        return [
            job
            for job in jobs
            if job_stage(job) in ACTIVE_STAGES
            and (getattr(job, "labels", None) or {}).get("mode") == mode
        ]

    def _budget_decision(
        self, desired_jobs: int, jobs: list[object]
    ) -> dict[str, object]:
        ceiling = (
            self.settings.paper_markdown_backfill_budget_usd
            if self.full
            else self.settings.paper_markdown_incremental_monthly_budget_usd
        )
        budget = paper_markdown_budget_snapshot(
            jobs,
            mode="backfill" if self.full else "live",
            ceiling_usd=ceiling,
            planned_jobs=desired_jobs,
        )
        self.budget_desired_jobs = int(budget["desired_jobs"])
        self.budget_affordable_jobs = int(budget["affordable_jobs"])
        self.budget_projected_usd = float(budget["projected_usd"])
        self.budget_ceiling_usd = ceiling
        if desired_jobs and not self.budget_affordable_jobs:
            self.logger.warning(
                "paper Markdown GPU budget exhausted: %s",
                budget["reason"],
            )
        return budget

    def _launch(self, candidates: list[dict[str, object]]) -> list[dict[str, str]]:
        remote_jobs = self._remote_jobs()
        active = self._active_jobs(remote_jobs)
        concurrency = (
            self.settings.paper_markdown_backfill_concurrency if self.full else 1
        )
        if self.max_jobs is not None:
            concurrency = min(concurrency, self.max_jobs)
        available_slots = max(0, concurrency - len(active))
        batch_size = (
            self.settings.paper_markdown_backfill_batch_size
            if self.full
            else self.settings.paper_markdown_incremental_batch_size
        )
        if self.batch_size is not None:
            maximum = 500 if self.full else 100
            if self.batch_size < 1 or self.batch_size > maximum:
                raise ValueError(f"batch size must be between 1 and {maximum}")
            batch_size = self.batch_size
        plans = chunks(candidates, batch_size)[:available_slots]
        budget = self._budget_decision(len(plans), remote_jobs)
        affordable = int(budget["affordable_jobs"])
        plans = plans[:affordable]
        self.logger.info(
            "paper Markdown admission: desired=%s affordable=%s launched=%s",
            self.budget_desired_jobs,
            self.budget_affordable_jobs,
            len(plans) if self.should_execute else 0,
        )
        if self.should_execute and plans and not self.confirm:
            raise ValueError("paid GPU dispatch requires --confirm")

        launched: list[dict[str, str]] = []
        run_id = f"{'backfill' if self.full else 'live'}-{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}"
        for shard_number, entries in enumerate(plans):
            shard_id = f"{shard_number:05d}"
            manifest_key = f"_jobs/manifests/{run_id}/{shard_id}.jsonl"
            manifest = (
                "\n".join(json.dumps(item, sort_keys=True) for item in entries) + "\n"
            ).encode()
            if not self.should_execute:
                launched.append(
                    {
                        "run_id": run_id,
                        "shard_id": shard_id,
                        "papers": str(len(entries)),
                        "mode": "dry_run",
                        "retried": str(
                            sum(bool(item.get("retry")) for item in entries)
                        ),
                    }
                )
                continue
            self.api.batch_bucket_files(
                self.settings.paper_markdown_hf_bucket_id,
                add=[(manifest, manifest_key)],
                token=self.settings.hf_token or None,
            )
            info = self.api.run_uv_job(
                str(SCRIPT),
                script_args=[
                    "--manifest",
                    f"/content/{manifest_key}",
                    "--content-root",
                    "/content",
                    "--soft-deadline-seconds",
                    str(self.settings.paper_markdown_soft_deadline_seconds),
                ],
                image=self.settings.paper_markdown_runtime_image,
                flavor=self.settings.paper_markdown_hardware,
                timeout=self.settings.paper_markdown_job_timeout,
                labels={
                    "app": "pwc-paper-markdown",
                    "mode": "backfill" if self.full else "live",
                    "run_id": run_id,
                    "shard_id": shard_id,
                },
                env={
                    "PWC_MARKDOWN_MODEL_ID": self.settings.paper_markdown_model_id,
                    "PWC_MARKDOWN_MODEL_REVISION": self.settings.paper_markdown_model_revision,
                    "PWC_MARKDOWN_MAX_PAGES": str(
                        self.settings.paper_markdown_max_pages
                    ),
                    "PWC_SCRIPT_VERSION": os.environ.get(
                        "PWC_RELEASE_ID", "development"
                    ),
                },
                secrets={"HF_TOKEN": self.settings.hf_token},
                volumes=[
                    Volume(
                        type="bucket",
                        source=self.settings.paper_markdown_hf_bucket_id,
                        mount_path="/content",
                        read_only=False,
                    )
                ],
                namespace=self.settings.paper_markdown_hf_namespace,
                token=self.settings.hf_token or None,
            )
            job_id = str(getattr(info, "id", None) or getattr(info, "job_id", ""))
            launched.append(
                {
                    "run_id": run_id,
                    "shard_id": shard_id,
                    "papers": str(len(entries)),
                    "hf_job_id": job_id,
                    "retried": str(sum(bool(item.get("retry")) for item in entries)),
                }
            )
        return launched

    def run(self) -> None:
        if self.should_execute and not self.settings.hf_token:
            raise ValueError("PWC_HF_TOKEN is required")
        papers = self._papers()
        paths = [str(item["output_key"]) for item in papers]
        canonical = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id, paths
        )
        missing = [item for item in papers if str(item["output_key"]) not in canonical]
        remaining, upstream_available = self._copy_upstream(missing)
        status_paths = [f"_jobs/status/{item['arxiv_id']}.json" for item in remaining]
        status_records = self._status_records(status_paths)
        dispositions = {
            path: status_disposition(payload)
            for path, payload in status_records.items()
        }
        candidates = []
        for item in remaining:
            status_path = f"_jobs/status/{item['arxiv_id']}.json"
            disposition = dispositions.get(status_path)
            if disposition is None or disposition == "retryable_due":
                candidates.append({**item, "retry": disposition == "retryable_due"})
        failed_or_completed = len(remaining) - len(candidates)
        canonical_after_upstream = len(canonical) + upstream_available
        coverage = {
            "observed_at": datetime.now(UTC).isoformat(),
            "scope": "full" if self.full else "recent_14_days",
            "eligible_papers": len(papers),
            "canonical_markdown_count": canonical_after_upstream,
            "copied_from_upstream_count": upstream_available,
            "missing_count": len(remaining),
            "coverage_percentage": round(
                canonical_after_upstream / len(papers) * 100, 2
            )
            if papers
            else 100.0,
        }
        append_coverage_history(coverage)
        launched = self._launch(candidates)
        metrics = {
            "mode": "backfill" if self.full else "live",
            "execute": self.should_execute,
            "eligible_papers": len(papers),
            "canonical_markdown": len(canonical),
            "canonical_markdown_after_upstream": canonical_after_upstream,
            "coverage_scope": coverage["scope"],
            "coverage_percentage": coverage["coverage_percentage"],
            "missing_before": len(missing),
            "upstream_available": upstream_available,
            "missing_after_upstream": len(remaining),
            "previously_attempted": failed_or_completed,
            "retryable_due": sum(
                disposition == "retryable_due" for disposition in dispositions.values()
            ),
            "retryable_deferred": sum(
                disposition == "retryable_deferred"
                for disposition in dispositions.values()
            ),
            "permanent_failures": sum(
                disposition == "permanent_failure"
                for disposition in dispositions.values()
            ),
            "attempts_exhausted": sum(
                disposition == "attempts_exhausted"
                for disposition in dispositions.values()
            ),
            "retried_papers": sum(int(item.get("retried") or 0) for item in launched),
            "ocr_candidates": len(candidates),
            "jobs_planned_or_launched": len(launched),
            "desired_jobs": self.budget_desired_jobs,
            "affordable_jobs": self.budget_affordable_jobs,
            "papers_planned_or_launched": sum(int(item["papers"]) for item in launched),
            "budget_exhausted": (
                self.budget_desired_jobs > 0 and self.budget_affordable_jobs == 0
            ),
            "budget_projected_usd": self.budget_projected_usd,
            "budget_ceiling_usd": self.budget_ceiling_usd,
            "hf_job_ids": ",".join(
                item["hf_job_id"] for item in launched if item.get("hf_job_id")
            )
            or "none",
        }
        self.logger.info("PAPER_MARKDOWN_SUMMARY %s", json.dumps(metrics))
        self.logger.info("Papers processed: %s", upstream_available)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--max-jobs", type=int)
    parser.add_argument("--batch-size", type=int)
    args = parser.parse_args()
    job = PaperMarkdownBackfillJob(
        full=args.full,
        execute=args.execute,
        confirm=args.confirm,
        max_jobs=args.max_jobs,
        batch_size=args.batch_size,
    )
    raise SystemExit(0 if job.execute() else 1)


if __name__ == "__main__":
    main()
