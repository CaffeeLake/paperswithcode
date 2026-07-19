#!/usr/bin/env python3
"""Import MaskFlownet's paper-native optical-flow evaluations."""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


ARXIV_ID = "2003.10955"
TASK_ID = 323

ROWS = [
    {
        "dataset_id": 1366,
        "model_name": "MaskFlownet",
        "metrics": {"Average End-Point Error": 2.52},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 1, MPI Sintel Clean official hidden test. The "
            "two-stage MaskFlownet is trained sequentially on FlyingChairs and "
            "FlyingThings3D, then fine-tuned with a mixed batch of Sintel "
            "training data, KITTI 2015, and HD1K using the paper's longer "
            "PWC-Net+-style cyclic schedule. This is the best paper-introduced "
            "variant on this board."
        ),
    },
    {
        "dataset_id": 1367,
        "model_name": "MaskFlownet",
        "metrics": {"Average End-Point Error": 4.17},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 1, MPI Sintel Final official hidden test. The "
            "two-stage MaskFlownet is trained sequentially on FlyingChairs and "
            "FlyingThings3D, then fine-tuned with a mixed batch of Sintel "
            "training data, KITTI 2015, and HD1K using the paper's longer "
            "PWC-Net+-style cyclic schedule. This is the best paper-introduced "
            "variant on this board."
        ),
    },
    {
        "dataset_id": 1373,
        "model_name": "MaskFlownet",
        "metrics": {"Average End-Point Error": 1.1},
        "best_metric": "Average End-Point Error",
        "methodology": (
            "Paper Table 1, KITTI 2012 official hidden test. For KITTI "
            "submission, the Sintel-tuned two-stage MaskFlownet is further "
            "fine-tuned on the combined KITTI 2012 and KITTI 2015 training "
            "sets, with inputs resized to 1280x576 before augmentation and "
            "cropping. The paper does not report Out-Noc for this row."
        ),
    },
    {
        "dataset_id": 1370,
        "model_name": "MaskFlownet",
        "metrics": {"Fl-all": 6.11},
        "best_metric": "Fl-all",
        "methodology": (
            "Paper Table 1, KITTI 2015 official hidden test. For KITTI "
            "submission, the Sintel-tuned two-stage MaskFlownet is further "
            "fine-tuned on the combined KITTI 2012 and KITTI 2015 training "
            "sets, with inputs resized to 1280x576 before augmentation and "
            "cropping. Fl-all is a percentage over all valid test pixels."
        ),
    },
    {
        "dataset_id": 1375,
        "model_name": "MaskFlownet (zero-shot)",
        "metrics": {"F1-all": 23.14},
        "best_metric": "F1-all",
        "methodology": (
            "Paper Table 1, KITTI 2015 training-set cross-dataset evaluation. "
            "Per the table caption, training columns include only checkpoints "
            "that have not trained on the corresponding target training set; "
            "this is therefore the pre-KITTI-fine-tuning MaskFlownet result. "
            "The paper's Fl-all percentage is stored under this leaderboard's "
            "configured F1-all label. EPE is not reported for this setup."
        ),
    },
]


def ensure_authors(session, paper_id: int, names: list[str]) -> None:
    for order, name in enumerate(names, start=1):
        author = session.query(Author).filter(Author.name == name).first()
        if author is None:
            author = Author(name=name)
            session.add(author)
            session.flush()
        association = (
            session.query(PaperAuthor)
            .filter_by(paper_id=paper_id, author_id=author.id)
            .first()
        )
        if association is None:
            session.add(
                PaperAuthor(
                    paper_id=paper_id,
                    author_id=author.id,
                    author_order=order,
                )
            )
    session.flush()


async def ensure_paper(session) -> tuple[Paper, bool]:
    metadata = await ArxivService().get_paper_metadata(ARXIV_ID)
    if not metadata.success:
        raise RuntimeError(f"Failed to fetch arXiv metadata: {metadata.error_message}")
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == ARXIV_ID, Paper.is_latest_version.is_(True))
        .first()
    )
    created = False
    if paper is None:
        paper_id = PaperService(session).add_paper(
            {
                "arxiv_id": metadata.arxiv_id,
                "title": metadata.title,
                "abstract": metadata.abstract,
                "version": metadata.version,
                "date_published": metadata.published.date()
                if metadata.published
                else None,
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
        created = True
    ensure_authors(session, paper.id, metadata.authors)
    return paper, created


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
                    num_parameters=None,
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
                    num_parameters=None,
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
