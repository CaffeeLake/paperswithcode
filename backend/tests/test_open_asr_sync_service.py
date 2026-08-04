"""Validation and idempotency tests for the living Open ASR sync."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import (
    Base,
    Dataset,
    Evaluation,
    Metric,
    Paper,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.open_asr_sync_service import (
    DEFAULT_COLUMNS,
    LEGACY_SOURCE_URL,
    MANAGED_METHODOLOGY_PREFIX,
    SPACE_APP_URL,
    SPACE_SOURCE_URL,
    OpenAsrEntry,
    OpenAsrSyncService,
    fetch_open_asr_leaderboard,
    parse_open_asr_leaderboard,
)


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
@compiles(JSONB, "sqlite")
@compiles(TSVECTOR, "sqlite")
def _compile_postgres_types_sqlite(_element, _compiler, **_kw):
    return "JSON"


def _payload(count: int = 40):
    return {
        "headers": ["Rank", "model", "Average WER ⬇️", "RTFx ⬆️️", "License"],
        "data": [
            [
                rank,
                f'<a href="https://huggingface.co/org/model-{rank}">org/model-{rank}</a>',
                f"{4 + rank / 10:.1f}" + (" 🥇" if rank == 1 else ""),
                "NA" if rank == 1 else rank * 10,
                "Proprietary" if rank == 1 else "apache-2.0",
            ]
            for rank in range(1, count + 1)
        ],
    }


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Task.__table__,
            Dataset.__table__,
            Metric.__table__,
            TaskDataset.__table__,
            TaskDatasetMetric.__table__,
            Evaluation.__table__,
        ],
    )
    session = Session(engine)
    task = Task(
        id=12, name="Automatic Speech Recognition", slug="automatic-speech-recognition"
    )
    dataset = Dataset(id=181, name="Open ASR Leaderboard", slug="open-asr-leaderboard")
    wer = Metric(id=1, name="WER", direction="lower_is_better")
    rtfx = Metric(id=38, name="RTFx", direction="higher_is_better")
    session.add_all([task, dataset, wer, rtfx])
    session.add(TaskDataset(task_id=task.id, dataset_id=dataset.id))
    session.add_all(
        [
            TaskDatasetMetric(task_id=task.id, dataset_id=dataset.id, metric_id=wer.id),
            TaskDatasetMetric(
                task_id=task.id, dataset_id=dataset.id, metric_id=rtfx.id
            ),
        ]
    )
    session.add_all(
        [
            Paper(
                id=1,
                title="Model paper",
                arxiv_id="2311.00430",
                source="arxiv",
                version="v1",
                is_latest_version=True,
            ),
            Paper(
                id=2,
                title="Legacy external model",
                source="external",
                source_url="https://huggingface.co/vendor/legacy",
                version="v1",
                is_latest_version=True,
            ),
        ]
    )
    session.commit()
    return session


def test_parse_and_fetch_public_leaderboard_contract():
    payload = _payload()

    class FakeClient:
        def __init__(self, url, *, verbose):
            assert url == SPACE_APP_URL
            assert verbose is False

        def predict(self, query, proprietary, llm, columns, *, api_name):
            assert (query, proprietary, llm) == ("", True, False)
            assert columns == DEFAULT_COLUMNS
            assert api_name == "/filter_main_table"
            return payload

    entries = fetch_open_asr_leaderboard(FakeClient)
    assert entries[0] == OpenAsrEntry("org/model-1", 1, 4.1, None, False)
    assert entries[1] == OpenAsrEntry("org/model-2", 2, 4.2, 20.0, True)


def test_parser_rejects_truncated_or_noncontiguous_data():
    with pytest.raises(ValueError, match="expected 40-150"):
        parse_open_asr_leaderboard(_payload(10))
    payload = _payload()
    payload["data"][-1][0] = 41
    with pytest.raises(ValueError, match="contiguous"):
        parse_open_asr_leaderboard(payload)


def test_sync_replaces_legacy_and_only_deletes_stale_managed_rows(monkeypatch):
    session = _session()
    session.add_all(
        [
            Evaluation(
                paper_id=2,
                task_id=12,
                dataset_id=181,
                model_name="Legacy",
                methodology=(
                    "Open ASR Leaderboard rank 1; sourced from "
                    "vendor/legacy/.eval_results/open_asr_leaderboard.yaml (main)"
                ),
                metrics={"WER": 9.0},
                best_metric="WER",
                external_source_url=LEGACY_SOURCE_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=12,
                dataset_id=181,
                model_name="gone/model",
                methodology=f"{MANAGED_METHODOLOGY_PREFIX} old",
                metrics={"WER": 10.0},
                best_metric="WER",
                external_source_url=SPACE_SOURCE_URL,
            ),
            Evaluation(
                paper_id=1,
                task_id=12,
                dataset_id=181,
                model_name="Manual paper result",
                methodology="Human curated",
                metrics={"WER": 3.0},
                best_metric="WER",
            ),
        ]
    )
    session.commit()
    monkeypatch.setitem(
        __import__(
            "backend.services.open_asr_sync_service", fromlist=["MODEL_PAPER_ARXIV_IDS"]
        ).MODEL_PAPER_ARXIV_IDS,
        "distil-whisper/distil-large-v3.5",
        "2311.00430",
    )
    entries = [
        OpenAsrEntry("vendor/legacy", 1, 5.0, None, False),
        OpenAsrEntry("distil-whisper/distil-large-v3.5", 2, 6.0, 100.0, True),
        OpenAsrEntry("vendor/unmatched", 3, 7.0, 50.0, False),
    ]
    now = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)
    stats = OpenAsrSyncService(session).sync(entries, fetched_at=now)

    assert stats.to_dict() == {
        "fetched": 3,
        "matched": 2,
        "created": 2,
        "updated": 0,
        "deleted": 2,
        "unmatched_models": ["vendor/unmatched"],
        "missing_papers": [],
    }
    rows = {row.model_name: row for row in session.query(Evaluation).all()}
    assert set(rows) == {
        "vendor/legacy",
        "distil-whisper/distil-large-v3.5",
        "Manual paper result",
    }
    assert rows["vendor/legacy"].paper_id == 2
    assert rows["vendor/legacy"].metrics == {"WER": 5.0}
    assert rows["distil-whisper/distil-large-v3.5"].metrics == {
        "WER": 6.0,
        "RTFx": 100.0,
    }
    assert rows["Manual paper result"].best_rank == 1

    second = OpenAsrSyncService(session).sync(entries, fetched_at=now)
    assert second.created == 0
    assert second.updated == 2
    assert second.deleted == 0
    assert session.query(Evaluation).count() == 3
