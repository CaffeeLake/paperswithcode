#!/usr/bin/env python3
"""
Sync generated paper thumbnails to a private Hugging Face Storage Bucket.

By default this script performs a dry run. Pass --apply to upload files.
"""

import argparse
import os
from pathlib import Path

from huggingface_hub import create_bucket, sync_bucket

from backend.config import get_settings


def _build_destination(bucket_id: str, prefix: str) -> str:
    cleaned_prefix = prefix.strip("/")
    if cleaned_prefix:
        return f"hf://buckets/{bucket_id}/{cleaned_prefix}"
    return f"hf://buckets/{bucket_id}"


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(
        description="Sync the local thumbnail cache to a Hugging Face bucket."
    )
    parser.add_argument(
        "--local-dir",
        default=settings.thumbnail_cache_dir,
        help="Local thumbnail directory to sync.",
    )
    parser.add_argument(
        "--bucket-id",
        default=settings.thumbnail_hf_bucket_id,
        help="Hugging Face bucket ID, e.g. owner/pwc-thumbnails.",
    )
    parser.add_argument(
        "--prefix",
        default=settings.thumbnail_hf_bucket_prefix,
        help="Destination prefix inside the bucket.",
    )
    parser.add_argument(
        "--create-bucket",
        action="store_true",
        help="Create the private bucket before syncing.",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete remote files that no longer exist locally.",
    )
    parser.add_argument(
        "--include",
        action="append",
        help="Include filter passed to Hugging Face sync. Can be repeated.",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        help="Exclude filter passed to Hugging Face sync. Can be repeated.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the sync. Omit this flag to preview with a dry run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    local_dir = Path(args.local_dir)
    bucket_id = args.bucket_id.strip()
    token = os.environ.get("PWC_HF_TOKEN") or os.environ.get("HF_TOKEN")

    if not local_dir.exists() or not local_dir.is_dir():
        raise SystemExit(f"Local thumbnail directory does not exist: {local_dir}")
    if not bucket_id:
        raise SystemExit("Bucket ID is required via --bucket-id or config.")

    dry_run = not args.apply
    destination = _build_destination(bucket_id, args.prefix)

    print(f"Source: {local_dir}")
    print(f"Destination: {destination}")
    print(f"Mode: {'apply' if args.apply else 'dry-run'}")

    if args.create_bucket:
        if dry_run:
            print(f"Would create private bucket: {bucket_id}")
        else:
            create_bucket(bucket_id, private=True, exist_ok=True, token=token)
            print(f"Ensured private bucket exists: {bucket_id}")

    plan = sync_bucket(
        str(local_dir),
        destination,
        delete=args.delete,
        include=args.include,
        exclude=args.exclude,
        dry_run=dry_run,
        verbose=True,
        token=token,
    )
    print(plan)


if __name__ == "__main__":
    main()
