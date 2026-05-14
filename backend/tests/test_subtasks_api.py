"""
Tests for first-class task hierarchy (subtasks):
  - leaderboards key off the most-specific task (the child / subtask)
  - parent task pages can roll up child benchmarks and evaluations via
    `include_descendants=True`
  - rank recalculation stays scoped per (task_id, dataset_id, best_metric)

These mirror the post-migration shape in production where Language Modeling
benchmarks live under per-capability subtasks (World Knowledge, Math,
Reasoning, Coding, ...).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.database.connection import get_database_session
from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    Metric as DBMetric,
    Paper as DBPaper,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.dataset_service import DatasetService
from backend.services.evaluation_service import EvaluationService


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    """SQLite cannot autoincrement BIGINT; rewrite to INTEGER for tests."""
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)
    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)


def _seed_lm_with_subtasks(db):
    """Build a minimal Language Modeling parent + two subtasks + benchmarks.

    Layout:
        Language Modeling (id=1)               <-- parent task; no benchmarks
          ├── World Knowledge (id=2)
          │     - MMLU (dataset 1, metric Accuracy, two evaluations)
          │     - GPQA Diamond (dataset 2, metric Accuracy)
          └── Math (id=3)
                - GSM8k (dataset 3, metric Accuracy)
    """
    parent = DBTask(id=1, name="Language Modeling", slug="language-modeling", level=0)
    knowledge = DBTask(
        id=2,
        name="World Knowledge",
        slug="world-knowledge",
        parent_id=1,
        level=1,
    )
    math = DBTask(id=3, name="Math", slug="math", parent_id=1, level=1)
    db.add_all([parent, knowledge, math])

    datasets = [
        DBDataset(id=1, name="MMLU", slug="mmlu"),
        DBDataset(id=2, name="GPQA Diamond", slug="gpqa-diamond"),
        DBDataset(id=3, name="GSM8k", slug="gsm8k"),
    ]
    db.add_all(datasets)

    db.add(DBMetric(id=1, name="Accuracy", direction="higher_is_better"))

    db.add_all(
        [
            TaskDataset(task_id=2, dataset_id=1),
            TaskDataset(task_id=2, dataset_id=2),
            TaskDataset(task_id=3, dataset_id=3),
            TaskDatasetMetric(task_id=2, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=2, dataset_id=2, metric_id=1),
            TaskDatasetMetric(task_id=3, dataset_id=3, metric_id=1),
        ]
    )

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2026.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 5)
    ]
    db.add_all(papers)

    db.add_all(
        [
            DBEvaluation(
                id=10,
                paper_id=1,
                task_id=2,
                dataset_id=1,
                model_name="GPT-x",
                metrics={"Accuracy": "85.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=11,
                paper_id=2,
                task_id=2,
                dataset_id=1,
                model_name="GPT-y",
                metrics={"Accuracy": "90.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=12,
                paper_id=3,
                task_id=2,
                dataset_id=2,
                model_name="GPT-x",
                metrics={"Accuracy": "60.0"},
                best_metric="Accuracy",
            ),
            DBEvaluation(
                id=13,
                paper_id=4,
                task_id=3,
                dataset_id=3,
                model_name="GPT-y",
                metrics={"Accuracy": "95.0"},
                best_metric="Accuracy",
            ),
        ]
    )

    db.commit()


def test_create_evaluation_on_child_task_validates_against_child_leaderboard(
    db_session,
):
    """Creating an evaluation against a subtask (child task) must succeed
    when the (child, dataset, metric) triple exists in `task_dataset_metrics`."""
    _seed_lm_with_subtasks(db_session)

    service = EvaluationService(db_session)
    created = service.create_evaluation(
        paper_id=1,
        task_id=2,  # World Knowledge child task
        dataset_id=2,  # GPQA Diamond
        metrics={"Accuracy": "70.0"},
        best_metric="Accuracy",
        model_name="ModelZ",
    )

    assert created.task_id == "2"
    assert created.dataset_id == "2"
    assert created.best_metric == "Accuracy"


def test_create_evaluation_on_parent_task_without_triple_fails(db_session):
    """The parent Language Modeling task no longer owns benchmarks, so
    creating an evaluation pointing at the parent must fail validation."""
    _seed_lm_with_subtasks(db_session)

    service = EvaluationService(db_session)
    with pytest.raises(ValueError, match="No leaderboard defined"):
        service.create_evaluation(
            paper_id=1,
            task_id=1,  # parent Language Modeling
            dataset_id=1,
            metrics={"Accuracy": "70.0"},
            best_metric="Accuracy",
            model_name="ModelZ",
        )


def test_get_datasets_for_parent_without_descendants_returns_nothing(db_session):
    """Parent Language Modeling page must not surface benchmarks unless the
    caller opts into rolling up subtask benchmarks via include_descendants."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(task_id=1)
    assert [d.slug for d in result.results] == []


def test_get_datasets_for_parent_with_include_descendants_rolls_up(db_session):
    """include_descendants=True surfaces benchmarks owned by all subtasks."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(
        task_id=1, include_descendants=True
    )

    assert sorted(d.slug for d in result.results) == [
        "gpqa-diamond",
        "gsm8k",
        "mmlu",
    ]


def test_get_datasets_for_child_task_only_returns_its_benchmarks(db_session):
    """Fetching by the child task id must scope strictly to that subtask."""
    _seed_lm_with_subtasks(db_session)

    result = DatasetService(db_session).get_datasets(task_id=2)
    assert sorted(d.slug for d in result.results) == ["gpqa-diamond", "mmlu"]


def test_get_evaluations_with_include_descendants_rolls_up_subtask_evals(client):
    """The /evaluations API supports include_descendants for parent tasks."""
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.close()

    parent_only = client.get("/api/v1/evaluations/?task_id=1&page_size=50").json()
    assert parent_only["count"] == 0

    rolled_up = client.get(
        "/api/v1/evaluations/?task_id=1&include_descendants=true&page_size=50"
    ).json()
    assert rolled_up["count"] == 4

    child_only = client.get("/api/v1/evaluations/?task_id=2&page_size=50").json()
    assert child_only["count"] == 3
    assert all(row["task_id"] == "2" for row in child_only["results"])


def test_recalculate_ranks_is_scoped_to_child_task(db_session):
    """Rank recalculation runs per (child_task_id, dataset_id, best_metric)
    so two subtasks sharing nothing don't pollute each other's ordering."""
    _seed_lm_with_subtasks(db_session)
    service = EvaluationService(db_session)

    updated = service.recalculate_ranks(task_id=2, dataset_id=1, metric_name="Accuracy")
    assert updated == 2

    rows = (
        db_session.query(DBEvaluation)
        .filter(DBEvaluation.task_id == 2, DBEvaluation.dataset_id == 1)
        .all()
    )
    by_id = {row.id: row.best_rank for row in rows}
    # Higher Accuracy wins; eval 11 = 90.0 -> rank 1, eval 10 = 85.0 -> rank 2.
    assert by_id == {11: 1, 10: 2}

    # The other subtask leaderboard is untouched until we recalc it.
    other_eval = db_session.query(DBEvaluation).filter(DBEvaluation.id == 13).first()
    assert other_eval.best_rank is None


def test_task_children_endpoint_lists_subtasks_for_parent(client):
    """Frontend /tasks/{id}/children powers the parent task page subtask grid."""
    db = TestingSessionLocal()
    _seed_lm_with_subtasks(db)
    db.close()

    response = client.get("/api/v1/tasks/1/children")
    assert response.status_code == 200
    payload = response.json()
    slugs = sorted(t["slug"] for t in payload["results"])
    assert slugs == ["math", "world-knowledge"]
    assert all(t["parent_id"] == "1" for t in payload["results"])
    assert all(t["level"] == 1 for t in payload["results"])


if __name__ == "__main__":
    pytest.main([__file__])
