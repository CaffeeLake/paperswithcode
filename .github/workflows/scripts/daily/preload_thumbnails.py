"""
Daily Thumbnail Preload CRON Job

Generates and uploads paper thumbnails to a Hugging Face Storage Bucket so that
they are warm before browsers request them via /api/thumbnails/{filename}.

Behavior:
- Iterates ArXiv papers ordered newest first.
- Uses the existing ThumbnailService to keep the filename scheme and bucket
  layout identical to the on-demand serving path.
- Skips any paper whose thumbnail already exists in the bucket (cheap exists()
  check via HfFileSystem) or in the active local cache.
- Generates and uploads only the missing ones by default, or regenerates existing
  thumbnails when --refresh-existing is passed.

The backend falls back to on-demand generation if a file is somehow missed by
this job (e.g. for very newly imported papers).

Schedule: Daily.
Dependencies: PostgreSQL, ArXiv access, Hugging Face bucket configured via
PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket plus PWC_THUMBNAIL_HF_BUCKET_ID and
PWC_HF_TOKEN.
"""

import argparse
import asyncio
import gc
import sys
import time
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper as DBPaper
from backend.services.thumbnail_service import ThumbnailService
from backend.utils.exceptions import ThumbnailGenerationError
from scripts.utils.cron_helpers import CronJobBase


DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_FAILURES = 50
DEFAULT_REFRESH_REQUEST_DELAY_SECONDS = 6.0


class ThumbnailPreloadJob(CronJobBase):
    """Daily job that warms the thumbnail bucket for ArXiv papers."""

    def __init__(
        self,
        limit: Optional[int],
        batch_size: int,
        recent_days: Optional[int],
        max_failures: Optional[int],
        dry_run: bool,
        refresh_existing: bool,
        request_delay_seconds: Optional[float],
    ):
        super().__init__(job_name="preload_thumbnails", log_level="INFO")
        self.settings = get_settings()
        self.limit = limit
        self.batch_size = max(1, batch_size)
        self.recent_days = recent_days
        self.max_failures = max_failures
        self.dry_run = dry_run
        self.refresh_existing = refresh_existing
        if request_delay_seconds is not None:
            self.request_delay_seconds = max(0.0, request_delay_seconds)
        elif refresh_existing and not dry_run:
            self.request_delay_seconds = DEFAULT_REFRESH_REQUEST_DELAY_SECONDS
        else:
            self.request_delay_seconds = 0.0

        self.candidates_seen = 0
        self.already_cached = 0
        self.generated = 0
        self.would_generate = 0
        self.failures = 0

    def _validate_settings(self) -> None:
        backend = (self.settings.thumbnail_storage_backend or "").lower()
        if backend != "hf_bucket":
            raise RuntimeError(
                "PWC_THUMBNAIL_STORAGE_BACKEND must be 'hf_bucket' to preload "
                f"thumbnails (current: {backend or 'unset'})"
            )
        if not (self.settings.thumbnail_hf_bucket_id or "").strip():
            raise RuntimeError(
                "PWC_THUMBNAIL_HF_BUCKET_ID is required to preload thumbnails"
            )
        if not (self.settings.hf_token or "").strip():
            raise RuntimeError(
                "PWC_HF_TOKEN is required to authenticate against the Hugging Face bucket"
            )

    def _iter_candidates(self, session) -> Iterable[Tuple[int, str, str]]:
        """Yield (id, arxiv_id, version) for eligible papers, newest first."""
        filters = [
            DBPaper.is_latest_version,
            DBPaper.arxiv_id.isnot(None),
            DBPaper.arxiv_id != "",
        ]
        if self.recent_days is not None and self.recent_days > 0:
            cutoff = datetime.utcnow().date() - timedelta(days=self.recent_days)
            filters.append(
                or_(
                    DBPaper.date_published.is_(None),
                    DBPaper.date_published >= cutoff,
                )
            )

        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(and_(*filters))
            .order_by(
                DBPaper.date_published.desc(),
                DBPaper.id.desc(),
            )
        )
        if self.limit is not None and self.limit > 0:
            query = query.limit(self.limit)

        for row in query.yield_per(self.batch_size):
            yield row.id, row.arxiv_id, row.version or "v1"

    async def _process_paper(
        self,
        thumbnail_service: ThumbnailService,
        arxiv_id: str,
        version: str,
    ) -> str:
        """Process one paper, returning a status: cached | generated | dry_run | failed."""
        filename = thumbnail_service.get_filename(arxiv_id, version)

        if not self.refresh_existing:
            active_cache_path = thumbnail_service._get_active_cache_path(filename)
            if active_cache_path.exists():
                return "cached"

            if thumbnail_service._bucket_thumbnail_exists(filename):
                return "cached"

        if self.dry_run:
            return "dry_run"

        await thumbnail_service.generate_thumbnail(
            arxiv_id, version, force=self.refresh_existing
        )
        return "generated"

    async def _run_async(self) -> None:
        thumbnail_service = ThumbnailService()

        session = db_manager.session_local()
        try:
            candidates: List[Tuple[int, str, str]] = list(
                self._iter_candidates(session)
            )
        finally:
            session.close()

        total = len(candidates)
        self.logger.info(
            "Found %d candidate papers "
            "(limit=%s, recent_days=%s, dry_run=%s, refresh_existing=%s, "
            "request_delay_seconds=%.1f)",
            total,
            self.limit,
            self.recent_days,
            self.dry_run,
            self.refresh_existing,
            self.request_delay_seconds,
        )
        if total == 0:
            return

        start = time.time()
        for paper_id, arxiv_id, version in candidates:
            self.candidates_seen += 1

            try:
                status = await self._process_paper(thumbnail_service, arxiv_id, version)
            except ThumbnailGenerationError as exc:
                self.failures += 1
                self.logger.warning(
                    "Failed to generate thumbnail for paper %s (%s %s): %s",
                    paper_id,
                    arxiv_id,
                    version,
                    exc,
                )
            except Exception as exc:
                self.failures += 1
                self.logger.warning(
                    "Unexpected error for paper %s (%s %s): %s",
                    paper_id,
                    arxiv_id,
                    version,
                    exc,
                )
            else:
                if status == "cached":
                    self.already_cached += 1
                elif status == "generated":
                    self.generated += 1
                    self.logger.info(
                        "Generated thumbnail for %s %s (paper_id=%s)",
                        arxiv_id,
                        version,
                        paper_id,
                    )
                elif status == "dry_run":
                    self.would_generate += 1

            if self.candidates_seen % self.batch_size == 0:
                elapsed = time.time() - start
                self.logger.info(
                    "Progress: %d/%d processed, generated=%d, cached=%d, "
                    "would_generate=%d, failures=%d (%.1fs elapsed)",
                    self.candidates_seen,
                    total,
                    self.generated,
                    self.already_cached,
                    self.would_generate,
                    self.failures,
                    elapsed,
                )
                gc.collect()

            if (
                self.max_failures is not None
                and self.max_failures >= 0
                and self.failures > self.max_failures
            ):
                self.logger.error(
                    "Aborting: failures (%d) exceeded --max-failures=%d",
                    self.failures,
                    self.max_failures,
                )
                break

            if (
                self.request_delay_seconds > 0
                and not self.dry_run
                and self.candidates_seen < total
            ):
                await asyncio.sleep(self.request_delay_seconds)

    def run(self) -> None:
        self._validate_settings()
        self.logger.info(
            "Starting thumbnail preload job "
            "(bucket=%s, prefix=%s, dry_run=%s, refresh_existing=%s, "
            "request_delay_seconds=%.1f)",
            self.settings.thumbnail_hf_bucket_id,
            self.settings.thumbnail_hf_bucket_prefix,
            self.dry_run,
            self.refresh_existing,
            self.request_delay_seconds,
        )

        asyncio.run(self._run_async())

        self.logger.info("Thumbnail preload finished:")
        self.logger.info("  - Candidates seen: %d", self.candidates_seen)
        self.logger.info("  - Already cached:  %d", self.already_cached)
        self.logger.info("  - Generated:       %d", self.generated)
        self.logger.info("  - Would generate:  %d", self.would_generate)
        self.logger.info("  - Failures:        %d", self.failures)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preload paper thumbnails into a Hugging Face bucket so they are "
            "warm before /api/thumbnails/{filename} is requested."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of candidate papers to consider (default: all).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help="Logging / yield_per batch size (default: %(default)s).",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=None,
        help=(
            "Only consider papers published within the last N days. "
            "Papers without a date_published are also included."
        ),
    )
    parser.add_argument(
        "--max-failures",
        type=int,
        default=DEFAULT_MAX_FAILURES,
        help=(
            "Abort after this many failures (default: %(default)s). "
            "Pass a negative value to disable the cap."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be generated without downloading or uploading.",
    )
    parser.add_argument(
        "--refresh-existing",
        action="store_true",
        help=(
            "Regenerate and overwrite thumbnails even when a local or bucket "
            "object already exists."
        ),
    )
    parser.add_argument(
        "--request-delay-seconds",
        type=float,
        default=None,
        help=(
            "Minimum delay between paper downloads. Defaults to "
            f"{DEFAULT_REFRESH_REQUEST_DELAY_SECONDS:g}s for --refresh-existing "
            "and 0 otherwise."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    job = ThumbnailPreloadJob(
        limit=args.limit,
        batch_size=args.batch_size,
        recent_days=args.recent_days,
        max_failures=args.max_failures,
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
        request_delay_seconds=args.request_delay_seconds,
    )
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
