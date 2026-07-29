#!/usr/bin/env python3
"""Phase 4 robotics rollout: tag seed-list papers and wire robot-learning methods.

Links the curated robotics reading-list corpus to the Robotics task and attaches
canonical method tags (VLA, imitation learning, Diffusion Policy, ACT).

Run:

    uv run --env-file backend/keys.env \\
        python backend/database/tasks_setup/link_robotics_seed_papers.py
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.database.datasets_setup.add_robotics_benchmarks import ensure_arxiv_paper
from backend.models.database import Paper
from backend.services.paper_method_link_service import upsert_evidence_links

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ROBOTICS_TASK_SLUG = "robotics"

# Full seed list from the robotics practitioner reading list (84 papers).
SEED_ARXIV: list[str] = [
    "2501.09747",
    "2502.19417",
    "2503.14734",
    "2304.13705",
    "2410.18647",
    "2405.04798",
    "2402.19432",
    "2504.05299",
    "2503.03707",
    "2411.04549",
    "1011.0686",
    "2505.11917",
    "2505.09561",
    "2401.17698",
    "2411.09942",
    "2505.12705",
    "2410.24221",
    "2505.03233",
    "2505.11709",
    "2503.13441",
    "2502.13013",
    "2303.04137",
    "2306.03310",
    "2205.14135",
    "2106.09685",
    "2506.01844",
    "2502.05450",
    "2403.12945",
    "2410.13816",
    "2506.16211",
    "2104.09864",
    "2310.05209",
    "2502.08844",
    "2201.00206",
    "2504.01301",
    "2507.05331",
    "2203.15556",
    "2412.09858",
    "2505.10911",
    "2210.00030",
    "2306.00958",
    "2310.08581",
    "2405.19988",
    "2302.12766",
    "2203.12601",
    "2311.06430",
    "2411.04999",
    "2508.07917",
    "2508.21112",
    "2507.06219",
    "2508.13073",
    "2509.25358",
    "2512.00565",
    "2512.01801",
    "2509.07953",
    "1810.02890",
    "2512.15692",
    "2510.14830",
    "2512.05964",
    "2602.11075",
    "2510.19430",
    "2602.09021",
    "2602.15922",
    "2602.18532",
    "2602.01067",
    "2602.03310",
    "2602.19313",
    "2509.00576",
    "2603.03818",
    "2601.21998",
    "2602.16710",
    "2602.10556",
    "2603.16666",
    "2512.24210",
    "2602.13193",
    "2512.08580",
    "2603.06450",
    "2510.00695",
    "2407.08693",
    "2511.17502",
    "2603.13616",
    "2601.18692",
    "2605.03269",
    "2604.03037",
]

# General ML / algorithms / surveys — index if missing but do not tag Robotics.
EXCLUDE_ROBOTICS: set[str] = {
    "1011.0686",  # DAgger (algorithm)
    "1810.02890",  # HG-DAgger (algorithm)
    "2106.09685",  # LoRA
    "2205.14135",  # FlashAttention
    "2104.09864",  # RoFormer / RoPE
    "2203.15556",  # Chinchilla
    "2310.05209",  # RoPE scaling laws
    "2508.13073",  # VLA survey
    "2603.13616",  # N-SCORE (eval methodology)
    "2410.18647",  # Data scaling laws analysis
}

# Robotics papers missing from DB that we should index before tagging.
INDEX_MISSING: set[str] = {
    "2201.00206",
    "2503.03707",
    "2602.13193",
    "2603.03818",
    "2603.06450",
}

VLA_ARXIV: set[str] = {
    "2501.09747",
    "2502.19417",
    "2503.14734",
    "2505.11917",
    "2505.03233",
    "2506.01844",
    "2506.16211",
    "2507.05331",
    "2508.07917",
    "2508.21112",
    "2407.08693",
    "2511.17502",
    "2601.18692",
    "2601.21998",
    "2602.18532",
    "2510.19430",
    "2602.09021",
    "2602.15922",
    "2602.03310",
    "2602.10556",
    "2603.03818",
    "2512.08580",
}

IMITATION_LEARNING_ARXIV: set[str] = {
    "2303.04137",
    "2304.13705",
    "2401.17698",
    "2411.09942",
    "2504.01301",
    "2505.09561",
    "2410.24221",
    "2505.12705",
    "2512.15692",
    "2502.05450",
    "2602.01067",
    "2512.24210",
    "2603.16666",
    "2503.03707",
    "2506.01844",
    "2505.11917",
    "2508.07917",
    "2510.00695",
}

DIFFUSION_POLICY_ARXIV: set[str] = {
    "2303.04137",
    "2505.09561",
    "2401.17698",
    "2411.09942",
    "2504.01301",
    "2510.00695",
}

ACT_ARXIV: set[str] = {
    "2304.13705",
    "2401.17698",
    "2411.09942",
    "2504.01301",
    "2506.01844",
}


def apply_method_migrations(session) -> None:
    for migration in (
        "add_diffusion_policy_method.sql",
        "add_act_method.sql",
    ):
        sql = Path(f"backend/database/migrations/{migration}").read_text()
        session.execute(text(sql))
        logger.info("Applied migration %s", migration)


def tag_paper_task(session, paper_id: int, task_id: int) -> bool:
    result = session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            RETURNING (xmax = 0) AS inserted
            """
        ),
        {"paper_id": paper_id, "task_id": task_id},
    ).scalar()
    return bool(result)


def tag_paper_method(session, paper_id: int, method_slug: str) -> bool:
    method_id = session.execute(
        text("SELECT id FROM methods WHERE slug = :slug"),
        {"slug": method_slug},
    ).scalar()
    if method_id is None:
        return False
    return bool(
        upsert_evidence_links(
            session,
            [{"paper_id": paper_id, "method_id": method_id}],
            evidence_type="manual",
            details={"curation_source": "robotics_seed_list"},
        )
    )


async def index_missing_papers(session) -> list[str]:
    indexed: list[str] = []
    for arxiv_id in sorted(INDEX_MISSING):
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            continue
        await ensure_arxiv_paper(session, arxiv_id)
        indexed.append(arxiv_id)
        logger.info("Indexed missing seed paper %s", arxiv_id)
    return indexed


def link_seed_papers(session) -> dict[str, int]:
    task_id = session.execute(
        text("SELECT id FROM tasks WHERE slug = :slug"),
        {"slug": ROBOTICS_TASK_SLUG},
    ).scalar_one()

    stats = {
        "task_new": 0,
        "vla_new": 0,
        "il_new": 0,
        "dp_new": 0,
        "act_new": 0,
        "skipped_exclude": 0,
        "missing_paper": 0,
    }

    for arxiv_id in SEED_ARXIV:
        if arxiv_id in EXCLUDE_ROBOTICS:
            stats["skipped_exclude"] += 1
            continue

        row = session.execute(
            text(
                """
                SELECT id FROM papers
                WHERE arxiv_id = :arxiv_id AND is_latest_version IS TRUE
                ORDER BY id DESC LIMIT 1
                """
            ),
            {"arxiv_id": arxiv_id},
        ).first()
        if not row:
            stats["missing_paper"] += 1
            logger.warning("Seed paper %s not in DB — skipping", arxiv_id)
            continue

        paper_id = int(row[0])

        if tag_paper_task(session, paper_id, task_id):
            stats["task_new"] += 1

        if arxiv_id in VLA_ARXIV and tag_paper_method(session, paper_id, "vla"):
            stats["vla_new"] += 1
        if arxiv_id in IMITATION_LEARNING_ARXIV and tag_paper_method(
            session, paper_id, "imitation-learning"
        ):
            stats["il_new"] += 1
        if arxiv_id in DIFFUSION_POLICY_ARXIV and tag_paper_method(
            session, paper_id, "diffusion-policy"
        ):
            stats["dp_new"] += 1
        if arxiv_id in ACT_ARXIV and tag_paper_method(session, paper_id, "act"):
            stats["act_new"] += 1

    return stats


def main() -> None:
    session = db_manager.session_local()
    try:
        apply_method_migrations(session)
        indexed = asyncio.run(index_missing_papers(session))
        stats = link_seed_papers(session)
        session.commit()
        logger.info("Indexed %s missing papers: %s", len(indexed), indexed)
        logger.info("Link stats: %s", stats)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
