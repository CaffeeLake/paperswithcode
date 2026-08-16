#!/usr/bin/env python3
"""Publish a prepared paper thumbnail with a content-addressed filename."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

from backend.database.connection import get_database_session
from backend.models.database import Paper
from backend.services.thumbnail_service import (
    ThumbnailService,
    build_custom_thumbnail_url,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-id", required=True, type=int)
    parser.add_argument("--image", required=True, type=Path)
    args = parser.parse_args()

    raw = args.image.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:12]
    filename = f"paper_{args.paper_id}_source_art_{digest}.jpg"

    with Image.open(args.image) as opened:
        image = opened.convert("RGB")
        if image.width != 400 or image.height < 400:
            parser.error(f"expected a 400 px wide portrait image, got {image.size}")

    service = ThumbnailService()
    service.validate_custom_filename(filename)
    target = service._get_active_cache_path(filename)

    session_gen = get_database_session()
    db = next(session_gen)
    try:
        paper = db.get(Paper, args.paper_id)
        if paper is None:
            raise SystemExit(f"paper {args.paper_id} not found")
        previous_url = paper.thumbnail_url
        service._save_thumbnail(image, target)
        service._upload_to_bucket(target, filename)
        url = build_custom_thumbnail_url(filename)
        paper.thumbnail_url = url
        db.commit()
        print(
            json.dumps(
                {
                    "paper_id": paper.id,
                    "title": paper.title,
                    "previous_thumbnail_url": previous_url,
                    "thumbnail_url": url,
                    "filename": filename,
                    "size": [image.width, image.height],
                },
                indent=2,
            )
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
