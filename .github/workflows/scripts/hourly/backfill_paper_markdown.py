"""Copy available HF paper Markdown and dispatch Chandra for remaining gaps."""

from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from huggingface_hub import HfApi, Volume
from sqlalchemy import select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper
from backend.services.paper_markdown_budget_service import (
    paper_markdown_budget_snapshot,
)
from scripts.utils.cron_helpers import CronJobBase

ARXIV_ID = re.compile(r"^(?P<base>\d{4}\.\d{4,5})(?:v\d+)?$")
ACTIVE_STAGES = {"PENDING", "RUNNING", "STARTING", "QUEUED"}
SCRIPT = (
    Path(__file__).resolve().parents[4]
    / "backend"
    / "scripts"
    / "generate_missing_paper_markdown.py"
)


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
        self.api = HfApi(token=self.settings.hf_token or None)

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

    def _active_jobs(self) -> list[object]:
        jobs = list(
            self.api.list_jobs(
                labels={"app": "pwc-paper-markdown"},
                namespace=self.settings.paper_markdown_hf_namespace,
                token=self.settings.hf_token or None,
            )
        )
        return [job for job in jobs if job_stage(job) in ACTIVE_STAGES]

    def _budget_available(self, planned_jobs: int) -> bool:
        if not planned_jobs:
            return True
        all_jobs = list(
            self.api.list_jobs(
                labels={"app": "pwc-paper-markdown"},
                namespace=self.settings.paper_markdown_hf_namespace,
                token=self.settings.hf_token or None,
            )
        )
        ceiling = (
            self.settings.paper_markdown_backfill_budget_usd
            if self.full
            else self.settings.paper_markdown_incremental_monthly_budget_usd
        )
        budget = paper_markdown_budget_snapshot(
            all_jobs,
            mode="backfill" if self.full else "live",
            ceiling_usd=ceiling,
            planned_jobs=planned_jobs,
        )
        projected = budget["projected_usd"]
        self.budget_projected_usd = projected
        self.budget_ceiling_usd = ceiling
        if projected > ceiling:
            self.logger.warning(
                f"paper Markdown GPU budget exhausted: projected ${projected:.2f} "
                f"exceeds ${ceiling:.2f}"
            )
            return False
        return True

    def _launch(self, candidates: list[dict[str, object]]) -> list[dict[str, str]]:
        active = self._active_jobs() if self.should_execute else []
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
        if self.should_execute and plans and not self.confirm:
            raise ValueError("paid GPU dispatch requires --confirm")
        if self.should_execute and not self._budget_available(len(plans)):
            return []

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
        attempted = self._existing_paths(
            self.settings.paper_markdown_hf_bucket_id, status_paths
        )
        candidates = [
            item
            for item in remaining
            if f"_jobs/status/{item['arxiv_id']}.json" not in attempted
        ]
        failed_or_completed = len(remaining) - len(candidates)
        launched = self._launch(candidates)
        metrics = {
            "mode": "backfill" if self.full else "live",
            "execute": self.should_execute,
            "eligible_papers": len(papers),
            "canonical_markdown": len(canonical),
            "missing_before": len(missing),
            "upstream_available": upstream_available,
            "missing_after_upstream": len(remaining),
            "previously_attempted": failed_or_completed,
            "ocr_candidates": len(candidates),
            "jobs_planned_or_launched": len(launched),
            "papers_planned_or_launched": sum(int(item["papers"]) for item in launched),
            "budget_exhausted": (
                self.budget_projected_usd is not None
                and self.budget_ceiling_usd is not None
                and self.budget_projected_usd > self.budget_ceiling_usd
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
