"""
Daily Thumbnail Local-Disk Mirror CRON Job

Mirrors the entire Hugging Face thumbnail bucket prefix to the VPS local cache
directory served by `/api/thumbnails/{filename}`. After this job runs the
endpoint can answer every paper-thumbnail request from local disk and never
needs to do a per-request HF bucket download (or PDF rasterisation), which is
the source of the slow thumbnail loading on listing pages.

Behavior:
- Uses `huggingface_hub.sync_bucket` for incremental, resumable mirroring
  (compares sizes + mtimes, only downloads what changed).
- Mirrors `hf://buckets/{bucket_id}/{prefix}` -> `PWC_THUMBNAIL_TEMP_CACHE_DIR`.
- Never deletes local files (so manually-served / freshly-generated thumbnails
  are preserved even if they're not yet in the bucket).
- Pairs with `preload_thumbnails.py`: that job ensures new thumbnails reach the
  bucket; this job ensures they reach the VPS disk.

Schedule: Daily, after `preload_thumbnails`.
Dependencies: PWC_THUMBNAIL_STORAGE_BACKEND=hf_bucket plus
PWC_THUMBNAIL_HF_BUCKET_ID, PWC_THUMBNAIL_HF_BUCKET_PREFIX, PWC_HF_TOKEN, and
a writable PWC_THUMBNAIL_TEMP_CACHE_DIR.
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Optional

from huggingface_hub import sync_bucket

from backend.config import get_settings
from scripts.utils.cron_helpers import CronJobBase


class ThumbnailDiskMirrorJob(CronJobBase):
    """Mirror the thumbnail bucket prefix to the VPS local cache directory."""

    def __init__(self, dry_run: bool, delete: bool):
        super().__init__(job_name="mirror_thumbnails_to_disk", log_level="INFO")
        self.settings = get_settings()
        self.dry_run = dry_run
        self.delete = delete

    def _validate_settings(self) -> None:
        backend = (self.settings.thumbnail_storage_backend or "").lower()
        if backend != "hf_bucket":
            raise RuntimeError(
                "PWC_THUMBNAIL_STORAGE_BACKEND must be 'hf_bucket' to mirror the "
                f"thumbnail bucket (current: {backend or 'unset'})"
            )

        bucket_id = (self.settings.thumbnail_hf_bucket_id or "").strip()
        if not bucket_id:
            raise RuntimeError("PWC_THUMBNAIL_HF_BUCKET_ID is required")

        if not (self.settings.hf_token or "").strip():
            raise RuntimeError(
                "PWC_HF_TOKEN is required to authenticate against the Hugging Face bucket"
            )

    def _bucket_source(self) -> str:
        bucket_id = self.settings.thumbnail_hf_bucket_id.strip()
        prefix = (self.settings.thumbnail_hf_bucket_prefix or "").strip("/")
        if prefix:
            return f"hf://buckets/{bucket_id}/{prefix}"
        return f"hf://buckets/{bucket_id}"

    def _local_dest(self) -> Path:
        return Path(self.settings.thumbnail_temp_cache_dir)

    def run(self) -> None:
        self._validate_settings()

        source = self._bucket_source()
        dest = self._local_dest()
        dest.mkdir(parents=True, exist_ok=True)

        self.logger.info(
            "Mirroring %s -> %s (dry_run=%s, delete=%s)",
            source,
            dest,
            self.dry_run,
            self.delete,
        )

        start = time.time()
        plan = sync_bucket(
            source=source,
            dest=str(dest),
            delete=self.delete,
            dry_run=self.dry_run,
            quiet=True,
            token=self.settings.hf_token,
        )
        elapsed = time.time() - start

        summary = plan.summary()
        downloads = int(summary.get("downloads", 0))
        deletes = int(summary.get("deletes", 0))
        skips = int(summary.get("skips", 0))
        total_size = int(summary.get("total_size", 0))
        total_size_mb = total_size / (1024 * 1024)

        verb = "Would have transferred" if self.dry_run else "Transferred"
        self.logger.info(
            "%s %d files (%.1f MB total in plan), %d skipped, %d deletes, in %.1fs",
            verb,
            downloads,
            total_size_mb,
            skips,
            deletes,
            elapsed,
        )

        try:
            local_files = sum(1 for _ in dest.glob("*.jpg"))
            local_bytes = sum(p.stat().st_size for p in dest.glob("*.jpg"))
            self.logger.info(
                "Local cache now contains %d .jpg files (%.1f MB) in %s",
                local_files,
                local_bytes / (1024 * 1024),
                dest,
            )
            self.logger.info(
                "THUMBNAIL_MIRROR_SUMMARY %s",
                json.dumps(
                    {
                        "downloads": downloads,
                        "deletes": deletes,
                        "skips": skips,
                        "file_count": local_files,
                        "file_bytes": local_bytes,
                    }
                ),
            )
        except Exception as exc:
            self.logger.warning("Could not summarise local cache size: %s", exc)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Mirror the Hugging Face thumbnail bucket prefix to the VPS local "
            "cache directory served by /api/thumbnails/{filename}."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan transfers without writing any files locally.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help=(
            "Delete local files not present in the bucket. Off by default so "
            "freshly-generated thumbnails are preserved."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    job = ThumbnailDiskMirrorJob(dry_run=args.dry_run, delete=args.delete)
    success = job.execute()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
