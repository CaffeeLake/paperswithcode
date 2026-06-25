#!/usr/bin/env python3
"""Import Video-MME-v2 (2604.05015) Table 1 rows as external evals on model paper pages.

Run:
    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/import_video_mme_v2_external_evals.py
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import Paper as DBPaper
from backend.services.evaluation_service import EvaluationService

SOURCE_URL = "https://paperswithcode.co/paper/2604.05015"
TASK_ID = 9  # Video Understanding
DATASET_ID = 674  # Video-MME-v2
METHODOLOGY_PREFIX = (
    "Video-MME-v2 Table 1; w. sub (visual frames + subtitles/audio); "
    "source arXiv:2604.05015."
)

CLOSED_PAPER_IDS = {
    98051,  # Gemini 3
    63525,  # GPT-5 System Card
}


@dataclass(frozen=True)
class Row:
    raw_name: str
    frames: str
    score: float
    accuracy: float


# Table 1 main results (excluding human baseline).
ROWS: list[Row] = [
    Row("Gemini-3-Pro", "1fps", 49.4, 66.1),
    Row("Doubao-Seed-2.0-Pro-260215", "1fps", 43.3, 60.5),
    Row("Gemini-3-Flash", "1fps", 42.5, 61.1),
    Row("MiMo-v2-Omni", "1fps", 38.6, 56.1),
    Row("GPT-5", "50", 37.0, 55.6),
    Row("Kimi-K2.5", "64", 36.1, 54.4),
    Row("Qwen3-VL-235B-A22B-Instruct", "64", 25.0, 43.3),
    Row("Qwen3.5-397B-A17B-Instruct", "64", 24.5, 42.1),
    Row("Qwen3.5-27B-Instruct", "64", 23.9, 41.9),
    Row("InternVL3_5-241B-A28B-Instruct", "64", 23.1, 41.4),
    Row("Qwen2-5-VL-72B-Instruct", "64", 22.1, 38.9),
    Row("Qwen3.5-122B-A10B-Instruct", "64", 20.9, 39.2),
    Row("Qwen3.5-35B-A3B-Instruct", "64", 19.9, 36.9),
    Row("KimiVL-16B-A3B-Instruct", "64", 19.0, 37.3),
    Row("Qwen3.5-9B-Instruct", "64", 18.3, 35.5),
    Row("Qwen3-VL-8B-Instruct", "64", 18.2, 35.7),
    Row("Qwen3-VL-4B-Instruct", "64", 17.6, 34.1),
    Row("LLaVA-Video-72B-Qwen2", "64", 17.2, 34.4),
    Row("Qwen3-Omni-30B-A3B-Instruct", "64", 17.1, 34.1),
    Row("Qwen3-VL-30B-A3B-Instruct", "64", 16.8, 33.2),
    Row("InternVL3_5-30B-A3B-Instruct", "64", 16.6, 34.2),
    Row("InternVL3_5-8B-Instruct", "64", 16.4, 32.4),
    Row("Qwen3.5-4B-Instruct", "64", 15.4, 32.3),
    Row("MiMo-VL-7B-SFT-2508", "64", 14.7, 31.2),
    Row("Qwen2-5-VL-7B-Instruct", "64", 14.4, 30.9),
    Row("VideoLLaMA3-7B", "64", 14.2, 30.6),
    Row("InternVL-3-5-4B-Instruct", "64", 14.2, 30.5),
    Row("Keye-VL-1-5-8B", "64", 14.1, 31.1),
    Row("VITA-1.5-7B", "16", 11.3, 25.8),
    Row("LLaVA-Video-7B-Qwen2", "64", 9.7, 24.0),
    Row("Qwen3.5-397B-A17B-Think", "512", 39.1, 55.9),
    Row("Qwen3.5-27B-Think", "512", 31.4, 49.6),
    Row("Qwen3.5-397B-A17B-Think", "64", 30.6, 48.9),
    Row("Qwen3.5-27B-Think", "64", 29.6, 47.6),
    Row("Qwen3-VL-235B-A22B-Think", "512", 28.1, 47.2),
    Row("Qwen3.5-122B-A10B-Think", "64", 26.7, 45.1),
    Row("Qwen3.5-Omni-Plus", "64", 25.6, 44.3),
    Row("Qwen3-VL-235B-A22B-Think", "64", 26.3, 44.9),
    Row("Qwen3.5-9B-Think", "512", 26.2, 44.5),
    Row("Qwen3.5-35B-A3B-Think", "64", 25.8, 43.9),
    Row("Qwen3.5-122B-A10B-Think", "512", 25.1, 43.4),
    Row("Qwen3.5-35B-A3B-Think", "512", 23.9, 41.5),
    Row("Qwen3.5-9B-Think", "64", 23.2, 40.3),
    Row("Qwen3-VL-30B-A3B-Think", "512", 22.1, 39.8),
    Row("GLM4.5V-Think", "64", 21.8, 39.2),
    Row("Qwen3-VL-30B-A3B-Think", "64", 21.1, 38.6),
    Row("Qwen3.5-4B-Think", "64", 20.7, 38.8),
    Row("Qwen3-VL-8B-Think", "512", 20.2, 37.3),
    Row("GLM4.6-Flash", "64", 19.8, 37.4),
    Row("Qwen3-VL-8B-Think", "64", 19.7, 37.2),
    Row("Qwen3-Omni-30B-A3B-Think", "64", 19.5, 36.5),
    Row("MiMo-VL-7B-RL-2508", "64", 19.4, 36.0),
    Row("Qwen3-VL-4B-Think", "64", 18.2, 35.3),
    Row("KimiVL-16B-A3B-Think", "64", 15.7, 32.4),
    Row("GLM4.1V-Think", "64", 14.0, 30.3),
]

PAPER_PREFIXES: list[tuple[str, int]] = [
    ("Doubao-Seed-2.0-Pro", -1),  # resolved at runtime
    ("Gemini-3-Pro", 98051),
    ("Gemini-3-Flash", 98051),
    ("MiMo-v2-Omni", -2),  # resolved at runtime
    ("GPT-5", 63525),
    ("Kimi-K2.5", 55657),
    ("KimiVL", 47488),
    ("Qwen3.5-Omni-Plus", 57552),
    ("Qwen3.5-", 83017),
    ("Qwen3-VL-", 54536),
    ("Qwen3-Omni-", 52888),
    ("Qwen2-5-VL-", 44599),
    ("InternVL3_5-", 52518),
    ("InternVL-3-5-", 52518),
    ("LLaVA-Video-", 37794),
    ("VideoLLaMA3-", 43121),
    ("Keye-VL-", 52611),
    ("VITA-1.5-", 42463),
    ("MiMo-VL-", 50523),
    ("GLM4.5V-", 51617),
    ("GLM4.6-", 51617),
    ("GLM4.1V-", 51617),
]

EXTERNAL_PAPERS = [
    {
        "title": "Seed2.0 model card: towards intelligence frontier for real-world complexity",
        "source_url": "https://github.com/ByteDance-Seed/Seed2.0",
        "date_published": date(2026, 2, 15),
        "github_repository_urls": ["https://github.com/ByteDance-Seed/Seed2.0"],
    },
    {
        "title": "Xiaomi MiMo-v2-Omni: see, hear, act in the agentic era",
        "source_url": "https://huggingface.co/XiaomiMiMo/MiMo-V2-Omni",
        "date_published": date(2026, 1, 1),
        "hf_artifact_urls": ["https://huggingface.co/XiaomiMiMo/MiMo-V2-Omni"],
    },
]


def _ensure_external_papers(db) -> dict[str, int]:
    ids: dict[str, int] = {}
    for spec in EXTERNAL_PAPERS:
        existing = (
            db.query(DBPaper)
            .filter(
                DBPaper.source == "external",
                DBPaper.source_url == spec["source_url"],
            )
            .first()
        )
        if existing is None:
            paper = DBPaper(
                title=spec["title"],
                source="external",
                source_url=spec["source_url"],
                date_published=spec["date_published"],
                is_latest_version=True,
                version="v1",
                urls_extracted=True,
                hf_models=spec.get("hf_artifact_urls"),
            )
            db.add(paper)
            db.flush()
            existing = paper
        ids[spec["source_url"]] = existing.id
    return ids


def _display_name(raw: str, frames: str) -> str:
    name = (
        raw.replace("InternVL3_5", "InternVL3.5")
        .replace("Qwen2-5-VL", "Qwen2.5-VL")
        .replace("GLM4.5V", "GLM-4.5V")
        .replace("GLM4.6", "GLM-4.6")
        .replace("GLM4.1V", "GLM-4.1V")
        .replace("Doubao-Seed-2.0-Pro-260215", "Doubao-Seed-2.0-Pro")
    )
    if frames.endswith("fps"):
        return name
    if frames in {"64", "16"}:
        return name
    return f"{name} ({frames} frames)"


def _resolve_paper_id(raw: str, external_ids: dict[str, int]) -> int | None:
    for prefix, paper_id in PAPER_PREFIXES:
        if not raw.startswith(prefix):
            continue
        if paper_id == -1:
            return external_ids["https://github.com/ByteDance-Seed/Seed2.0"]
        if paper_id == -2:
            return external_ids["https://huggingface.co/XiaomiMiMo/MiMo-V2-Omni"]
        return paper_id
    return None


def _methodology(frames: str) -> str:
    sampling = frames if frames.endswith("fps") else f"{frames} sampled frames"
    return f"{METHODOLOGY_PREFIX} Video sampling: {sampling}."


def main() -> None:
    session_gen = get_database_session()
    db = next(session_gen)
    created = 0
    skipped = 0
    missing: list[str] = []
    try:
        external_ids = _ensure_external_papers(db)
        svc = EvaluationService(db)
        for row in ROWS:
            paper_id = _resolve_paper_id(row.raw_name, external_ids)
            if paper_id is None:
                missing.append(row.raw_name)
                continue
            model_name = _display_name(row.raw_name, row.frames)
            methodology = _methodology(row.frames)
            is_open = paper_id not in CLOSED_PAPER_IDS
            for metric, value in (("Score", row.score), ("Accuracy", row.accuracy)):
                params = {
                    "paper_id": paper_id,
                    "task_id": TASK_ID,
                    "dataset_id": DATASET_ID,
                    "model_name": model_name,
                    "best_metric": metric,
                }
                existing = db.execute(
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
                    paper_id=paper_id,
                    task_id=TASK_ID,
                    dataset_id=DATASET_ID,
                    model_name=model_name,
                    methodology=methodology,
                    metrics={metric: str(value)},
                    best_metric=metric,
                    external_source_url=SOURCE_URL,
                    source_url=SOURCE_URL,
                    is_open=is_open,
                )
                created += 1
        db.commit()
        print(f"created={created} skipped={skipped}")
        if missing:
            print("missing paper mapping:", missing)
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()
