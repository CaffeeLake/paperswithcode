"""Import ParseBench comparison-table rows as external evaluations on model papers.

Scores come from ParseBench (arxiv 2604.08538) Table 1 and are attached to each
evaluated model's introducing paper with external=true.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/evaluations_setup/import_parsebench_external_evals.py
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Evaluation as DBEvaluation, Paper, Task as DBTask
from backend.services.evaluation_service import EvaluationService
from backend.services.external_resource_service import (
    ExternalResourceInput,
    ExternalResourceService,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PARSEBENCH_SOURCE_URL = "https://paperswithcode.co/paper/2604.08538"
TASK_SLUG = "document-understanding"
DATASET_SLUG = "parsebench"
BEST_METRIC = "Accuracy"

CLOSED_MODELS = {
    "Gemini 3.1 Pro",
    "GPT-5.5",
    "Mistral OCR 4",
    "Mistral OCR 4 (Annotation)",
}


@dataclass(frozen=True)
class ParseBenchRow:
    model_name: str
    paper_id: int | None
    external_paper: dict | None
    overall: float
    tables: float
    charts: float
    content_faithfulness: float
    semantic_formatting: float
    visual_grounding: float
    hf_model_url: str | None
    num_parameters: int | None
    is_open: bool


EVAL_ROWS: list[ParseBenchRow] = [
    ParseBenchRow(
        model_name="MinerU 2.5-Pro",
        paper_id=57235,
        external_paper=None,
        overall=72.8,
        tables=77.6,
        charts=61.6,
        content_faithfulness=87.9,
        semantic_formatting=57.5,
        visual_grounding=79.3,
        hf_model_url="https://huggingface.co/opendatalab/MinerU2.5-Pro-2604-1.2B",
        num_parameters=1_156_026_624,
        is_open=True,
    ),
    ParseBenchRow(
        model_name="Chandra OCR 2",
        paper_id=83028,
        external_paper=None,
        overall=70.1,
        tables=89.2,
        charts=65.1,
        content_faithfulness=83.7,
        semantic_formatting=61.4,
        visual_grounding=51.2,
        hf_model_url="https://huggingface.co/datalab-to/chandra-ocr-2",
        num_parameters=5_295_564_288,
        is_open=True,
    ),
    ParseBenchRow(
        model_name="Gemini 3.1 Pro",
        paper_id=97943,
        external_paper=None,
        overall=69.1,
        tables=91.0,
        charts=41.1,
        content_faithfulness=90.2,
        semantic_formatting=52.4,
        visual_grounding=71.0,
        hf_model_url=None,
        num_parameters=None,
        is_open=False,
    ),
    ParseBenchRow(
        model_name="Mistral OCR 4 (Annotation)",
        paper_id=98727,
        external_paper=None,
        overall=68.2,
        tables=73.9,
        charts=40.1,
        content_faithfulness=89.6,
        semantic_formatting=66.4,
        visual_grounding=71.2,
        hf_model_url=None,
        num_parameters=None,
        is_open=False,
    ),
    ParseBenchRow(
        model_name="GPT-5.5",
        paper_id=97922,
        external_paper=None,
        overall=67.8,
        tables=90.1,
        charts=65.5,
        content_faithfulness=86.8,
        semantic_formatting=60.1,
        visual_grounding=36.3,
        hf_model_url=None,
        num_parameters=None,
        is_open=False,
    ),
    ParseBenchRow(
        model_name="PaddleOCR-VL 1.6",
        paper_id=92483,
        external_paper=None,
        overall=67.4,
        tables=67.8,
        charts=54.2,
        content_faithfulness=82.7,
        semantic_formatting=54.6,
        visual_grounding=77.8,
        hf_model_url="https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6",
        num_parameters=958_588_736,
        is_open=True,
    ),
    ParseBenchRow(
        model_name="Mistral OCR 4",
        paper_id=98727,
        external_paper=None,
        overall=60.7,
        tables=73.9,
        charts=2.4,
        content_faithfulness=89.6,
        semantic_formatting=66.4,
        visual_grounding=71.2,
        hf_model_url=None,
        num_parameters=None,
        is_open=False,
    ),
    ParseBenchRow(
        model_name="Unlimited OCR",
        paper_id=98695,
        external_paper=None,
        overall=46.2,
        tables=70.2,
        charts=1.3,
        content_faithfulness=86.8,
        semantic_formatting=1.0,
        visual_grounding=71.5,
        hf_model_url="https://huggingface.co/baidu/Unlimited-OCR",
        num_parameters=3_336_106_240,
        is_open=True,
    ),
    ParseBenchRow(
        model_name="DeepSeek-OCR 2",
        paper_id=55551,
        external_paper=None,
        overall=41.2,
        tables=61.7,
        charts=1.1,
        content_faithfulness=82.0,
        semantic_formatting=54.0,
        visual_grounding=7.0,
        hf_model_url="https://huggingface.co/deepseek-ai/DeepSeek-OCR-2",
        num_parameters=3_389_119_360,
        is_open=True,
    ),
    ParseBenchRow(
        model_name="GLM-OCR",
        paper_id=59560,
        external_paper=None,
        overall=29.6,
        tables=66.1,
        charts=1.7,
        content_faithfulness=78.0,
        semantic_formatting=2.3,
        visual_grounding=0.0,
        hf_model_url="https://huggingface.co/zai-org/GLM-OCR",
        num_parameters=1_325_258_240,
        is_open=True,
    ),
]


def _get_task_and_dataset(session: Session) -> tuple[int, int]:
    task = session.query(DBTask).filter(DBTask.slug == TASK_SLUG).one_or_none()
    if task is None:
        raise RuntimeError(f"Task {TASK_SLUG!r} not found")
    row = session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"),
        {"slug": DATASET_SLUG},
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"Dataset {DATASET_SLUG!r} not found; run add_parsebench_benchmark.py first"
        )
    return int(task.id), int(row[0])


def _ensure_external_paper(session: Session, spec: dict) -> Paper:
    existing = (
        session.query(Paper)
        .filter(
            Paper.source == "external",
            Paper.source_url == spec["source_url"],
        )
        .first()
    )
    if existing:
        return existing

    result = ExternalResourceService(session).add_external_resource(
        ExternalResourceInput(
            source_url=spec["source_url"],
            title=spec["title"],
            abstract=spec["abstract"],
            date_published=spec.get("date_published"),
        )
    )
    paper = session.query(Paper).filter(Paper.id == int(result.paper.id)).one()
    logger.info("Created external paper %r (id=%s)", spec["title"], paper.id)
    return paper


def _format_score(value: float) -> str:
    rounded = round(value, 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}"


def _methodology(row: ParseBenchRow) -> str:
    return (
        "ParseBench overall score from the comparison table in "
        "ParseBench: A Document Parsing Benchmark for AI Agents (2604.08538). "
        f"Dimension scores (%): Tables {_format_score(row.tables)}, "
        f"Charts {_format_score(row.charts)}, "
        f"Content Faithfulness {_format_score(row.content_faithfulness)}, "
        f"Semantic Formatting {_format_score(row.semantic_formatting)}, "
        f"Visual Grounding {_format_score(row.visual_grounding)}."
    )


def _delete_existing_rows(session: Session, task_id: int, dataset_id: int) -> int:
    deleted = session.execute(
        text(
            """
            DELETE FROM evaluations
            WHERE task_id = :task_id
              AND dataset_id = :dataset_id
              AND source_url = :source_url
            """
        ),
        {
            "task_id": task_id,
            "dataset_id": dataset_id,
            "source_url": PARSEBENCH_SOURCE_URL,
        },
    ).rowcount
    session.flush()
    return deleted or 0


def import_rows(
    session: Session, task_id: int, dataset_id: int
) -> tuple[int, list[str]]:
    skipped: list[str] = []
    created = 0

    for row in EVAL_ROWS:
        if row.paper_id is not None:
            paper_id = row.paper_id
        elif row.external_paper is not None:
            paper_id = _ensure_external_paper(session, row.external_paper).id
        else:
            skipped.append(f"{row.model_name}: no paper mapping")
            continue

        existing = session.execute(
            text(
                """
                SELECT id FROM evaluations
                WHERE paper_id = :paper_id
                  AND task_id = :task_id
                  AND dataset_id = :dataset_id
                  AND model_name = :model_name
                  AND COALESCE(harness, '') = ''
                  AND best_metric = :best_metric
                  AND source_url = :source_url
                """
            ),
            {
                "paper_id": paper_id,
                "task_id": task_id,
                "dataset_id": dataset_id,
                "model_name": row.model_name,
                "best_metric": BEST_METRIC,
                "source_url": PARSEBENCH_SOURCE_URL,
            },
        ).first()
        if existing:
            skipped.append(f"{row.model_name}: duplicate row already exists")
            continue

        session.add(
            DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=row.model_name,
                methodology=_methodology(row),
                metrics={BEST_METRIC: _format_score(row.overall)},
                best_metric=BEST_METRIC,
                external_source_url=PARSEBENCH_SOURCE_URL,
                source_url=PARSEBENCH_SOURCE_URL,
                external=True,
                is_open=row.is_open,
                hf_model_url=row.hf_model_url,
                num_parameters=row.num_parameters,
            )
        )
        created += 1

    session.flush()
    EvaluationService(session).recalculate_ranks(
        task_id, dataset_id, metric_name=BEST_METRIC
    )
    return created, skipped


def main() -> None:
    with db_manager.session_local() as session:
        task_id, dataset_id = _get_task_and_dataset(session)
        deleted = _delete_existing_rows(session, task_id, dataset_id)
        created, skipped = import_rows(session, task_id, dataset_id)
        session.commit()
        logger.info("Deleted %d prior ParseBench external rows", deleted)
        logger.info("Created %d ParseBench external evaluation rows", created)
        if skipped:
            logger.info("Skipped %d rows:", len(skipped))
            for line in skipped:
                logger.info("  - %s", line)


if __name__ == "__main__":
    main()
