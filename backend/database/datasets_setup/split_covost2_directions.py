"""Split CoVoST 2 into direction-specific leaderboards (X→En vs En→X).

Legacy Papers with Code kept these as separate datasets. Mixing macro X→En
averages with single-pair En→Zh scores on one ranked page is not comparable.

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/datasets_setup/split_covost2_directions.py
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

PARENT_DATASET_ID = 739
TASK_SLUG = "machine-translation"
METRIC_NAME = "BLEU"

X_EN_NAME = "CoVoST 2 (X→En)"
X_EN_SLUG = "covost-2-x-en"
EN_X_NAME = "CoVoST 2 (En→X)"
EN_X_SLUG = "covost-2-en-x"

PARENT_DESCRIPTION = (
    "CoVoST 2 is a massively multilingual speech-to-text translation benchmark. "
    "Results are reported on separate leaderboards by translation direction: "
    "X→En (source languages into English) and En→X (English into target languages)."
)

X_EN_DESCRIPTION = (
    "CoVoST 2 X→En: speech-to-text translation from source languages into English. "
    "Macro-average BLEU over multilingual directions (typically 20–21 languages on test). "
    "Single-pair rows (e.g. Chinese→English) may appear when papers report only that direction."
)

EN_X_DESCRIPTION = (
    "CoVoST 2 En→X: speech-to-text translation from English into target languages. "
    "Report BLEU on the official CoVoST 2 test split for the evaluated direction(s)."
)

# Evaluations to keep on the X→En leaderboard.
X_EN_EVAL_IDS = [10364, 9343, 9479]

# Evaluations to move to the En→X leaderboard.
EN_X_EVAL_IDS = [9478]

USM_EVAL_ID = 9343
USM_BLEU = "28.7"
USM_METHODOLOGY = (
    "Table 3 in-domain fine-tuned USM; CoVoST 2 XX→English macro BLEU over "
    "21 source languages (test). Parenthetical 6.9 in the paper is the "
    "low-resource subset on FLEURS 102-lang, not CoVoST."
)


def _get_task_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
    ).scalar_one()


def _get_metric_id(session: Session) -> int:
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :n"), {"n": METRIC_NAME}
    ).scalar_one()


def _get_parent(session: Session) -> DBDataset:
    parent = (
        session.query(DBDataset).filter(DBDataset.id == PARENT_DATASET_ID).one_or_none()
    )
    if parent is None:
        raise RuntimeError(f"CoVoST 2 parent dataset id={PARENT_DATASET_ID} not found")
    return parent


def _ensure_child_dataset(
    session: Session,
    parent: DBDataset,
    *,
    name: str,
    slug: str,
    description: str,
    split_name: str,
) -> DBDataset:
    dataset = session.query(DBDataset).filter(DBDataset.slug == slug).one_or_none()
    if dataset is None:
        dataset = DBDataset(
            name=name,
            slug=slug,
            description=description,
            short_description=description.split(".")[0] + ".",
            hf_url=parent.hf_url,
            homepage=parent.homepage,
            paper_url=parent.paper_url,
            introducing_paper_id=parent.introducing_paper_id,
            introducing_paper_title=parent.introducing_paper_title,
            introduced_year=parent.introduced_year,
            parent_dataset_id=parent.id,
            variant_type="subset",
            split_name=split_name,
            modalities=parent.modalities,
            languages=parent.languages,
        )
        session.add(dataset)
        session.flush()
        logger.info("Created dataset %r (id=%s)", dataset.name, dataset.id)
        return dataset

    dataset.name = name
    dataset.description = description
    dataset.short_description = description.split(".")[0] + "."
    dataset.parent_dataset_id = parent.id
    dataset.variant_type = "subset"
    dataset.split_name = split_name
    dataset.paper_url = parent.paper_url
    dataset.introducing_paper_id = parent.introducing_paper_id
    dataset.introducing_paper_title = parent.introducing_paper_title
    dataset.hf_url = parent.hf_url
    dataset.homepage = parent.homepage
    session.flush()
    logger.info("Updated dataset %r (id=%s)", dataset.name, dataset.id)
    return dataset


def _ensure_task_links(
    session: Session, task_id: int, dataset_id: int, metric_id: int
) -> None:
    session.execute(
        text(
            "INSERT INTO task_datasets (task_id, dataset_id) "
            "VALUES (:t, :d) ON CONFLICT (task_id, dataset_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id},
    )
    session.execute(
        text(
            "INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id) "
            "VALUES (:t, :d, :m) ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING"
        ),
        {"t": task_id, "d": dataset_id, "m": metric_id},
    )


def _unlink_parent_from_task(session: Session, task_id: int, parent_id: int) -> None:
    session.execute(
        text("DELETE FROM task_datasets WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )
    session.execute(
        text("DELETE FROM task_dataset_metrics WHERE task_id = :t AND dataset_id = :d"),
        {"t": task_id, "d": parent_id},
    )


def _migrate_evaluations(
    session: Session,
    service: EvaluationService,
    *,
    task_id: int,
    x_en_dataset_id: int,
    en_x_dataset_id: int,
) -> None:
    service.update_evaluation(
        evaluation_id=USM_EVAL_ID,
        dataset_id=x_en_dataset_id,
        metrics={"BLEU": USM_BLEU},
        best_metric=METRIC_NAME,
        methodology=USM_METHODOLOGY,
    )
    logger.info("Fixed USM eval %s -> BLEU %s on X→En", USM_EVAL_ID, USM_BLEU)

    for eval_id in X_EN_EVAL_IDS:
        if eval_id == USM_EVAL_ID:
            continue
        service.update_evaluation(evaluation_id=eval_id, dataset_id=x_en_dataset_id)
        logger.info("Moved evaluation %s -> CoVoST 2 (X→En)", eval_id)

    for eval_id in EN_X_EVAL_IDS:
        service.update_evaluation(evaluation_id=eval_id, dataset_id=en_x_dataset_id)
        logger.info("Moved evaluation %s -> CoVoST 2 (En→X)", eval_id)

    service.recalculate_ranks(task_id, x_en_dataset_id, metric_name=METRIC_NAME)
    service.recalculate_ranks(task_id, en_x_dataset_id, metric_name=METRIC_NAME)


def _move_orphan_parent_evals(
    session: Session,
    service: EvaluationService,
    *,
    task_id: int,
    parent_id: int,
    x_en_dataset_id: int,
) -> None:
    orphan_ids = (
        session.execute(
            text("SELECT id FROM evaluations WHERE dataset_id = :d"),
            {"d": parent_id},
        )
        .scalars()
        .all()
    )
    for eval_id in orphan_ids:
        service.update_evaluation(evaluation_id=eval_id, dataset_id=x_en_dataset_id)
        logger.info("Moved orphan parent evaluation %s -> CoVoST 2 (X→En)", eval_id)
    if orphan_ids:
        service.recalculate_ranks(task_id, x_en_dataset_id, metric_name=METRIC_NAME)


def main() -> None:
    session = db_manager.session_local()
    try:
        parent = _get_parent(session)
        parent.description = PARENT_DESCRIPTION
        parent.short_description = (
            "Multilingual speech-to-text translation; see X→En and En→X leaderboards."
        )
        task_id = _get_task_id(session)
        metric_id = _get_metric_id(session)

        x_en = _ensure_child_dataset(
            session,
            parent,
            name=X_EN_NAME,
            slug=X_EN_SLUG,
            description=X_EN_DESCRIPTION,
            split_name="X→En",
        )
        en_x = _ensure_child_dataset(
            session,
            parent,
            name=EN_X_NAME,
            slug=EN_X_SLUG,
            description=EN_X_DESCRIPTION,
            split_name="En→X",
        )

        _ensure_task_links(session, task_id, x_en.id, metric_id)
        _ensure_task_links(session, task_id, en_x.id, metric_id)
        _unlink_parent_from_task(session, task_id, parent.id)
        session.commit()

        service = EvaluationService(session)
        _migrate_evaluations(
            session,
            service,
            task_id=task_id,
            x_en_dataset_id=x_en.id,
            en_x_dataset_id=en_x.id,
        )
        _move_orphan_parent_evals(
            session,
            service,
            task_id=task_id,
            parent_id=parent.id,
            x_en_dataset_id=x_en.id,
        )
        session.commit()

        for label, dataset_id in [
            ("parent", parent.id),
            ("x-en", x_en.id),
            ("en-x", en_x.id),
        ]:
            count = session.execute(
                text("SELECT COUNT(*) FROM evaluations WHERE dataset_id = :d"),
                {"d": dataset_id},
            ).scalar_one()
            logger.info("%s evals=%s (dataset_id=%s)", label, count, dataset_id)

        logger.info(
            "Done. X→En: https://paperswithcode.co/benchmark/%s | "
            "En→X: https://paperswithcode.co/benchmark/%s",
            x_en.slug,
            en_x.slug,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
