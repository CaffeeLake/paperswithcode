#!/usr/bin/env python3
"""Regenerate one or more paper thumbnails and verify card sizing.

Usage (from repo root):
  uv run --env-file backend/keys.env \\
    .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py 2512.20856
  uv run --env-file backend/keys.env \\
    .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py --paper-id 54972
  uv run --env-file backend/keys.env \\
    .agents/skills/fix-paper-thumbnail/scripts/regenerate_thumbnail.py --url https://paperswithcode.co/paper/2512.20856
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.database.connection import db_manager  # noqa: E402
from backend.models.database import Paper as DBPaper  # noqa: E402
from backend.services.thumbnail_service import (  # noqa: E402
    CARD_THUMB_ASPECT,
    EXPECTED_THUMBNAIL_WIDTH,
    ThumbnailService,
    build_custom_thumbnail_url,
    build_thumbnail_filename,
    build_thumbnail_url,
    is_thumbnail_valid,
)
from PIL import Image  # noqa: E402


def _resolve_paper(
    session, *, arxiv_id: str | None, paper_id: int | None, url: str | None
) -> DBPaper:
    if url:
        match = re.search(r"/paper/([^/?#]+)", url)
        if not match:
            raise SystemExit(f"Could not parse paper id from URL: {url}")
        slug = match.group(1)
        if re.fullmatch(r"\d+\.\d+", slug):
            arxiv_id = slug
        else:
            paper_id = int(slug)

    if arxiv_id:
        paper = (
            session.query(DBPaper)
            .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.is_latest_version.is_(True))
            .one_or_none()
        )
        if paper is None:
            raise SystemExit(f"No latest-version paper for arxiv_id={arxiv_id}")
        return paper

    if paper_id is not None:
        paper = session.get(DBPaper, paper_id)
        if paper is None:
            raise SystemExit(f"No paper with id={paper_id}")
        return paper

    raise SystemExit("Provide arxiv_id, --paper-id, or --url")


def _describe_image(path: Path) -> dict:
    with Image.open(path) as img:
        ratio = img.height / img.width
        return {
            "path": str(path),
            "width": img.width,
            "height": img.height,
            "ratio": round(ratio, 4),
            "valid": is_thumbnail_valid(path),
        }


async def _regenerate_one(paper: DBPaper, *, force: bool) -> dict:
    service = ThumbnailService()
    if paper.source == "external":
        if not paper.source_url:
            raise SystemExit(f"External paper {paper.id} has no source_url")
        path = await service.generate_external_thumbnail(
            paper.id, paper.source_url, force=force
        )
        filename = path.name
        thumbnail_url = build_custom_thumbnail_url(filename)
        session = db_manager.session_local()
        try:
            row = session.get(DBPaper, paper.id)
            if row is not None:
                row.thumbnail_url = thumbnail_url
                session.commit()
        finally:
            session.close()
    else:
        if not paper.arxiv_id:
            raise SystemExit(f"Paper {paper.id} has no arxiv_id")
        version = paper.version or "v1"
        path = await service.generate_thumbnail(paper.arxiv_id, version, force=force)
        filename = build_thumbnail_filename(paper.arxiv_id, version)
        thumbnail_url = build_thumbnail_url(filename)

    stats = _describe_image(path)
    expected_height = int(EXPECTED_THUMBNAIL_WIDTH / CARD_THUMB_ASPECT)
    stats.update(
        {
            "paper_id": paper.id,
            "arxiv_id": paper.arxiv_id,
            "source": paper.source,
            "thumbnail_url": thumbnail_url,
            "expected_size": (EXPECTED_THUMBNAIL_WIDTH, expected_height),
        }
    )
    return stats


async def _main_async(args: argparse.Namespace) -> int:
    session = db_manager.session_local()
    try:
        papers = []
        for token in args.papers:
            if token.isdigit() and args.papers.count(token) == 1 and not args.url:
                papers.append(
                    _resolve_paper(
                        session, arxiv_id=None, paper_id=int(token), url=None
                    )
                )
            else:
                papers.append(
                    _resolve_paper(session, arxiv_id=token, paper_id=None, url=None)
                )
        if args.url and not args.papers:
            papers.append(
                _resolve_paper(
                    session, arxiv_id=None, paper_id=args.paper_id, url=args.url
                )
            )
        elif args.paper_id is not None and not args.papers:
            papers.append(
                _resolve_paper(session, arxiv_id=None, paper_id=args.paper_id, url=None)
            )
    finally:
        session.close()

    exit_code = 0
    for paper in papers:
        stats = await _regenerate_one(paper, force=not args.no_force)
        print(
            f"paper_id={stats['paper_id']} arxiv_id={stats['arxiv_id']} "
            f"size={stats['width']}x{stats['height']} ratio={stats['ratio']} "
            f"valid={stats['valid']} url={stats['thumbnail_url']}"
        )
        if not stats["valid"]:
            print(
                "  WARNING: thumbnail failed validation — inspect PDF/render pipeline",
                file=sys.stderr,
            )
            exit_code = 1
        elif (stats["width"], stats["height"]) != stats["expected_size"]:
            print(
                f"  WARNING: expected {stats['expected_size'][0]}x{stats['expected_size'][1]}",
                file=sys.stderr,
            )
            exit_code = 1
    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate paper thumbnail(s)")
    parser.add_argument("papers", nargs="*", help="arXiv ids (e.g. 2512.20856)")
    parser.add_argument("--paper-id", type=int, default=None)
    parser.add_argument("--url", default=None, help="paperswithcode.co paper URL")
    parser.add_argument(
        "--no-force",
        action="store_true",
        help="Skip regeneration when a valid thumbnail already exists locally",
    )
    raise SystemExit(asyncio.run(_main_async(parser.parse_args())))


if __name__ == "__main__":
    main()
