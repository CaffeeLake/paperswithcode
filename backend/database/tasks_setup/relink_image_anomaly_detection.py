#!/usr/bin/env python3
"""Conservatively link papers to the Image Anomaly Detection task.

The generic phrase "anomaly detection" spans time series, logs, graphs, medical
imaging, video surveillance, semantic OOD detection, and many other domains.
This backfill therefore requires an image/industrial-specific task keyword and
removes obvious non-image domains before writing auto links.
"""

from __future__ import annotations

import re

from psycopg2.extras import RealDictCursor, execute_batch

from backend.database.connection import db_manager
from backend.utils.keyword_matching import (
    create_keyword_patterns,
    find_matching_items_simple,
)

TASK_SLUG = "image-anomaly-detection"
TASK_KEYWORDS = (
    "image anomaly detection, image anomaly localization, image anomaly segmentation, "
    "industrial image anomaly detection, industrial visual anomaly detection, "
    "industrial anomaly detection, industrial anomaly localization, "
    "industrial anomaly segmentation, surface anomaly detection, "
    "surface anomaly localization, zero-shot visual anomaly detection, "
    "few-shot visual anomaly detection, MVTec AD, MVTec LOCO AD, Real-IAD"
)

# These papers were recovered from the legacy MVTec/VisA comparison tables and
# citation survey. Their titles are sometimes intentionally generic, so the
# phrase matcher alone misses them even though their experiments are directly
# about industrial image anomaly detection. Pin them as manual links so a future
# global auto-tag rebuild cannot remove the audited additions.
CURATED_ARXIV_IDS = (
    "2005.02357",  # SPADE
    "2006.16067",  # Patch SVDD
    "2008.12577",  # DifferNet
    "2103.04257",  # STPM
    "2104.04015",  # CutPaste
    "2107.12571",  # CFLOW-AD
    "2201.10703",  # Reverse Distillation / RD4AD
    "2206.04325",  # CFA
    "2210.07829",  # AST
    "2303.00601",  # M3DM
    "2303.08730",  # DiffusionAD
    "2304.02216",  # MMR / AeBAD
    "2305.15956",  # DDAD
    "2305.17382",  # APRIL-GAN
    "2308.15300",  # MSFlow
    "2310.18961",  # AnomalyCLIP
    "2403.05897",  # RealNet
    "2403.14233",  # SoftPatch
    "2404.06564",  # MambaAD
    "2404.13671",  # FiLo
    "2407.09359",  # GLASS
    "2407.15795",  # AdaCLIP
    "2412.07579",  # URD
    "2412.17458",  # PBAS
)

# A benchmark mention is strong evidence only in the context of anomaly work.
BENCHMARK_PATTERN = re.compile(
    r"\b(?:mvtec(?:\s|-)?ad(?:\s?2)?|mvtec\s+loco(?:\s+ad)?|real-iad|btad|mpdd)\b",
    re.IGNORECASE,
)
ANOMALY_PATTERN = re.compile(
    r"\b(?:anomal(?:y|ies|ous)|defect(?:s|ive)?)\b",
    re.IGNORECASE,
)

# Title-level exclusions are intentionally narrow. A paper with one of these
# domains in its title is not an image-anomaly paper unless its title also uses
# an explicit image/visual/industrial anomaly phrase.
EXCLUDED_TITLE_PHRASES = (
    "time series",
    "time-series",
    "video anomaly",
    "surveillance anomaly",
    "network anomaly",
    "log anomaly",
    "graph anomaly",
    "audio anomaly",
    "brain anomaly",
    "medical anomaly",
    "mri anomaly",
    "hyperspectral anomaly",
    "point cloud anomaly",
    "3d anomaly",
    "lidar anomaly",
)
TITLE_OVERRIDE_PHRASES = (
    "image anomaly",
    "visual anomaly",
    "industrial anomaly",
    "surface anomaly",
)
NON_IMAGE_ABSTRACT_PATTERN = re.compile(
    r"\b(?:physics-grounded video dataset|video anomaly detection|"
    r"videos across \d+ .{0,40} categories)\b",
    re.IGNORECASE,
)


def is_image_anomaly_paper(
    title: str,
    abstract: str | None,
    task_id: int,
    case_sensitive,
    case_insensitive,
) -> bool:
    title_lower = title.lower()
    text = f"{title} {abstract or ''}"
    text_lower = text.lower()

    keyword_match = task_id in find_matching_items_simple(
        text, case_sensitive, case_insensitive
    )
    benchmark_match = bool(
        BENCHMARK_PATTERN.search(text) and ANOMALY_PATTERN.search(text)
    )
    if not (keyword_match or benchmark_match):
        return False

    if any(phrase in title_lower for phrase in EXCLUDED_TITLE_PHRASES) and not any(
        phrase in title_lower for phrase in TITLE_OVERRIDE_PHRASES
    ):
        return False

    # Some video papers use the broad phrase "industrial anomaly detection"
    # without saying "video" in the title. Reject only strong abstract-level
    # video evidence so ordinary image papers that cite video work remain.
    if NON_IMAGE_ABSTRACT_PATTERN.search(abstract or "") and not any(
        phrase in title_lower
        for phrase in ("image anomaly", "visual anomaly", "surface anomaly")
    ):
        return False

    # Generic semantic OOD papers frequently mention MVTec or industrial anomaly
    # detection only in related work. Require direct visual anomaly evidence.
    if (
        any(
            phrase in title_lower
            for phrase in (
                "out-of-distribution detection",
                "out of distribution detection",
                "ood detection",
            )
        )
        and not any(phrase in title_lower for phrase in TITLE_OVERRIDE_PHRASES)
        and not BENCHMARK_PATTERN.search(title)
    ):
        return False

    # Avoid benchmark-name citations in unrelated papers.
    if benchmark_match and not keyword_match:
        direct_evidence = any(
            phrase in text_lower
            for phrase in (
                "industrial inspection",
                "industrial anomaly",
                "image anomaly",
                "visual anomaly",
                "surface defect",
                "anomaly localization",
                "anomaly segmentation",
            )
        )
        if not direct_evidence:
            return False

    return True


def main() -> None:
    conn = db_manager.engine.raw_connection()
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(
            "SELECT id FROM tasks WHERE slug = %s",
            (TASK_SLUG,),
        )
        task = cur.fetchone()
        if not task:
            raise RuntimeError(f"Task not found: {TASK_SLUG}")
        task_id = int(task["id"])

        cur.execute(
            "UPDATE tasks SET keywords = %s, updated_at = NOW() WHERE id = %s",
            (TASK_KEYWORDS, task_id),
        )
        cur.execute(
            "DELETE FROM paper_tasks WHERE task_id = %s AND source = 'auto'",
            (task_id,),
        )
        deleted = cur.rowcount

        case_sensitive, case_insensitive = create_keyword_patterns(
            [{"id": task_id, "keywords": TASK_KEYWORDS}]
        )
        cur.execute(
            """
            SELECT id, title, abstract
            FROM papers
            WHERE is_latest_version
            ORDER BY id
            """
        )
        matches = [
            (row["id"], task_id)
            for row in cur
            if is_image_anomaly_paper(
                row["title"],
                row["abstract"],
                task_id,
                case_sensitive,
                case_insensitive,
            )
        ]
        if matches:
            execute_batch(
                cur,
                """
                INSERT INTO paper_tasks (paper_id, task_id, source)
                VALUES (%s, %s, 'auto')
                ON CONFLICT (paper_id, task_id) DO NOTHING
                """,
                matches,
                page_size=1000,
            )
        cur.execute(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            SELECT p.id, %s, 'manual'
            FROM papers p
            WHERE p.arxiv_id = ANY(%s)
              AND p.is_latest_version
            ON CONFLICT (paper_id, task_id)
            DO UPDATE SET source = 'manual'
            """,
            (task_id, list(CURATED_ARXIV_IDS)),
        )
        curated = cur.rowcount
        conn.commit()
        print(
            f"{TASK_SLUG}: deleted {deleted:,} prior auto links; "
            f"created {len(matches):,} conservative auto links; "
            f"pinned {curated:,} curated comparison-table links"
        )
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
