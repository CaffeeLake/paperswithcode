"""
Thumbnail Preload CRON Job

Generates and uploads paper thumbnails to a Hugging Face Storage Bucket so that
they are warm before browsers request them via /api/thumbnails/{filename}.

Priority modes (selected via --priority):
- `trending`: candidates ranked by the EMA-smoothed `trending_papers_24h` view.
  Used by the hourly homepage preload cron.
- `task-top`: top --per-task papers per task tag (matches the default task page
  ranking: trending score, then stars, then date). Used by the daily task-page
  preload cron.
- `recent`: existing newest-first preload, optionally constrained to
  --recent-days. Used by the daily broad preload cron.
- `missing-all`: oldest-first sweep over every latest-version arXiv paper whose
  thumbnail is missing locally. Supports `--shard i/n` and `--after-id` /
  `--before-id` for chunked manual backfills.

The local cache is the source of truth for "do we have this thumbnail" during
backfills: candidates whose .jpg already exists on disk are skipped without any
HF bucket round-trip. By default the bucket is also probed once per missing
candidate; pass `--trust-local-cache` to skip that probe (cheap, safe when the
mirror cron is healthy) so a large backfill can process candidates as fast as
ArXiv allows.

Schedule: see `.github/workflows/cron-preload-thumbnails.yml` for the different
schedules feeding each priority mode.

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
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from sqlalchemy import and_, or_, text

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Paper as DBPaper
from backend.services.thumbnail_service import (
    ThumbnailService,
    build_thumbnail_filename,
)
from backend.utils.exceptions import ThumbnailGenerationError
from scripts.utils.cron_helpers import CronJobBase


DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_FAILURES = 50
DEFAULT_REFRESH_REQUEST_DELAY_SECONDS = 6.0
DEFAULT_TRENDING_MAX_AGE_DAYS = 180
DEFAULT_PER_TASK = 50

VALID_PRIORITIES = ("trending", "task-top", "recent", "missing-all")


Candidate = Tuple[int, str, str]


class ThumbnailPreloadJob(CronJobBase):
    """Generate thumbnails for prioritised subsets of ArXiv papers."""

    def __init__(
        self,
        priority: str,
        limit: Optional[int],
        batch_size: int,
        recent_days: Optional[int],
        per_task: int,
        trending_max_age_days: int,
        after_id: Optional[int],
        before_id: Optional[int],
        shard: Optional[Tuple[int, int]],
        missing_only: bool,
        trust_local_cache: bool,
        max_failures: Optional[int],
        dry_run: bool,
        refresh_existing: bool,
        request_delay_seconds: Optional[float],
    ):
        if priority not in VALID_PRIORITIES:
            raise ValueError(
                f"Unknown priority '{priority}', expected one of {VALID_PRIORITIES}"
            )

        super().__init__(job_name="preload_thumbnails", log_level="INFO")
        self.settings = get_settings()
        self.priority = priority
        self.limit = limit
        self.batch_size = max(1, batch_size)
        self.recent_days = recent_days
        self.per_task = max(1, per_task)
        self.trending_max_age_days = max(1, trending_max_age_days)
        self.after_id = after_id
        self.before_id = before_id
        self.shard = shard
        self.missing_only = missing_only
        self.trust_local_cache = trust_local_cache
        self.max_failures = max_failures
        self.dry_run = dry_run
        self.refresh_existing = refresh_existing

        # missing-all defaults to trusting the local cache because probing the
        # bucket for tens of thousands of candidates is pure overhead when the
        # mirror cron is healthy.
        if priority == "missing-all" and not refresh_existing:
            self.trust_local_cache = True

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

    def _local_cache_dir(self) -> Path:
        if self.settings.thumbnail_storage_backend.lower() == "hf_bucket":
            return Path(self.settings.thumbnail_temp_cache_dir)
        return Path(self.settings.thumbnail_cache_dir)

    def _existing_local_filenames(self) -> set:
        cache_dir = self._local_cache_dir()
        if not cache_dir.exists():
            return set()
        return {p.name for p in cache_dir.glob("*.jpg")}

    def _iter_recent(self, session) -> Iterable[Candidate]:
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

    def _iter_trending(self, session) -> Iterable[Candidate]:
        sql = text(
            """
            WITH ranked AS (
                SELECT DISTINCT ON (tp.paper_id)
                    tp.paper_id,
                    tp.arxiv_id,
                    p.version,
                    tp.trending_score,
                    tp.current_stars
                FROM trending_papers_24h tp
                JOIN papers p ON p.id = tp.paper_id
                WHERE tp.paper_age_days <= :max_age_days
                  AND tp.arxiv_id IS NOT NULL
                  AND tp.arxiv_id <> ''
                ORDER BY tp.paper_id,
                         tp.trending_score DESC NULLS LAST,
                         tp.current_stars DESC
            )
            SELECT paper_id, arxiv_id, version
            FROM ranked
            ORDER BY trending_score DESC NULLS LAST, current_stars DESC
            LIMIT :limit
            """
        )
        rows = session.execute(
            sql,
            {
                "max_age_days": self.trending_max_age_days,
                "limit": self.limit if self.limit and self.limit > 0 else 1000,
            },
        ).fetchall()
        for row in rows:
            yield row[0], row[1], row[2] or "v1"

    def _iter_task_top(self, session) -> Iterable[Candidate]:
        sql = text(
            """
            WITH scored AS (
                SELECT
                    pt.task_id,
                    p.id AS paper_id,
                    p.arxiv_id,
                    p.version,
                    p.date_published,
                    COALESCE(MAX(r.trending_score), 0)        AS trending_score,
                    COALESCE(MAX(r.num_stars), 0)              AS stars
                FROM paper_tasks pt
                JOIN papers p ON p.id = pt.paper_id
                LEFT JOIN paper_repositories pr
                  ON pr.paper_id = p.id AND pr.is_official = TRUE
                LEFT JOIN repositories r ON r.id = pr.repository_id
                WHERE p.is_latest_version
                  AND p.arxiv_id IS NOT NULL
                  AND p.arxiv_id <> ''
                GROUP BY pt.task_id, p.id, p.arxiv_id, p.version, p.date_published
            ), ranked AS (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY task_id
                    ORDER BY trending_score DESC NULLS LAST,
                             stars DESC NULLS LAST,
                             date_published DESC NULLS LAST,
                             paper_id DESC
                ) AS rn
                FROM scored
            )
            SELECT DISTINCT ON (paper_id) paper_id, arxiv_id, version
            FROM ranked
            WHERE rn <= :per_task
            ORDER BY paper_id
            """
        )
        rows = session.execute(sql, {"per_task": self.per_task}).fetchall()
        candidates = [(row[0], row[1], row[2] or "v1") for row in rows]
        if self.limit is not None and self.limit > 0:
            candidates = candidates[: self.limit]
        for cand in candidates:
            yield cand

    def _iter_missing_all(self, session) -> Iterable[Candidate]:
        filters = [
            DBPaper.is_latest_version,
            DBPaper.arxiv_id.isnot(None),
            DBPaper.arxiv_id != "",
        ]
        if self.after_id is not None:
            filters.append(DBPaper.id > self.after_id)
        if self.before_id is not None:
            filters.append(DBPaper.id < self.before_id)
        if self.shard is not None:
            shard_index, shard_total = self.shard
            filters.append(DBPaper.id % shard_total == shard_index)

        query = (
            session.query(DBPaper.id, DBPaper.arxiv_id, DBPaper.version)
            .filter(and_(*filters))
            .order_by(DBPaper.id.asc())
        )
        if self.limit is not None and self.limit > 0:
            query = query.limit(self.limit)

        for row in query.yield_per(self.batch_size):
            yield row.id, row.arxiv_id, row.version or "v1"

    def _collect_candidates(self, session) -> List[Candidate]:
        if self.priority == "trending":
            iterator = self._iter_trending(session)
        elif self.priority == "task-top":
            iterator = self._iter_task_top(session)
        elif self.priority == "missing-all":
            iterator = self._iter_missing_all(session)
        else:
            iterator = self._iter_recent(session)

        raw = list(iterator)

        if self.missing_only or self.priority == "missing-all":
            existing = self._existing_local_filenames()
            filtered = [
                (paper_id, arxiv_id, version)
                for paper_id, arxiv_id, version in raw
                if build_thumbnail_filename(arxiv_id, version) not in existing
            ]
            self.logger.info(
                "Missing-only filter: %d -> %d candidates (skipped %d already on disk)",
                len(raw),
                len(filtered),
                len(raw) - len(filtered),
            )
            return filtered

        return raw

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

            if (
                not self.trust_local_cache
                and thumbnail_service._bucket_thumbnail_exists(filename)
            ):
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
            candidates = self._collect_candidates(session)
        finally:
            session.close()

        total = len(candidates)
        self.logger.info(
            "Found %d candidate papers "
            "(priority=%s, limit=%s, recent_days=%s, per_task=%s, "
            "after_id=%s, before_id=%s, shard=%s, missing_only=%s, "
            "trust_local_cache=%s, dry_run=%s, refresh_existing=%s, "
            "request_delay_seconds=%.1f)",
            total,
            self.priority,
            self.limit,
            self.recent_days,
            self.per_task if self.priority == "task-top" else None,
            self.after_id,
            self.before_id,
            f"{self.shard[0]}/{self.shard[1]}" if self.shard else None,
            self.missing_only,
            self.trust_local_cache,
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
            "(priority=%s, bucket=%s, prefix=%s, dry_run=%s, "
            "refresh_existing=%s, missing_only=%s, trust_local_cache=%s, "
            "request_delay_seconds=%.1f)",
            self.priority,
            self.settings.thumbnail_hf_bucket_id,
            self.settings.thumbnail_hf_bucket_prefix,
            self.dry_run,
            self.refresh_existing,
            self.missing_only,
            self.trust_local_cache,
            self.request_delay_seconds,
        )

        asyncio.run(self._run_async())

        self.logger.info("Thumbnail preload finished:")
        self.logger.info("  - Candidates seen: %d", self.candidates_seen)
        self.logger.info("  - Already cached:  %d", self.already_cached)
        self.logger.info("  - Generated:       %d", self.generated)
        self.logger.info("  - Would generate:  %d", self.would_generate)
        self.logger.info("  - Failures:        %d", self.failures)


def _parse_shard(value: str) -> Tuple[int, int]:
    if "/" not in value:
        raise argparse.ArgumentTypeError("expected --shard in the form i/n")
    left, right = value.split("/", 1)
    try:
        shard_index = int(left)
        shard_total = int(right)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))
    if shard_total <= 0:
        raise argparse.ArgumentTypeError("shard total must be > 0")
    if not 0 <= shard_index < shard_total:
        raise argparse.ArgumentTypeError(
            f"shard index must be in [0, {shard_total - 1}]"
        )
    return shard_index, shard_total


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preload paper thumbnails into a Hugging Face bucket so they are "
            "warm before /api/thumbnails/{filename} is requested."
        )
    )
    parser.add_argument(
        "--priority",
        choices=VALID_PRIORITIES,
        default="recent",
        help=(
            "Which candidate set to process. 'trending' uses the EMA "
            "trending_papers_24h view, 'task-top' takes the top --per-task "
            "papers per task tag, 'recent' is newest-first (optionally "
            "constrained to --recent-days), and 'missing-all' sweeps every "
            "latest-version arXiv paper without a local thumbnail."
        ),
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
            "Only consider papers published within the last N days "
            "(applies to --priority=recent). Papers without date_published "
            "are also included."
        ),
    )
    parser.add_argument(
        "--per-task",
        type=int,
        default=DEFAULT_PER_TASK,
        help=(
            "Top N papers per task to preload for --priority=task-top "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--trending-max-age-days",
        type=int,
        default=DEFAULT_TRENDING_MAX_AGE_DAYS,
        help=(
            "Maximum paper age (days) for --priority=trending candidates "
            "(default: %(default)s)."
        ),
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=None,
        help="Only consider papers with id > AFTER_ID (--priority=missing-all).",
    )
    parser.add_argument(
        "--before-id",
        type=int,
        default=None,
        help="Only consider papers with id < BEFORE_ID (--priority=missing-all).",
    )
    parser.add_argument(
        "--shard",
        type=_parse_shard,
        default=None,
        help=(
            "Process only papers where paper.id %% N == I, expressed as 'I/N' "
            "(--priority=missing-all)."
        ),
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help=(
            "Drop candidates whose thumbnail already exists in the local "
            "cache before processing. Implicit for --priority=missing-all."
        ),
    )
    parser.add_argument(
        "--trust-local-cache",
        action="store_true",
        help=(
            "Skip the per-paper HF bucket exists() probe. Safe when the "
            "mirror_thumbnails_to_disk cron is healthy and the local cache "
            "reflects bucket contents. Implicit for --priority=missing-all."
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
        priority=args.priority,
        limit=args.limit,
        batch_size=args.batch_size,
        recent_days=args.recent_days,
        per_task=args.per_task,
        trending_max_age_days=args.trending_max_age_days,
        after_id=args.after_id,
        before_id=args.before_id,
        shard=args.shard,
        missing_only=args.missing_only,
        trust_local_cache=args.trust_local_cache,
        max_failures=args.max_failures,
        dry_run=args.dry_run,
        refresh_existing=args.refresh_existing,
        request_delay_seconds=args.request_delay_seconds,
    )
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
