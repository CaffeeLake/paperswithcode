from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService


BASE_URL = "https://medicalsphere.ai"
TASK_SLUG = "healthcare"
SOURCE_URL = f"{BASE_URL}/benchmarks"


MODEL_PAPER_IDS = {
    "muse-spark-1.1": 103945,
    "gpt-5.6-sol": 102702,
    "gpt-5.5-2026-04-23": 97922,
    "gpt-5.4-2026-03-05": 97924,
    "gpt-4o-mini-2024-07-18": 97935,
    "claude-opus-4-5-20251101": 97915,
    "claude-opus-4-6": 97916,
    "claude-opus-4-7": 97914,
    "claude-opus-4-8": 97913,
    "claude-sonnet-4-6": 97925,
    "gemini-3.1-pro-preview": 97943,
    "gemini-3.5-flash": 98897,
    "gemini-3-flash-preview": 98051,
    "grok-4.5": 102703,
    "moonshotai/Kimi-K2.6": 82965,
    "zai-org/GLM-5.2": 98456,
}


OPEN_MODEL_PREFIXES = (
    "moonshotai/",
    "zai-org/",
    "qwen/",
    "deepseek-ai/",
)


SCENARIO_OVERRIDES = {
    ("medxpertqa", "text_mcq"): {
        "name": "MedXpertQA Text",
        "slug": "medxpertqa-text",
        "metric": "Accuracy",
    },
    ("medxpertqa", "mm_mcq"): {
        "name": "MedXpertQA Multimodal",
        "slug": "medxpertqa-multimodal",
        "metric": "Accuracy",
    },
    ("healthbench-professional", "open_ended_rubric"): {
        "name": "HealthBench Professional",
        "slug": "healthbench-professional",
        "metric": "Score",
    },
    ("medagentbench", "medagentbench-std"): {
        "name": "MedAgentBench",
        "slug": "medagentbench",
        "metric": "Accuracy",
    },
    ("medcalc-bench-verified", "zero_shot"): {
        "name": "MedCalc-Bench Verified (Zero-Shot CoT)",
        "slug": "medcalc-bench-verified-zero-shot-cot",
        "metric": "Accuracy",
    },
    ("medcalc-bench-verified", "one_shot"): {
        "name": "MedCalc-Bench Verified (One-Shot CoT)",
        "slug": "medcalc-bench-verified-one-shot-cot",
        "metric": "Accuracy",
    },
    ("medcalc-bench-verified", "direct_answer"): {
        "name": "MedCalc-Bench Verified (Direct Answer)",
        "slug": "medcalc-bench-verified-direct-answer",
        "metric": "Accuracy",
    },
    ("nejm-bench", "scenario_1_mcq"): {
        "name": "NEJM-bench (MCQ)",
        "slug": "nejm-bench-mcq",
        "metric": "Accuracy",
    },
    ("nejm-bench", "scenario_2_open"): {
        "name": "NEJM-bench (Open-Ended)",
        "slug": "nejm-bench-open-ended",
        "metric": "Score",
    },
}


def fetch_json(path: str) -> Any:
    with urlopen(f"{BASE_URL}{path}") as response:
        return json.loads(response.read().decode("utf-8"))


def pct(value: float) -> str:
    scaled = value * 100 if value <= 1 else value
    return f"{scaled:.6f}".rstrip("0").rstrip(".")


def source_paper_url(row: Any) -> str | None:
    if row is None:
        return None
    if row.arxiv_id:
        return f"https://paperswithcode.co/paper/{row.arxiv_id}"
    return f"https://paperswithcode.co/paper/{row.id}"


def arxiv_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([0-9.]+)", url)
    return match.group(1) if match else None


async def ensure_arxiv_paper(session, arxiv_id: str):
    paper = session.execute(
        text(
            """
            SELECT id, title, arxiv_id, date_published
            FROM papers
            WHERE arxiv_id = :arxiv_id AND is_latest_version
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"arxiv_id": arxiv_id},
    ).first()
    if paper:
        return paper

    await PaperService(session).refresh_arxiv_paper(arxiv_id)
    return session.execute(
        text(
            """
            SELECT id, title, arxiv_id, date_published
            FROM papers
            WHERE arxiv_id = :arxiv_id AND is_latest_version
            ORDER BY id DESC
            LIMIT 1
            """
        ),
        {"arxiv_id": arxiv_id},
    ).first()


def ensure_external_ne_jm_paper(session, benchmark: dict[str, Any]):
    metadata = benchmark.get("metadata") or {}
    source_url = (
        metadata.get("github_url") or f"{BASE_URL}/benchmarks/{benchmark['slug']}"
    )
    paper = session.execute(
        text(
            """
            SELECT id, title, arxiv_id, date_published
            FROM papers
            WHERE source = 'external' AND source_url = :source_url
            LIMIT 1
            """
        ),
        {"source_url": source_url},
    ).first()
    if paper:
        return paper

    session.execute(
        text(
            """
            INSERT INTO papers (
                title, abstract, source, source_url, date_published,
                is_latest_version, version, urls_extracted, hf_datasets
            )
            VALUES (
                :title, :abstract, 'external', :source_url, :date_published,
                true, 'v1', true, :hf_datasets
            )
            """
        ),
        {
            "title": benchmark["name"],
            "abstract": benchmark["description"],
            "source_url": source_url,
            "date_published": date.fromisoformat(benchmark["created_at"][:10]),
            "hf_datasets": [metadata["hf_dataset"]]
            if metadata.get("hf_dataset")
            else None,
        },
    )
    session.commit()
    return session.execute(
        text(
            """
            SELECT id, title, arxiv_id, date_published
            FROM papers
            WHERE source = 'external' AND source_url = :source_url
            LIMIT 1
            """
        ),
        {"source_url": source_url},
    ).first()


def ensure_metric(session, name: str) -> int:
    row = session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": name}
    ).first()
    if row:
        return row.id
    session.execute(
        text(
            """
            INSERT INTO metrics (name, direction, scale)
            VALUES (:name, 'higher_is_better', '0-100')
            """
        ),
        {"name": name},
    )
    session.commit()
    return session.execute(
        text("SELECT id FROM metrics WHERE name = :name"), {"name": name}
    ).scalar_one()


def upsert_dataset(
    session,
    *,
    dataset: dict[str, Any],
    source_paper,
    benchmark: dict[str, Any],
    scenario: dict[str, Any],
) -> int:
    metadata = benchmark.get("metadata") or {}
    session.execute(
        text(
            """
            INSERT INTO datasets (
                name, slug, description, short_description, homepage, url,
                paper_url, introducing_paper_id, introducing_paper_title,
                introduced_year, modalities
            )
            VALUES (
                :name, :slug, :description, :short_description, :homepage, :url,
                :paper_url, :introducing_paper_id, :introducing_paper_title,
                :introduced_year, CAST(:modalities AS jsonb)
            )
            ON CONFLICT (slug) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                short_description = EXCLUDED.short_description,
                homepage = EXCLUDED.homepage,
                url = EXCLUDED.url,
                paper_url = EXCLUDED.paper_url,
                introducing_paper_id = EXCLUDED.introducing_paper_id,
                introducing_paper_title = EXCLUDED.introducing_paper_title,
                introduced_year = EXCLUDED.introduced_year,
                modalities = EXCLUDED.modalities,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "name": dataset["name"],
            "slug": dataset["slug"],
            "description": benchmark["description"],
            "short_description": f"{scenario['name']} scenario from {benchmark['name']}.",
            "homepage": f"{BASE_URL}/benchmarks/{benchmark['slug']}",
            "url": metadata.get("hf_dataset")
            or metadata.get("github_url")
            or f"{BASE_URL}/benchmarks/{benchmark['slug']}",
            "paper_url": source_paper_url(source_paper),
            "introducing_paper_id": source_paper.id if source_paper else None,
            "introducing_paper_title": source_paper.title if source_paper else None,
            "introduced_year": source_paper.date_published.year
            if source_paper and getattr(source_paper, "date_published", None)
            else None,
            "modalities": json.dumps(benchmark.get("modalities") or []),
        },
    )
    session.commit()
    return session.execute(
        text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": dataset["slug"]}
    ).scalar_one()


async def main() -> None:
    migration_sql = Path(
        "backend/database/migrations/add_healthcare_medicalsphere.sql"
    ).read_text()
    benchmarks = fetch_json("/api/benchmarks")
    created_datasets: list[str] = []
    imported: list[str] = []
    skipped: dict[str, int] = {}

    with db_manager.session_local() as session:
        session.execute(text(migration_sql))
        session.commit()

        task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = :slug"), {"slug": TASK_SLUG}
        ).scalar_one()
        medical_imaging_task_id = session.execute(
            text("SELECT id FROM tasks WHERE slug = 'medical-imaging'")
        ).scalar_one_or_none()
        ensure_metric(session, "Accuracy")

        for benchmark in benchmarks:
            metadata = benchmark.get("metadata") or {}
            arxiv_id = arxiv_id_from_url(metadata.get("paper_url"))
            source_paper = (
                await ensure_arxiv_paper(session, arxiv_id) if arxiv_id else None
            )
            if not source_paper and benchmark["slug"] == "nejm-bench":
                source_paper = ensure_external_ne_jm_paper(session, benchmark)

            if source_paper:
                session.execute(
                    text(
                        """
                        INSERT INTO paper_tasks (paper_id, task_id, source)
                        VALUES (:paper_id, :task_id, 'manual')
                        ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
                        """
                    ),
                    {"paper_id": source_paper.id, "task_id": task_id},
                )
                session.commit()

            for scenario in benchmark["scenarios"]:
                override = SCENARIO_OVERRIDES[
                    (benchmark["slug"], scenario["scenario_key"])
                ]
                dataset_id = upsert_dataset(
                    session,
                    dataset=override,
                    source_paper=source_paper,
                    benchmark=benchmark,
                    scenario=scenario,
                )
                created_datasets.append(override["slug"])
                metric_id = ensure_metric(session, override["metric"])
                session.execute(
                    text(
                        """
                        INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                        VALUES (:task_id, :dataset_id, false)
                        ON CONFLICT (task_id, dataset_id) DO UPDATE
                        SET supports_harness = EXCLUDED.supports_harness,
                            updated_at = CURRENT_TIMESTAMP
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
                    {
                        "task_id": task_id,
                        "dataset_id": dataset_id,
                        "metric_id": metric_id,
                    },
                )
                session.commit()

                rows = fetch_json(
                    f"/api/benchmarks/{benchmark['slug']}/leaderboard?scenario_key={quote(scenario['scenario_key'])}"
                )
                for row in rows:
                    paper_id = MODEL_PAPER_IDS.get(row["model_name"])
                    if not paper_id:
                        skipped[f"no-paper:{row['model_name']}"] = (
                            skipped.get(f"no-paper:{row['model_name']}", 0) + 1
                        )
                        continue
                    exists = session.execute(
                        text(
                            """
                            SELECT id FROM evaluations
                            WHERE paper_id = :paper_id
                              AND task_id = :task_id
                              AND dataset_id = :dataset_id
                              AND model_name = :model_name
                              AND COALESCE(harness, '') = ''
                              AND best_metric = :best_metric
                            LIMIT 1
                            """
                        ),
                        {
                            "paper_id": paper_id,
                            "task_id": task_id,
                            "dataset_id": dataset_id,
                            "model_name": row.get("display_name") or row["model_name"],
                            "best_metric": override["metric"],
                        },
                    ).first()
                    if exists:
                        skipped["already-exists"] = skipped.get("already-exists", 0) + 1
                        continue
                    is_open = row["model_name"].lower().startswith(OPEN_MODEL_PREFIXES)
                    methodology = (
                        f"External Medical Sphere evaluation on {benchmark['name']} / "
                        f"{scenario['name']} ({scenario['scenario_key']}); "
                        f"source score {row['score']}; sample_count={row.get('sample_count')}. "
                        f"{metadata.get('scoring_description') or ''}"
                    ).strip()
                    EvaluationService(session).create_evaluation(
                        paper_id=paper_id,
                        task_id=task_id,
                        dataset_id=dataset_id,
                        model_name=row.get("display_name") or row["model_name"],
                        methodology=methodology,
                        metrics={override["metric"]: pct(float(row["score"]))},
                        best_metric=override["metric"],
                        external_source_url=f"{BASE_URL}/benchmarks/{benchmark['slug']}",
                        is_open=is_open,
                    )
                    imported.append(
                        f"{override['slug']}:{row.get('display_name') or row['model_name']}"
                    )

        if medical_imaging_task_id:
            radle_id = session.execute(
                text(
                    "SELECT id FROM datasets WHERE slug = 'radiology-s-last-exam-2-0-radle-2-0'"
                )
            ).scalar_one_or_none()
            if radle_id:
                session.execute(
                    text(
                        """
                        INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
                        VALUES (:task_id, :dataset_id, false)
                        ON CONFLICT (task_id, dataset_id) DO NOTHING
                        """
                    ),
                    {"task_id": task_id, "dataset_id": radle_id},
                )
                for metric_id in session.execute(
                    text(
                        """
                        SELECT metric_id FROM task_dataset_metrics
                        WHERE task_id = :medical_imaging_task_id AND dataset_id = :dataset_id
                        """
                    ),
                    {
                        "medical_imaging_task_id": medical_imaging_task_id,
                        "dataset_id": radle_id,
                    },
                ):
                    session.execute(
                        text(
                            """
                            INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                            VALUES (:task_id, :dataset_id, :metric_id)
                            ON CONFLICT DO NOTHING
                            """
                        ),
                        {
                            "task_id": task_id,
                            "dataset_id": radle_id,
                            "metric_id": metric_id.metric_id,
                        },
                    )
                session.commit()

    print(
        json.dumps(
            {
                "datasets": sorted(set(created_datasets)),
                "evaluations_imported": len(imported),
                "skipped": skipped,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
