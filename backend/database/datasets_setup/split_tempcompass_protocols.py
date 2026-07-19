"""Split TempCompass overall and multi-choice evaluation protocols.

TempCompass publishes four task formats. Some papers report the official
full-benchmark aggregate, while others report only multi-choice QA accuracy.
Those results are not comparable and must live on separate leaderboards.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/split_tempcompass_protocols.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

TASK_ID = 9
PAPER_ID = 28240
METRIC_NAME = "Accuracy"
NATIVE_PAPER_URL = "https://paperswithcode.co/paper/2403.00476"

OVERALL_DATASET_ID = 311
OVERALL_NAME = "TempCompass (Overall)"
OVERALL_SLUG = "tempcompass"
OVERALL_DESCRIPTION = (
    "TempCompass (Overall) evaluates temporal perception across all four official "
    "task formats: multi-choice QA, yes/no QA, caption matching, and caption "
    "generation. Results use the benchmark's full 'Avg. All' accuracy, aggregated "
    "over the public test examples across the five temporal dimensions."
)

MCQ_NAME = "TempCompass (MCQ)"
MCQ_SLUG = "tempcompass-mcq"
MCQ_DESCRIPTION = (
    "TempCompass (MCQ) evaluates the benchmark's multi-choice QA task format on "
    "the public test examples. Accuracy is aggregated across action, direction, "
    "speed, event order, and attribute change. It excludes yes/no QA, caption "
    "matching, and caption generation."
)

MCQ_ROWS = {
    675: (
        "Table 8; TempCompass multi-choice QA accuracy, aggregated across the five "
        "temporal dimensions. V-JEPA 2 ViT-g/384px with Llama 3.1 8B."
    ),
    15430: (
        "Table 2 test multi-choice QA (MCQ) format; official TempCompass Accuracy; "
        "paper offline video evaluation configuration (Table 10)."
    ),
    7104: (
        "Paper video benchmark table; source label TempCompass-MC, i.e. the "
        "multi-choice QA format. LLaVA-OneVision-2-8B evaluation."
    ),
    9515: (
        "Table 2 test multi-choice QA (MCQ) format; greedy decoding with up to 384 "
        "frames at 2 fps (paper section 4.1)."
    ),
    7845: (
        "Table 4; TempCompass (MCQ) accuracy for PLM-8B, reproduced using the "
        "official evaluation code."
    ),
}

OVERALL_ROWS = {
    9214: (
        "Table 3; TempCompass overall 'Avg. All' accuracy across multi-choice QA, "
        "yes/no QA, caption matching, and caption generation. Thinking mode."
    ),
    5032: (
        "Table 8, TempCompass Avg.; full benchmark accuracy across multi-choice QA, "
        "yes/no QA, caption matching, and caption generation."
    ),
    5597: (
        "Table 8, TempCompass (TC); full benchmark aggregate across multi-choice "
        "QA, yes/no QA, caption matching, and caption generation."
    ),
    9238: (
        "Public benchmark table in arXiv:2507.01949; TempCompass overall aggregate "
        "across all four task formats. Thinking mode."
    ),
    1224: (
        "Table 8; TempCompass overall aggregate across multi-choice QA, yes/no QA, "
        "caption matching, and caption generation for VideoLLaMA3-7B."
    ),
    9631: (
        "Table 1; full TempCompass evaluation via VLMEvalKit, aggregated across "
        "multi-choice QA, yes/no QA, caption matching, and caption generation."
    ),
}


def _metric_id(session) -> int:
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": METRIC_NAME}
    ).scalar_one()


def _ensure_mcq_dataset(session, overall: DBDataset) -> DBDataset:
    mcq = session.query(DBDataset).filter(DBDataset.slug == MCQ_SLUG).one_or_none()
    if mcq is None:
        mcq = DBDataset(slug=MCQ_SLUG, name=MCQ_NAME)
        session.add(mcq)
        session.flush()
        logger.info("Created %s (id=%s)", MCQ_NAME, mcq.id)

    mcq.name = MCQ_NAME
    mcq.full_name = MCQ_NAME
    mcq.description = MCQ_DESCRIPTION
    mcq.url = overall.url
    mcq.hf_url = overall.hf_url
    mcq.homepage = overall.homepage
    mcq.parent_dataset_id = overall.id
    mcq.variant_type = "subset"
    mcq.split_name = "MCQ"
    mcq.introducing_paper_id = PAPER_ID
    mcq.introducing_paper_title = overall.introducing_paper_title
    mcq.introduced_year = overall.introduced_year
    mcq.paper_url = NATIVE_PAPER_URL
    return mcq


def _ensure_links(session, dataset_id: int, metric_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id, supports_harness) "
            "VALUES (:task_id, :dataset_id, FALSE) "
            "ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"task_id": TASK_ID, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:task_id, :dataset_id, :metric_id) "
            "ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"task_id": TASK_ID, "dataset_id": dataset_id, "metric_id": metric_id},
    )


def _verify_expected_rows(session, mcq_dataset_id: int) -> None:
    rows = session.execute(
        text(
            "SELECT id FROM evaluations "
            "WHERE task_id = :task_id AND dataset_id IN (:overall_id, :mcq_id)"
        ),
        {
            "task_id": TASK_ID,
            "overall_id": OVERALL_DATASET_ID,
            "mcq_id": mcq_dataset_id,
        },
    ).scalars()
    found = set(rows)
    expected = set(MCQ_ROWS) | set(OVERALL_ROWS)
    if found != expected:
        raise RuntimeError(
            "TempCompass rows changed since verification: "
            f"missing={sorted(expected - found)}, unexpected={sorted(found - expected)}"
        )


def main() -> None:
    session = db_manager.session_local()
    try:
        overall = (
            session.query(DBDataset).filter(DBDataset.id == OVERALL_DATASET_ID).one()
        )
        overall.name = OVERALL_NAME
        overall.full_name = OVERALL_NAME
        overall.slug = OVERALL_SLUG
        overall.description = OVERALL_DESCRIPTION
        overall.introducing_paper_id = PAPER_ID
        overall.paper_url = NATIVE_PAPER_URL

        mcq = _ensure_mcq_dataset(session, overall)
        metric_id = _metric_id(session)
        _ensure_links(session, overall.id, metric_id)
        _ensure_links(session, mcq.id, metric_id)
        session.execute(
            text(
                "INSERT INTO paper_tasks (paper_id, task_id, source) "
                "VALUES (:paper_id, :task_id, 'manual') "
                "ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'"
            ),
            {"paper_id": PAPER_ID, "task_id": TASK_ID},
        )
        session.commit()

        _verify_expected_rows(session, mcq.id)
        service = EvaluationService(session)
        for evaluation_id, methodology in OVERALL_ROWS.items():
            service.update_evaluation(
                evaluation_id=evaluation_id,
                dataset_id=overall.id,
                methodology=methodology,
            )
        for evaluation_id, methodology in MCQ_ROWS.items():
            service.update_evaluation(
                evaluation_id=evaluation_id,
                dataset_id=mcq.id,
                methodology=methodology,
            )

        service.recalculate_ranks(TASK_ID, overall.id, metric_name=METRIC_NAME)
        service.recalculate_ranks(TASK_ID, mcq.id, metric_name=METRIC_NAME)
        session.commit()

        counts = session.execute(
            text(
                "SELECT dataset_id, count(*) FROM evaluations "
                "WHERE task_id = :task_id AND dataset_id IN (:overall_id, :mcq_id) "
                "GROUP BY dataset_id ORDER BY dataset_id"
            ),
            {
                "task_id": TASK_ID,
                "overall_id": overall.id,
                "mcq_id": mcq.id,
            },
        ).all()
        logger.info(
            "Split complete: overall=%s, mcq=%s, counts=%s",
            overall.id,
            mcq.id,
            counts,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
