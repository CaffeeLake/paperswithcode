"""
Regression tests for task-dataset membership and featured benchmark ordering.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.models.database import (
    Base,
    Dataset as DBDataset,
    Metric as DBMetric,
    Paper as DBPaper,
    PaperDataset,
    Task as DBTask,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.services.dataset_service import DatasetService


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
def task_dataset_fixture(db_session):
    task = DBTask(id=1, name="Coding Agents", slug="coding-agents", level=0)
    db_session.add(task)

    datasets = [
        DBDataset(id=1, name="Alpha", slug="alpha"),
        DBDataset(id=2, name="SWE-Bench Verified", slug="swe-bench-verified"),
        DBDataset(id=3, name="LiveCodeBench", slug="livecodebench"),
        DBDataset(id=4, name="Beta", slug="beta"),
    ]
    db_session.add_all(datasets)

    papers = [
        DBPaper(
            id=i,
            title=f"Paper {i}",
            abstract=f"Abstract {i}",
            arxiv_id=f"2026.0{i:04d}",
            version="v1",
            is_latest_version=True,
        )
        for i in range(1, 8)
    ]
    db_session.add_all(papers)

    db_session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2, featured_rank=1),
            TaskDataset(task_id=1, dataset_id=3, featured_rank=2),
            TaskDataset(task_id=1, dataset_id=4),
        ]
    )

    db_session.add_all(
        [
            PaperDataset(paper_id=1, dataset_id=1),
            PaperDataset(paper_id=2, dataset_id=1),
            PaperDataset(paper_id=3, dataset_id=1),
            PaperDataset(paper_id=4, dataset_id=2),
            PaperDataset(paper_id=5, dataset_id=3),
            PaperDataset(paper_id=6, dataset_id=3),
            PaperDataset(paper_id=7, dataset_id=4),
        ]
    )

    metrics = [
        DBMetric(id=1, name="Accuracy", direction="higher_is_better"),
        DBMetric(id=2, name="Pass@1", direction="higher_is_better"),
    ]
    db_session.add_all(metrics)

    # Dataset 3 has two metrics for the same task-dataset pair. The task-filtered
    # dataset query should still return it once.
    db_session.add_all(
        [
            TaskDatasetMetric(task_id=1, dataset_id=2, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=3, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=3, metric_id=2),
            TaskDatasetMetric(task_id=1, dataset_id=1, metric_id=1),
            TaskDatasetMetric(task_id=1, dataset_id=4, metric_id=1),
        ]
    )

    db_session.commit()


def test_task_datasets_without_featured_ranks_use_requested_fallback(db_session):
    task = DBTask(id=1, name="Image Classification", slug="image-classification")
    db_session.add(task)
    db_session.add_all(
        [
            DBDataset(id=1, name="Small", slug="small"),
            DBDataset(id=2, name="Large", slug="large"),
        ]
    )
    db_session.add_all(
        [
            TaskDataset(task_id=1, dataset_id=1),
            TaskDataset(task_id=1, dataset_id=2),
            PaperDataset(paper_id=1, dataset_id=2),
            PaperDataset(paper_id=2, dataset_id=2),
            PaperDataset(paper_id=3, dataset_id=1),
        ]
    )
    db_session.add_all(
        [
            DBPaper(id=1, title="One", abstract="A", arxiv_id="2026.00001"),
            DBPaper(id=2, title="Two", abstract="B", arxiv_id="2026.00002"),
            DBPaper(id=3, title="Three", abstract="C", arxiv_id="2026.00003"),
        ]
    )
    db_session.commit()

    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert [dataset.slug for dataset in result.results] == ["large", "small"]
    assert [dataset.featured_rank for dataset in result.results] == [None, None]


def test_featured_ranks_order_before_fallback_and_return_once(
    db_session, task_dataset_fixture
):
    result = DatasetService(db_session).get_datasets(
        task_id=1, order_by="paper_count", order_dir="desc"
    )

    assert [dataset.slug for dataset in result.results] == [
        "swe-bench-verified",
        "livecodebench",
        "alpha",
        "beta",
    ]
    assert [dataset.featured_rank for dataset in result.results] == [1, 2, None, None]
    assert (
        len([dataset for dataset in result.results if dataset.slug == "livecodebench"])
        == 1
    )


def test_unfiltered_dataset_queries_do_not_populate_featured_rank(
    db_session, task_dataset_fixture
):
    result = DatasetService(db_session).get_datasets(order_by="name", order_dir="asc")

    assert [dataset.name for dataset in result.results] == [
        "Alpha",
        "Beta",
        "LiveCodeBench",
        "SWE-Bench Verified",
    ]
    assert all(dataset.featured_rank is None for dataset in result.results)
