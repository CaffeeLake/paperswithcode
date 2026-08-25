"""Create MMEB-v2/v3 and directional TextCaps retrieval leaderboards."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset, Metric, Paper, Task

logger = logging.getLogger(__name__)

MMEB_SPACE_URL = "https://huggingface.co/spaces/TIGER-Lab/MMEB-Leaderboard"
VLM2VEC_REPO_URL = "https://github.com/TIGER-AI-Lab/VLM2Vec"


def _paper(session: Session, arxiv_id: str) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Missing source paper arXiv:{arxiv_id}")
    return paper


def _task(session: Session, slug: str) -> Task:
    task = session.query(Task).filter(Task.slug == slug).one_or_none()
    if task is None:
        raise RuntimeError(f"Missing task {slug!r}")
    return task


def _metric(session: Session, name: str) -> Metric:
    metric = session.query(Metric).filter(Metric.name == name).one_or_none()
    if metric is None:
        metric = Metric(name=name, direction="higher_is_better")
        session.add(metric)
        session.flush()
    return metric


def _ensure_mmeb(
    session: Session, *, version: str, arxiv_id: str, description: str
) -> Dataset:
    paper = _paper(session, arxiv_id)
    slug = f"mmeb-{version}"
    name = f"MMEB-{version}"
    dataset = session.query(Dataset).filter(Dataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = Dataset(name=name, slug=slug)
        session.add(dataset)
    dataset.name = name
    dataset.full_name = f"Massive Multimodal Embedding Benchmark ({version.upper()})"
    dataset.description = description
    dataset.short_description = description
    dataset.url = VLM2VEC_REPO_URL
    dataset.homepage = MMEB_SPACE_URL
    dataset.hf_url = (
        "https://huggingface.co/datasets/TIGER-Lab/MMEB-V2" if version == "v2" else None
    )
    dataset.paper_url = f"https://paperswithcode.co/paper/{arxiv_id}"
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_date = paper.date_published
    dataset.introduced_year = paper.date_published.year
    dataset.modalities = ["Images", "Videos", "Text", "Visual Documents"]
    if version == "v3":
        dataset.modalities.append("Audio")
    dataset.languages = ["English"]
    session.flush()
    return dataset


def _ensure_textcaps_direction(
    session: Session, *, direction: str, name: str, description: str
) -> Dataset:
    source = session.query(Dataset).filter(Dataset.slug == "textcaps").one_or_none()
    if source is None or source.introducing_paper_id is None:
        raise RuntimeError("TextCaps source benchmark is not configured")
    slug = f"textcaps-{direction}"
    dataset = session.query(Dataset).filter(Dataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = Dataset(name=name, slug=slug)
        session.add(dataset)
    dataset.name = name
    dataset.full_name = name
    dataset.description = description
    dataset.short_description = description
    dataset.homepage = source.homepage
    dataset.paper_url = source.paper_url
    dataset.introducing_paper_id = source.introducing_paper_id
    dataset.introducing_paper_title = source.introducing_paper_title
    dataset.introduced_date = source.introduced_date
    dataset.introduced_year = source.introduced_year
    dataset.modalities = source.modalities
    dataset.languages = source.languages
    dataset.parent_dataset_id = source.id
    dataset.variant_type = "variant"
    session.flush()
    return dataset


def _link(
    session: Session, *, paper_id: int, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT DO NOTHING
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET supports_harness = FALSE
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id, "metric_id": metric_id},
    )


def configure_benchmarks(session: Session) -> dict[str, Dataset]:
    """Create or update all four benchmark definitions in one transaction."""
    embedding_task = _task(session, "embedding-models")
    image_task = _task(session, "image-understanding")
    mmeb_v2 = _ensure_mmeb(
        session,
        version="v2",
        arxiv_id="2507.04590",
        description=(
            "Overall MMEB-v2 evaluation across image, video, and visual-document "
            "embedding tasks using the official benchmark aggregate."
        ),
    )
    mmeb_v3 = _ensure_mmeb(
        session,
        version="v3",
        arxiv_id="2604.23321",
        description=(
            "Overall MMEB-v3 evaluation across image, video, visual-document, "
            "text, audio, and agent-oriented embedding tasks."
        ),
    )
    textcaps_t2i = _ensure_textcaps_direction(
        session,
        direction="text-to-image",
        name="TextCaps Text-to-Image Retrieval",
        description=(
            "Text-to-image retrieval on TextCaps, querying images with text and "
            "ranking by Recall@1."
        ),
    )
    textcaps_i2t = _ensure_textcaps_direction(
        session,
        direction="image-to-text",
        name="TextCaps Image-to-Text Retrieval",
        description=(
            "Image-to-text retrieval on TextCaps, querying captions with images "
            "and ranking by Recall@1."
        ),
    )

    for dataset, arxiv_id, metric_name in (
        (mmeb_v2, "2507.04590", "MMEB-v2 Score"),
        (mmeb_v3, "2604.23321", "MMEB-v3 Score"),
    ):
        metric = _metric(session, metric_name)
        _link(
            session,
            paper_id=_paper(session, arxiv_id).id,
            task_id=embedding_task.id,
            dataset_id=dataset.id,
            metric_id=metric.id,
        )
    recall = _metric(session, "R@1")
    textcaps_paper_id = int(textcaps_t2i.introducing_paper_id)
    for dataset in (textcaps_t2i, textcaps_i2t):
        _link(
            session,
            paper_id=textcaps_paper_id,
            task_id=image_task.id,
            dataset_id=dataset.id,
            metric_id=recall.id,
        )
    return {
        "mmeb-v2": mmeb_v2,
        "mmeb-v3": mmeb_v3,
        "textcaps-text-to-image": textcaps_t2i,
        "textcaps-image-to-text": textcaps_i2t,
    }


def main() -> None:
    with db_manager.session_local() as session:
        benchmarks = configure_benchmarks(session)
        session.commit()
        logger.info(
            "Configured benchmark ids: MMEB-v2=%s MMEB-v3=%s TextCaps-t2i=%s "
            "TextCaps-i2t=%s",
            benchmarks["mmeb-v2"].id,
            benchmarks["mmeb-v3"].id,
            benchmarks["textcaps-text-to-image"].id,
            benchmarks["textcaps-image-to-text"].id,
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
