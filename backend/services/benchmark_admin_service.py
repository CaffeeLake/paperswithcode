"""Idempotent benchmark creation for the maintenance CLI."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import (
    Dataset,
    Metric,
    PaperTask,
    Task,
    TaskDataset,
    TaskDatasetMetric,
)
from backend.utils.paper_reference import resolve_paper
from backend.utils.slug_utils import slugify


@dataclass(frozen=True)
class BenchmarkAddResult:
    status: str
    id: int
    name: str
    slug: str
    tasks: list[str]
    metrics: list[str]
    source_url: str

    def to_dict(self) -> dict:
        return asdict(self)


def _resolve_tasks(db: Session, references: list[str]) -> list[Task]:
    tasks: list[Task] = []
    for reference in dict.fromkeys(references):
        statement = select(Task)
        if reference.isdigit():
            statement = statement.where(Task.id == int(reference))
        else:
            statement = statement.where(Task.slug == reference)
        task = db.execute(statement).scalar_one_or_none()
        if task is None:
            raise ValueError(f"Task not found: {reference}")
        tasks.append(task)
    return tasks


def _resolve_metrics(db: Session, names: list[str]) -> list[Metric]:
    metrics: list[Metric] = []
    for name in dict.fromkeys(names):
        metric = db.execute(
            select(Metric).where(Metric.name == name)
        ).scalar_one_or_none()
        if metric is None:
            raise ValueError(f"Metric not found: {name}")
        metrics.append(metric)
    return metrics


def add_benchmark(
    db: Session,
    *,
    name: str,
    description: str,
    task_references: list[str],
    metric_names: list[str],
    source_paper: str,
    full_name: str | None = None,
    url: str | None = None,
    hf_url: str | None = None,
    homepage: str | None = None,
    supports_harness: bool = False,
) -> BenchmarkAddResult:
    """Create or reuse a benchmark and ensure its core leaderboard links."""
    normalized_name = name.strip()
    normalized_description = description.strip()
    slug = slugify(normalized_name)
    if not slug:
        raise ValueError("Benchmark name must contain a letter or number")
    if not normalized_description:
        raise ValueError("Benchmark description must not be empty")

    paper, route_reference = resolve_paper(db, source_paper)
    tasks = _resolve_tasks(db, task_references)
    metrics = _resolve_metrics(db, metric_names)
    source_url = f"https://paperswithcode.co/paper/{route_reference}"

    try:
        benchmark = db.execute(
            select(Dataset).where(Dataset.slug == slug)
        ).scalar_one_or_none()
        status = "existing"
        if benchmark is None:
            benchmark = Dataset(
                name=normalized_name,
                slug=slug,
                full_name=full_name,
                description=normalized_description,
                url=url,
                hf_url=hf_url,
                homepage=homepage,
            )
            db.add(benchmark)
            db.flush()
            status = "created"

        benchmark.description = normalized_description
        if full_name is not None:
            benchmark.full_name = full_name
        if url is not None:
            benchmark.url = url
        if hf_url is not None:
            benchmark.hf_url = hf_url
        if homepage is not None:
            benchmark.homepage = homepage

        benchmark.introducing_paper_id = paper.id
        benchmark.introducing_paper_title = paper.title
        benchmark.paper_url = source_url

        for task in tasks:
            paper_task = db.get(PaperTask, (paper.id, task.id))
            if paper_task is None:
                db.add(PaperTask(paper_id=paper.id, task_id=task.id, source="manual"))
            else:
                paper_task.source = "manual"

            task_dataset = db.get(TaskDataset, (task.id, benchmark.id))
            if task_dataset is None:
                db.add(
                    TaskDataset(
                        task_id=task.id,
                        dataset_id=benchmark.id,
                        supports_harness=supports_harness,
                    )
                )
            elif supports_harness:
                task_dataset.supports_harness = True

            for metric in metrics:
                key = (task.id, benchmark.id, metric.id)
                if db.get(TaskDatasetMetric, key) is None:
                    db.add(
                        TaskDatasetMetric(
                            task_id=task.id,
                            dataset_id=benchmark.id,
                            metric_id=metric.id,
                        )
                    )

        db.commit()
        return BenchmarkAddResult(
            status=status,
            id=benchmark.id,
            name=benchmark.name,
            slug=benchmark.slug,
            tasks=[task.slug for task in tasks],
            metrics=[metric.name for metric in metrics],
            source_url=source_url,
        )
    except Exception:
        db.rollback()
        raise
