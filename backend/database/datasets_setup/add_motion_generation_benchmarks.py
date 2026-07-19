"""Add tier-1 text-to-motion benchmarks to Motion Generation.

Benchmarks:
- HumanML3D (Guo et al., CVPR 2022 — external paper, no arXiv)
- KIT Motion-Language (Plappert et al., arXiv:1607.03827)

Leaderboard metrics follow legacy Papers With Code Motion Synthesis:
FID, R Precision Top3, Diversity, Multimodality.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/add_motion_generation_benchmarks.py
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset, Paper, Task as DBTask
from backend.services.arxiv_service import ArxivService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_SLUG = "motion-generation"

HUMANML3D_SOURCE_URL = (
    "http://openaccess.thecvf.com/content/CVPR2022/html/"
    "Guo_Generating_Diverse_and_Natural_3D_Human_Motions_From_Text_CVPR_2022_paper.html"
)
HUMANML3D_TITLE = "Generating Diverse and Natural 3D Human Motions From Text"
HUMANML3D_DATE = date(2022, 6, 1)
HUMANML3D_AUTHORS = [
    "Chuan Guo",
    "Shihao Zou",
    "Xinxin Zuo",
    "Sen Wang",
    "Wei Ji",
    "Xingyu Li",
    "Li Cheng",
]
HUMANML3D_ABSTRACT = (
    "Automated generation of 3D human motions from text is a challenging problem. "
    "The generated motions are expected to be sufficiently diverse to explore the "
    "text-grounded motion space, and more importantly, accurately depicting the "
    "content in prescribed text descriptions. We tackle this with text2length "
    "sampling and text2motion generation, and introduce HumanML3D — a large-scale "
    "dataset of 14,616 motion clips with 44,970 text descriptions for benchmarking "
    "text-to-motion generation."
)

METRIC_SPECS = [
    {
        "name": "R Precision Top3",
        "direction": "higher_is_better",
        "full_name": "R Precision @ Top 3",
        "scale": "0-1",
        "description": (
            "Retrieval precision at top 3: fraction of generated motions whose "
            "nearest text match in the batch is the ground-truth caption."
        ),
    },
    {
        "name": "Diversity",
        "direction": "higher_is_better",
        "full_name": "Motion Diversity",
        "scale": "unbounded",
        "description": (
            "Average pairwise distance among generated motion features for a fixed "
            "set of text prompts (higher = more diverse samples)."
        ),
    },
    {
        "name": "Multimodality",
        "direction": "higher_is_better",
        "full_name": "Multimodality",
        "scale": "unbounded",
        "description": (
            "Average pairwise distance among multiple generations per text prompt "
            "(higher = more multimodal / varied outputs per caption)."
        ),
    },
]

BENCHMARKS = [
    {
        "name": "HumanML3D",
        "slug": "humanml3d",
        "full_name": "HumanML3D",
        "description": (
            "HumanML3D is a 3D human motion-language dataset built from HumanAct12 "
            "and AMASS with 14,616 motion clips and 44,970 crowd-sourced text "
            "descriptions. It is the primary benchmark for text-to-motion generation."
        ),
        "short_description": (
            "Large-scale 3D human motion-language dataset (14.6K motions, 45K captions)."
        ),
        "homepage": "https://github.com/EricGuo5513/HumanML3D",
        "url": "https://github.com/EricGuo5513/HumanML3D",
        "introduced_year": 2022,
        "source_kind": "external",
        "github": "https://github.com/EricGuo5513/HumanML3D",
    },
    {
        "name": "KIT Motion-Language",
        "slug": "kit-motion-language",
        "full_name": "KIT Motion-Language Dataset",
        "description": (
            "The KIT Motion-Language dataset links KIT whole-body mocap sequences "
            "with natural-language annotations gathered via a crowd-sourced Motion "
            "Annotation Tool. The processed text-to-motion split used in recent "
            "papers contains 3,911 motions and 6,278 descriptions."
        ),
        "short_description": (
            "KIT whole-body mocap with natural-language annotations (~3.9K motions)."
        ),
        "homepage": "https://motion-annotation.humanoids.kit.edu/dataset/",
        "url": "https://motion-annotation.humanoids.kit.edu/dataset/",
        "introduced_year": 2016,
        "source_kind": "arxiv",
        "source_arxiv": "1607.03827",
    },
]

METRIC_NAMES = ["FID", "R Precision Top3", "Diversity", "Multimodality"]


async def ensure_arxiv_paper(session: Session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata for {arxiv_id}")

    paper_id = PaperService(session).add_paper(
        {
            "arxiv_id": metadata.arxiv_id,
            "title": metadata.title,
            "abstract": metadata.abstract,
            "version": metadata.version,
            "date_published": metadata.published.date() if metadata.published else None,
            "primary_category": metadata.primary_category,
            "all_categories": metadata.categories,
            "is_latest_version": True,
        }
    )
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Failed to load newly created paper {paper_id}")
    logger.info("Imported paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def ensure_humanml3d_source_paper(session: Session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == HUMANML3D_SOURCE_URL)
        .one_or_none()
    )
    if paper is not None:
        logger.info("Reusing HumanML3D source paper id=%s", paper.id)
        return paper

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=HUMANML3D_SOURCE_URL,
            title=HUMANML3D_TITLE,
            abstract=HUMANML3D_ABSTRACT,
            authors=HUMANML3D_AUTHORS,
            date_published=HUMANML3D_DATE,
            github_repository_urls=["https://github.com/EricGuo5513/HumanML3D"],
        )
    )
    paper = session.query(Paper).filter(Paper.id == int(result.paper.id)).one()
    logger.info("Created HumanML3D source paper id=%s", paper.id)
    return paper


def paper_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://paperswithcode.co/paper/{paper.arxiv_id}"
    return f"https://paperswithcode.co/paper/{paper.id}"


def get_task(session: Session) -> DBTask:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task slug={TASK_SLUG!r} not found")
    return task


def ensure_metric(session: Session, spec: dict) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": spec["name"]}
    ).fetchone()
    if row:
        return int(row[0])

    metric_id = session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, full_name, scale, description)
            VALUES (:name, :direction, :full_name, :scale, :description)
            RETURNING id
            """
        ),
        spec,
    ).scalar_one()
    logger.info("Created metric %r (id=%s)", spec["name"], metric_id)
    return int(metric_id)


def metric_id(session: Session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": name}
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Metric {name!r} not found")
    return int(row[0])


def ensure_dataset(session: Session, spec: dict, source_paper: Paper) -> DBDataset:
    native_paper_url = paper_url(source_paper)
    dataset = (
        session.query(DBDataset).filter(DBDataset.slug == spec["slug"]).one_or_none()
    )
    if dataset is None:
        dataset = DBDataset(
            name=spec["name"],
            slug=spec["slug"],
            full_name=spec["full_name"],
            description=spec["description"],
            short_description=spec["short_description"],
            url=spec["url"],
            homepage=spec["homepage"],
            paper_url=native_paper_url,
            introducing_paper_id=source_paper.id,
            introducing_paper_title=source_paper.title,
            introduced_year=spec["introduced_year"],
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
    else:
        dataset.full_name = spec["full_name"]
        dataset.description = spec["description"]
        dataset.short_description = spec["short_description"]
        dataset.url = spec["url"]
        dataset.homepage = spec["homepage"]
        dataset.paper_url = native_paper_url
        dataset.introducing_paper_id = source_paper.id
        dataset.introducing_paper_title = source_paper.title
        dataset.introduced_year = dataset.introduced_year or spec["introduced_year"]
        session.flush()
        logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def link_task_dataset(session: Session, task_id: int, dataset_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:task_id, :dataset_id, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"task_id": task_id, "dataset_id": dataset_id},
    )


def link_metric(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
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


def tag_source_paper(session: Session, paper_id: int, task_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    )


async def main() -> None:
    with db_manager.session_local() as session:
        task = get_task(session)

        for spec in METRIC_SPECS:
            ensure_metric(session, spec)
        metric_ids = {name: metric_id(session, name) for name in METRIC_NAMES}

        tagged_papers: set[int] = set()

        for spec in BENCHMARKS:
            if spec["source_kind"] == "external":
                source_paper = ensure_humanml3d_source_paper(session)
            else:
                source_paper = await ensure_arxiv_paper(session, spec["source_arxiv"])

            dataset = ensure_dataset(session, spec, source_paper)
            link_task_dataset(session, task.id, dataset.id)
            for metric_name in METRIC_NAMES:
                link_metric(session, task.id, dataset.id, metric_ids[metric_name])

            if source_paper.id not in tagged_papers:
                tag_source_paper(session, source_paper.id, task.id)
                tagged_papers.add(source_paper.id)

            logger.info(
                "%s ready: https://paperswithcode.co/benchmark/%s metrics=%s source=%s",
                spec["name"],
                spec["slug"],
                METRIC_NAMES,
                paper_url(source_paper),
            )

        session.commit()


if __name__ == "__main__":
    asyncio.run(main())
