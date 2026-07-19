#!/usr/bin/env python3
"""Import the original PWC-Net paper and its paper-native evaluations."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "1709.02371"
TASK_ID = 323
NUM_PARAMETERS = 8_750_000

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "PWC-Net-ft",
        "metrics": {"Average End-Point Error": 3.86},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 1, MPI Sintel Clean official hidden test. PWC-Net is "
            "pretrained sequentially on FlyingChairs and FlyingThings3D, then "
            "PWC-Net-ft is fine-tuned throughout on both the Clean and Final "
            "passes of the Sintel training set. This is the paper's best "
            "eligible introduced variant on the Clean hidden test."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "PWC-Net-ft-final",
        "metrics": {"Average End-Point Error": 5.04},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 1, MPI Sintel Final official hidden test. PWC-Net is "
            "pretrained sequentially on FlyingChairs and FlyingThings3D. The "
            "paper's PWC-Net-ft-final schedule fine-tunes on both Sintel passes "
            "initially, then gives the Final pass exclusive weight during the "
            "second half; it is the paper's best eligible introduced variant "
            "on the Final hidden test."
        ),
    },
    {
        "dataset_id": 1373,
        "model_name": "PWC-Net-ft",
        "metrics": {"Average End-Point Error": 1.7, "Out-Noc": 4.22},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 3, KITTI 2012 official hidden test. PWC-Net is "
            "pretrained on FlyingChairs and FlyingThings3D and fine-tuned on "
            "the KITTI training set. The paper labels the configured Out-Noc "
            "quantity as Fl-Noc: the percentage of erroneous non-occluded "
            "pixels; Average End-Point Error is in pixels."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "PWC-Net-ft",
        "metrics": {"Fl-all": 9.60},
        "best_metric": "Fl-all",
        "methodology": (
            "Paper Table 3, KITTI 2015 official hidden test. PWC-Net is "
            "pretrained on FlyingChairs and FlyingThings3D and fine-tuned on "
            "the KITTI training set. Fl-all is the percentage of erroneous "
            "pixels over all valid test pixels."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "PWC-Net-ft",
        "metrics": {"EPE": 2.16, "F1-all": 9.80},
        "best_metric": "EPE",
        "methodology": (
            "Paper Table 3, KITTI 2015 training-set evaluation (the values in "
            "parentheses denote the set used for fine-tuning). PWC-Net is "
            "pretrained on FlyingChairs and FlyingThings3D and fine-tuned on "
            "KITTI. EPE is in pixels and the paper's Fl-all percentage is "
            "stored under this leaderboard's configured F1-all label."
        ),
    },
]


async def ensure_paper(session) -> tuple[Paper, bool]:
    metadata = await ArxivService().get_paper_metadata(ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata: {metadata.error_message}")
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == ARXIV_ID, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        ensure_authors(session, existing.id, metadata.authors)
        return existing, False

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
    if paper_id is None:
        raise RuntimeError("PaperService did not create the missing paper")
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Could not reload created paper {paper_id}")
    ensure_authors(session, paper.id, metadata.authors)
    return paper, True


def ensure_authors(session, paper_id: int, names: list[str]) -> None:
    for order, name in enumerate(names, start=1):
        author = session.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            session.add(author)
            session.flush()
        exists = (
            session.query(PaperAuthor)
            .filter_by(paper_id=paper_id, author_id=author.id)
            .first()
        )
        if exists is None:
            session.add(
                PaperAuthor(
                    paper_id=paper_id,
                    author_id=author.id,
                    author_order=order,
                )
            )
    session.flush()


async def main() -> None:
    with db_manager.session_local() as session:
        paper, paper_created = await ensure_paper(session)
        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper.id, "task_id": TASK_ID},
        )
        session.commit()

        service = EvaluationService(session)
        results = []
        for row in ROWS:
            board = (
                session.execute(
                    text(
                        """
                    SELECT td.supports_harness,
                           array_agg(m.name ORDER BY m.name) AS metrics
                    FROM task_datasets td
                    JOIN task_dataset_metrics tdm
                      ON tdm.task_id = td.task_id
                     AND tdm.dataset_id = td.dataset_id
                    JOIN metrics m ON m.id = tdm.metric_id
                    WHERE td.task_id = :task_id AND td.dataset_id = :dataset_id
                    GROUP BY td.supports_harness
                    """
                    ),
                    {"task_id": TASK_ID, "dataset_id": row["dataset_id"]},
                )
                .mappings()
                .one()
            )
            if board["supports_harness"]:
                raise RuntimeError("Optical-flow board unexpectedly supports harness")
            if not set(row["metrics"]).issubset(set(board["metrics"])):
                raise RuntimeError(
                    f"Metric mismatch for dataset {row['dataset_id']}: {dict(board)}"
                )

            params = {
                "paper_id": paper.id,
                "task_id": TASK_ID,
                "dataset_id": row["dataset_id"],
                "model_name": row["model_name"],
                "best_metric": row["best_metric"],
            }
            existing_id = session.execute(
                text(
                    """
                    SELECT id FROM evaluations
                    WHERE paper_id = :paper_id AND task_id = :task_id
                      AND dataset_id = :dataset_id AND model_name = :model_name
                      AND harness IS NULL AND best_metric = :best_metric
                    ORDER BY id LIMIT 1
                    """
                ),
                params,
            ).scalar_one_or_none()
            source_url = f"paper:{paper.id}"
            if existing_id is None:
                evaluation = service.create_evaluation(
                    paper_id=paper.id,
                    task_id=TASK_ID,
                    dataset_id=row["dataset_id"],
                    model_name=row["model_name"],
                    methodology=row["methodology"],
                    metrics=row["metrics"],
                    best_metric=row["best_metric"],
                    harness=None,
                    source_url=source_url,
                    uses_additional_data=True,
                    is_open=True,
                    num_parameters=NUM_PARAMETERS,
                    hf_model_url=None,
                )
                evaluation_id = evaluation.id
                action = "created"
            else:
                service.update_evaluation(
                    existing_id,
                    model_name=row["model_name"],
                    methodology=row["methodology"],
                    metrics=row["metrics"],
                    best_metric=row["best_metric"],
                    uses_additional_data=True,
                    is_open=True,
                    harness=None,
                    harness_set=True,
                    source_url=source_url,
                    source_url_set=True,
                    num_parameters=NUM_PARAMETERS,
                    num_parameters_set=True,
                    hf_model_url=None,
                    hf_model_url_set=True,
                )
                evaluation_id = existing_id
                action = "updated"

            for metric in row["metrics"]:
                service.recalculate_ranks(
                    TASK_ID, row["dataset_id"], metric_name=metric
                )
            results.append((action, evaluation_id, row["dataset_id"]))

        print(f"paper_id={paper.id} created={paper_created} version={paper.version}")
        for result in results:
            print(result)


if __name__ == "__main__":
    asyncio.run(main())
