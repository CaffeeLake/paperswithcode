"""Tests for the preload_thumbnails cron job (visible priority + validity filter)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

WORKFLOWS_SCRIPTS_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows"
if str(WORKFLOWS_SCRIPTS_PATH) not in sys.path:
    sys.path.insert(0, str(WORKFLOWS_SCRIPTS_PATH))


def _make_job(
    *,
    priority: str = "visible",
    limit=None,
    citation_top: int = 1000,
    trending_top: int = 500,
    per_task: int = 20,
    missing_only: bool = True,
    cache_dir: Path | None = None,
):
    """Construct a ThumbnailPreloadJob without going through __init__'s settings."""
    from scripts.daily.preload_thumbnails import ThumbnailPreloadJob

    job = ThumbnailPreloadJob.__new__(ThumbnailPreloadJob)
    job.logger = MagicMock()
    job.settings = MagicMock(thumbnail_storage_backend="local")
    job.priority = priority
    job.limit = limit
    job.batch_size = 50
    job.recent_days = None
    job.per_task = per_task
    job.trending_max_age_days = 180
    job.citation_top = citation_top
    job.trending_top = trending_top
    job.after_id = None
    job.before_id = None
    job.shard = None
    job.missing_only = missing_only
    job.trust_local_cache = True
    job.max_failures = None
    job.dry_run = True
    job.refresh_existing = False
    job.request_delay_seconds = 0.0
    job.candidates_seen = 0
    job.already_cached = 0
    job.generated = 0
    job.would_generate = 0
    job.failures = 0

    if cache_dir is not None:
        job._local_cache_dir = lambda: cache_dir  # type: ignore[method-assign]
    return job


def test_iter_visible_dedups_paper_ids_citation_first():
    from scripts.daily.preload_thumbnails import Candidate

    job = _make_job()

    job._iter_citation_top = lambda session: iter(
        [Candidate(1, "1234.5678", "v1"), Candidate(2, "2345.6789", "v2")]
    )
    job._iter_trending = lambda session, limit_override=None: iter(
        [Candidate(2, "2345.6789", "v2"), Candidate(3, "3456.7890", "v1")]
    )
    job._iter_task_top = lambda session: iter(
        [Candidate(1, "1234.5678", "v1"), Candidate(4, "4567.8901", "v3")]
    )

    result = [
        (candidate.paper_id, candidate.arxiv_id, candidate.version)
        for candidate in job._iter_visible(session=None)
    ]

    assert result == [
        (1, "1234.5678", "v1"),
        (2, "2345.6789", "v2"),
        (3, "3456.7890", "v1"),
        (4, "4567.8901", "v3"),
    ]


def test_iter_visible_passes_trending_top_to_trending_iterator():
    job = _make_job(trending_top=42)

    job._iter_citation_top = lambda session: iter([])
    captured = {}

    def fake_trending(session, limit_override=None):
        captured["limit_override"] = limit_override
        return iter([])

    job._iter_trending = fake_trending
    job._iter_task_top = lambda session: iter([])

    list(job._iter_visible(session=None))

    assert captured["limit_override"] == 42


def test_collect_candidates_visible_caps_to_limit_after_dedup():
    from scripts.daily.preload_thumbnails import Candidate

    # missing_only=False so we don't go through the local-cache validity filter
    # for this test, which only checks the limit/dedup contract.
    job = _make_job(limit=2, missing_only=False)

    job._iter_citation_top = lambda session: iter(
        [
            Candidate(1, "1.2", "v1"),
            Candidate(2, "2.3", "v1"),
            Candidate(3, "3.4", "v1"),
        ]
    )
    job._iter_trending = lambda session, limit_override=None: iter([])
    job._iter_task_top = lambda session: iter([])

    result = job._collect_candidates(session=None)
    assert len(result) == 2
    assert [candidate.paper_id for candidate in result] == [1, 2]


def _save_jpeg(path: Path, width: int, height: int = 560) -> None:
    from PIL import Image

    Image.new("RGB", (width, height), "white").save(path, "JPEG", quality=85)


def test_missing_only_filter_keeps_invalid_local_thumbnails(tmp_path: Path):
    from scripts.daily.preload_thumbnails import Candidate, build_thumbnail_filename

    job = _make_job(cache_dir=tmp_path)

    valid_filename = build_thumbnail_filename("9999.0001", "v1")
    invalid_filename = build_thumbnail_filename("9999.0002", "v1")
    _save_jpeg(tmp_path / valid_filename, 400)
    _save_jpeg(tmp_path / invalid_filename, 200)  # wrong width

    job._iter_citation_top = lambda session: iter(
        [
            Candidate(10, "9999.0001", "v1"),
            Candidate(11, "9999.0002", "v1"),
            Candidate(12, "9999.0003", "v1"),  # missing entirely
        ]
    )
    job._iter_trending = lambda session, limit_override=None: iter([])
    job._iter_task_top = lambda session: iter([])

    result = job._collect_candidates(session=None)
    paper_ids = sorted(candidate.paper_id for candidate in result)

    assert paper_ids == [11, 12]


def test_process_paper_regenerates_when_local_thumbnail_invalid(tmp_path: Path):
    from scripts.daily.preload_thumbnails import (
        Candidate,
        ThumbnailPreloadJob,
        build_thumbnail_filename,
    )

    job = _make_job(cache_dir=tmp_path)
    job.dry_run = False
    job.trust_local_cache = True

    filename = build_thumbnail_filename("8888.0001", "v1")
    invalid_path = tmp_path / filename
    _save_jpeg(invalid_path, 100)  # wrong width

    thumbnail_service = MagicMock()
    thumbnail_service.get_filename.return_value = filename
    thumbnail_service._get_active_cache_path.return_value = invalid_path

    async def fake_generate(arxiv_id, version, force=False):
        captured["force"] = force
        return invalid_path

    captured: dict = {}
    thumbnail_service.generate_thumbnail = fake_generate

    import asyncio

    status = asyncio.run(
        ThumbnailPreloadJob._process_paper(
            job, thumbnail_service, Candidate(1, "8888.0001", "v1")
        )
    )

    assert status == "generated"
    assert captured["force"] is True


def test_process_paper_treats_valid_local_thumbnail_as_cached(tmp_path: Path):
    from scripts.daily.preload_thumbnails import (
        Candidate,
        ThumbnailPreloadJob,
        build_thumbnail_filename,
    )

    job = _make_job(cache_dir=tmp_path)
    job.dry_run = False
    job.trust_local_cache = True

    filename = build_thumbnail_filename("8888.0002", "v1")
    valid_path = tmp_path / filename
    _save_jpeg(valid_path, 400)

    thumbnail_service = MagicMock()
    thumbnail_service.get_filename.return_value = filename
    thumbnail_service._get_active_cache_path.return_value = valid_path

    import asyncio

    status = asyncio.run(
        ThumbnailPreloadJob._process_paper(
            job, thumbnail_service, Candidate(1, "8888.0002", "v1")
        )
    )

    assert status == "cached"
    thumbnail_service.generate_thumbnail.assert_not_called()
