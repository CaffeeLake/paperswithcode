"""Split Procgen's canonical generalization and PPG sample-efficiency protocols.

Dataset 1057 was originally a generic Procgen row containing a 100M-step PPG
result. The Procgen source paper defines the canonical hard generalization
protocol at 200M steps with 500 training levels, so the two results must not
share a leaderboard.

Run:
    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/fix_procgen_protocol_benchmarks.py
"""

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Dataset, Evaluation, Paper, Task

SOURCE_ARXIV_ID = "1912.01588"
SOURCE_URL = f"https://paperswithcode.co/paper/{SOURCE_ARXIV_ID}"
TASK_ID = 366
TASK_SLUG = "procedural-generalization"
CANONICAL_DATASET_ID = 1057
PPG_EVALUATION_ID = 13422
METRIC_NAME = "Mean Normalized Performance"

GENERALIZATION_SLUG = "procgen-hard-generalization-500-train-levels-200m-steps"
SAMPLE_EFFICIENCY_SLUG = "procgen-hard-sample-efficiency-full-distribution-100m-steps"


def require_source_paper(session) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.arxiv_id == SOURCE_ARXIV_ID, Paper.is_latest_version)
        .one_or_none()
    )
    if paper is None:
        raise RuntimeError(f"Source paper {SOURCE_ARXIV_ID} is missing")
    return paper


def require_task(session) -> Task:
    task = session.query(Task).filter(Task.slug == TASK_SLUG).one_or_none()
    if task is None or task.id != TASK_ID:
        raise RuntimeError(
            f"Expected task {TASK_SLUG!r} with id={TASK_ID}, found {task!r}"
        )
    return task


def configure_dataset(
    dataset: Dataset,
    *,
    name: str,
    slug: str,
    description: str,
    short_description: str,
    split_name: str,
    paper: Paper,
) -> None:
    dataset.name = name
    dataset.slug = slug
    dataset.full_name = name
    dataset.description = description
    dataset.short_description = short_description
    dataset.homepage = "https://github.com/openai/procgen"
    dataset.parent_dataset_id = None
    dataset.variant_type = "variant"
    dataset.split_name = split_name
    dataset.paper_url = SOURCE_URL
    dataset.introducing_paper_id = paper.id
    dataset.introducing_paper_title = paper.title
    dataset.introduced_date = paper.date_published
    dataset.introduced_year = 2019


def ensure_sample_efficiency_dataset(session, paper: Paper) -> Dataset:
    dataset = (
        session.query(Dataset)
        .filter(Dataset.slug == SAMPLE_EFFICIENCY_SLUG)
        .one_or_none()
    )
    if dataset is None:
        dataset = Dataset(
            name="Procgen Hard Sample Efficiency (Full Distribution, 100M Steps)",
            slug=SAMPLE_EFFICIENCY_SLUG,
        )
        session.add(dataset)
        session.flush()

    configure_dataset(
        dataset,
        name="Procgen Hard Sample Efficiency (Full Distribution, 100M Steps)",
        slug=SAMPLE_EFFICIENCY_SLUG,
        description=(
            "The 16-game Procgen hard-mode sample-efficiency aggregate for "
            "agents trained for 100 million environment steps while sampling "
            "unlimited levels from the full distribution. Performance is the "
            "arithmetic mean of each game's normalized episodic return using "
            "the Procgen source paper's Rmin and Rmax constants. This protocol "
            "is not comparable to the canonical 500-training-level, 200M-step "
            "generalization protocol."
        ),
        short_description=(
            "Procgen hard-mode mean normalized return after 100M steps on the "
            "full level distribution."
        ),
        split_name="full distribution / 100M environment steps",
        paper=paper,
    )
    return dataset


def wire_leaderboard(session, dataset_id: int, metric_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO task_datasets (
                task_id, dataset_id, featured_rank, supports_harness
            )
            VALUES (:task_id, :dataset_id, NULL, FALSE)
            ON CONFLICT (task_id, dataset_id) DO UPDATE
            SET featured_rank = NULL, supports_harness = FALSE
            """
        ),
        {"task_id": TASK_ID, "dataset_id": dataset_id},
    )
    session.execute(
        text(
            """
            DELETE FROM task_dataset_metrics
            WHERE task_id = :task_id AND dataset_id = :dataset_id
              AND metric_id <> :metric_id
            """
        ),
        {
            "task_id": TASK_ID,
            "dataset_id": dataset_id,
            "metric_id": metric_id,
        },
    )
    session.execute(
        text(
            """
            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
            VALUES (:task_id, :dataset_id, :metric_id)
            ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
            """
        ),
        {
            "task_id": TASK_ID,
            "dataset_id": dataset_id,
            "metric_id": metric_id,
        },
    )


def move_ppg_evaluation(session, sample_efficiency_dataset_id: int) -> None:
    evaluation = session.get(Evaluation, PPG_EVALUATION_ID)
    if evaluation is None:
        raise RuntimeError(f"PPG evaluation {PPG_EVALUATION_ID} is missing")
    if evaluation.model_name != "PPG" or evaluation.paper.arxiv_id != "2009.04416":
        raise RuntimeError(
            f"Evaluation {PPG_EVALUATION_ID} is not the expected PPG row"
        )
    if evaluation.metrics != {METRIC_NAME: "0.757"}:
        raise RuntimeError(
            f"Evaluation {PPG_EVALUATION_ID} has unexpected metrics: "
            f"{evaluation.metrics!r}"
        )

    evaluation.dataset_id = sample_efficiency_dataset_id
    evaluation.best_metric = METRIC_NAME
    evaluation.methodology = (
        "Procgen hard mode across all 16 games; unlimited levels sampled from "
        "the full distribution; 100M environment steps; score 0.757 is the "
        "mean normalized episodic return using Procgen Rmin/Rmax constants "
        "(PPG paper Figure 2 and Appendix A.2)."
    )
    evaluation.harness = None


def main() -> None:
    with db_manager.session_local() as session:
        task = require_task(session)
        paper = require_source_paper(session)
        metric_id = session.execute(
            text("SELECT id FROM metrics WHERE name = :name"),
            {"name": METRIC_NAME},
        ).scalar_one()

        canonical = session.get(Dataset, CANONICAL_DATASET_ID)
        if canonical is None:
            raise RuntimeError(f"Dataset {CANONICAL_DATASET_ID} is missing")
        configure_dataset(
            canonical,
            name="Procgen Hard Generalization (500 Train Levels, 200M Steps)",
            slug=GENERALIZATION_SLUG,
            description=(
                "The canonical 16-game Procgen hard-mode generalization "
                "aggregate. Agents train for 200 million environment steps on "
                "500 fixed training levels per game, then undergo zero-shot "
                "evaluation on unseen levels sampled from the full level "
                "distribution. Performance is the arithmetic mean of each "
                "game's normalized return using the source paper's Rmin and "
                "Rmax constants. Results with unlimited training levels or a "
                "different interaction budget are not comparable."
            ),
            short_description=(
                "Procgen hard-mode zero-shot generalization from 500 train "
                "levels after 200M steps."
            ),
            split_name="500 train levels / full unseen test distribution",
            paper=paper,
        )
        sample_efficiency = ensure_sample_efficiency_dataset(session, paper)
        session.flush()

        session.execute(
            text(
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (:paper_id, :task_id, 'manual')
                ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                """
            ),
            {"paper_id": paper.id, "task_id": task.id},
        )
        wire_leaderboard(session, canonical.id, metric_id)
        wire_leaderboard(session, sample_efficiency.id, metric_id)
        move_ppg_evaluation(session, sample_efficiency.id)
        session.commit()

        print(
            "Procgen protocols ready: "
            f"generalization={canonical.id}, "
            f"sample_efficiency={sample_efficiency.id}, "
            f"metric={METRIC_NAME}"
        )


if __name__ == "__main__":
    main()
