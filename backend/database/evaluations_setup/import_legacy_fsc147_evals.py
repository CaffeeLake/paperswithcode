#!/usr/bin/env python3
"""Backfill FSC-147 / FSCD-147 evals from legacy PwC evaluation-tables.json."""

from __future__ import annotations

import asyncio
import logging
from datetime import date

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)
from backend.services.paper_service import PaperService

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TASK_ID = 340
FSC147_SLUG = "fsc-147"
FSCD147_SLUG = "fscd-147"
SOURCE = "Legacy PwC evaluation-tables.json; object-counting-on-fsc147 / few-shot-object-counting-and-detection-on-fsc147"

EXTERNAL_PAPERS = {
    "save": {
        "source_url": "https://www.mdpi.com/2313-433X/11/2/52",
        "title": "SAVE: Self-Attention on Visual Embedding for Zero-Shot Generic Object Counting",
        "abstract": (
            "Proposes SAVE, a zero-shot generic object counting method using "
            "self-attention on visual embeddings for exemplar-free counting on FSC-147."
        ),
        "authors": ["Ahmed Zgaren", "Ngai-Man Cheung"],
        "date_published": date(2025, 2, 10),
        "github_repository_urls": ["https://github.com/AhmedZgaren/Save"],
    },
    "spdcn": {
        "source_url": "https://bmvc2022.mpi-inf.mpg.de/313/",
        "title": "Scale-Prior Deformable Convolution for Exemplar-Guided Class-Agnostic Counting",
        "abstract": (
            "Introduces SPDCN, a scale-prior deformable convolution approach for "
            "exemplar-guided class-agnostic counting evaluated on FSC-147."
        ),
        "authors": ["Yulin Li", "Hao Lu", "Minh Hoai"],
        "date_published": date(2022, 12, 21),
        "github_repository_urls": ["https://github.com/Elin24/SPDCN-CAC"],
    },
}

# (paper_key, model_name, dataset_slug, metric, score, note)
# paper_key is arxiv_id or external key
ROWS = [
    # FSC-147 — legacy main Object Counting board (counting-only methods)
    ("2407.04619", "CountGD", FSC147_SLUG, "MAE", "5.74", "FSC-147 test split"),
    ("2407.04619", "CountGD", FSC147_SLUG, "RMSE", "24.09", "FSC-147 test split"),
    ("2305.04440", "CACViT", FSC147_SLUG, "MAE", "9.13", "FSC-147 test split"),
    ("2305.04440", "CACViT", FSC147_SLUG, "RMSE", "48.96", "FSC-147 test split"),
    ("2405.11770", "SSD", FSC147_SLUG, "MAE", "9.58", "FSC-147 test split"),
    ("2405.11770", "SSD", FSC147_SLUG, "RMSE", "64.13", "FSC-147 test split"),
    ("2211.08217", "LOCA", FSC147_SLUG, "MAE", "10.79", "FSC-147 test split"),
    ("2211.08217", "LOCA", FSC147_SLUG, "RMSE", "56.97", "FSC-147 test split"),
    (
        "2311.16122",
        "SemAug-CounTR",
        FSC147_SLUG,
        "MAE",
        "11.32",
        "FSC-147 test split; uses additional synthetic data",
    ),
    (
        "2311.16122",
        "SemAug-CounTR",
        FSC147_SLUG,
        "RMSE",
        "77.50",
        "FSC-147 test split; uses additional synthetic data",
    ),
    ("2208.13721", "CounTR", FSC147_SLUG, "MAE", "11.95", "FSC-147 test split"),
    ("2208.13721", "CounTR", FSC147_SLUG, "RMSE", "91.23", "FSC-147 test split"),
    (
        "2311.16122",
        "SemAug-SAFECount",
        FSC147_SLUG,
        "MAE",
        "12.74",
        "FSC-147 test split; uses additional synthetic data",
    ),
    (
        "2311.16122",
        "SemAug-SAFECount",
        FSC147_SLUG,
        "RMSE",
        "89.90",
        "FSC-147 test split; uses additional synthetic data",
    ),
    ("spdcn", "SPDCN", FSC147_SLUG, "MAE", "13.51", "FSC-147 test split"),
    ("spdcn", "SPDCN", FSC147_SLUG, "RMSE", "96.80", "FSC-147 test split"),
    ("2409.12249", "GCA-SUN", FSC147_SLUG, "MAE", "14.00", "FSC-147 test split"),
    ("2409.12249", "GCA-SUN", FSC147_SLUG, "RMSE", "92.19", "FSC-147 test split"),
    ("2201.08959", "SAFECount", FSC147_SLUG, "MAE", "14.32", "FSC-147 test split"),
    ("2201.08959", "SAFECount", FSC147_SLUG, "RMSE", "85.54", "FSC-147 test split"),
    ("2203.08354", "BMNet+", FSC147_SLUG, "MAE", "14.62", "FSC-147 test split"),
    ("2203.08354", "BMNet+", FSC147_SLUG, "RMSE", "91.83", "FSC-147 test split"),
    ("2112.05993", "LaoNet", FSC147_SLUG, "MAE", "15.78", "FSC-147 test split"),
    ("2112.05993", "LaoNet", FSC147_SLUG, "RMSE", "97.15", "FSC-147 test split"),
    (
        "2306.01851",
        "CounTX",
        FSC147_SLUG,
        "MAE",
        "15.88",
        "FSC-147 test split; text-specified",
    ),
    (
        "2306.01851",
        "CounTX",
        FSC147_SLUG,
        "RMSE",
        "106.29",
        "FSC-147 test split; text-specified",
    ),
    ("2205.10203", "RCC", FSC147_SLUG, "MAE", "17.12", "FSC-147 test split"),
    ("2205.10203", "RCC", FSC147_SLUG, "RMSE", "104.53", "FSC-147 test split"),
    (
        "2403.05435",
        "OmniCount (zero-shot)",
        FSC147_SLUG,
        "MAE",
        "18.63",
        "FSC-147 test split; open-vocabulary without training",
    ),
    (
        "2403.05435",
        "OmniCount (zero-shot)",
        FSC147_SLUG,
        "RMSE",
        "112",
        "FSC-147 test split; open-vocabulary without training",
    ),
    ("2104.08391", "FamNet", FSC147_SLUG, "MAE", "22.08", "FSC-147 test split"),
    ("2104.08391", "FamNet", FSC147_SLUG, "RMSE", "99.54", "FSC-147 test split"),
    ("save", "SAVE", FSC147_SLUG, "MAE", "8.92", "FSC-147 test split; exemplar-free"),
    ("save", "SAVE", FSC147_SLUG, "RMSE", "80.39", "FSC-147 test split; exemplar-free"),
    # FSCD-147 — legacy Few-shot Object Counting and Detection board
    (
        "2207.10988",
        "Counting-DETR",
        FSCD147_SLUG,
        "MAE",
        "16.79",
        "FSCD-147 test split",
    ),
    (
        "2207.10988",
        "Counting-DETR",
        FSCD147_SLUG,
        "RMSE",
        "123.56",
        "FSCD-147 test split",
    ),
    ("2207.10988", "Counting-DETR", FSCD147_SLUG, "AP", "22.66", "FSCD-147 test split"),
    (
        "2207.10988",
        "Counting-DETR",
        FSCD147_SLUG,
        "AP50",
        "50.57",
        "FSCD-147 test split",
    ),
]


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_service = PaperService(session)
    paper_id = paper_service.add_paper(
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
    if not paper_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing
        raise RuntimeError(f"Failed to create paper row for {arxiv_id}")

    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Created paper {paper_id} but could not reload it")

    if metadata.authors:
        for order, author_name in enumerate(metadata.authors, start=1):
            author = session.query(Author).filter(Author.name == author_name).first()
            if not author:
                author = Author(name=author_name)
                session.add(author)
                session.flush()
            session.add(
                PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
            )
        session.flush()

    logger.info("Imported arXiv paper %s (id=%s)", arxiv_id, paper.id)
    return paper


def ensure_external_paper(session, key: str) -> Paper:
    spec = EXTERNAL_PAPERS[key]
    existing = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == spec["source_url"])
        .first()
    )
    if existing:
        return existing
    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["title"],
            abstract=spec["abstract"],
            authors=spec["authors"],
            date_published=spec["date_published"],
            github_repository_urls=spec["github_repository_urls"],
        )
    )
    logger.info("Imported external paper %s (id=%s)", key, result.paper.id)
    return result.paper


def paper_source_url(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://arxiv.org/abs/{paper.arxiv_id}"
    if paper.source_url:
        return paper.source_url
    return f"https://paperswithcode.co/paper/{paper.id}"


def link_paper_task(session, paper_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"p": paper_id, "t": TASK_ID},
    )


def resolve_dataset_ids(session) -> dict[str, int]:
    out: dict[str, int] = {}
    for slug in (FSC147_SLUG, FSCD147_SLUG):
        row = session.execute(
            text("SELECT id FROM datasets WHERE slug = :s"), {"s": slug}
        ).first()
        if not row:
            raise RuntimeError(f"Missing dataset slug={slug!r}")
        out[slug] = int(row[0])
    return out


async def resolve_paper(session, key: str) -> Paper:
    if key in EXTERNAL_PAPERS:
        return ensure_external_paper(session, key)
    return await ensure_arxiv_paper(session, key)


async def main() -> None:
    session = db_manager.session_local()
    created = skipped = 0
    paper_cache: dict[str, Paper] = {}
    try:
        dataset_ids = resolve_dataset_ids(session)
        svc = EvaluationService(session)

        for paper_key, model_name, dataset_slug, metric, score, note in ROWS:
            if paper_key not in paper_cache:
                paper = await resolve_paper(session, paper_key)
                paper_cache[paper_key] = paper
                link_paper_task(session, paper.id)
            else:
                paper = paper_cache[paper_key]

            dataset_id = dataset_ids[dataset_slug]
            params = {
                "paper_id": paper.id,
                "task_id": TASK_ID,
                "dataset_id": dataset_id,
                "model_name": model_name,
                "best_metric": metric,
            }
            existing = session.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id=:paper_id AND task_id=:task_id AND dataset_id=:dataset_id
                      AND model_name=:model_name
                      AND COALESCE(harness, '') = ''
                      AND best_metric=:best_metric
                    """
                ),
                params,
            ).first()
            if existing:
                skipped += 1
                continue

            svc.create_evaluation(
                paper_id=paper.id,
                task_id=TASK_ID,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=f"{note}. {SOURCE}.",
                metrics={metric: score},
                best_metric=metric,
                source_url=paper_source_url(paper),
                is_open=True,
            )
            created += 1
            logger.info(
                "Created %s %s on %s for paper_id=%s",
                model_name,
                metric,
                dataset_slug,
                paper.id,
            )

        for dataset_id in dataset_ids.values():
            for metric in ("MAE", "RMSE", "AP", "AP50"):
                svc.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)

        session.commit()
        print(f"created={created} skipped={skipped}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
