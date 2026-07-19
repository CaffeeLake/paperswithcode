#!/usr/bin/env python3
"""Import object-counting evals requested in feedback issue #35."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Author, Paper, PaperAuthor
from backend.services.arxiv_service import ArxivService
from backend.services.evaluation_service import EvaluationService
from backend.services.paper_service import PaperService

TASK_ID = 340

PAIR_TALLY_SOURCE = "https://arxiv.org/abs/2509.13939"
PRACO_SOURCE = "https://arxiv.org/abs/2409.15953"
GECO2_SOURCE = "https://arxiv.org/abs/2511.08048"


@dataclass(frozen=True)
class EvalRow:
    paper_key: str
    model_name: str
    dataset_slug: str
    metric: str
    score: float | str
    methodology: str
    source_url: str
    is_open: bool = True
    num_parameters: int | None = None


PAPER_KEYS = {
    "clip_count": "2305.07304",
    "countgd": "2407.04619",
    "counting_detr": "2207.10988",
    "countx": "2306.01851",
    "dave": "2404.16622",
    "famnet": "2104.08391",
    "geco": "2409.18686",
    "geco2": "2511.08048",
    "internvl3": "2504.10479",
    "llama32": "external:https://ai.meta.com/blog/llama-3-2-connect-2024-vision-edge-mobile-devices/",
    "llmdet": "2501.18954",
    "loca": "2211.08217",
    "ovis": "2405.20797",
    "pseco": "2311.12386",
    "qwen25vl": "2502.13923",
    "tfpoc": "2307.00038",
    "vlcounter": "2312.16580",
}


PAIR_TALLY_ROWS = [
    EvalRow(
        "dave",
        "DAVE",
        "pairtally",
        "MAE",
        47.37,
        "PairTally test split; bounding-box exemplars; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "geco",
        "GeCo",
        "pairtally",
        "MAE",
        50.24,
        "PairTally test split; bounding-box exemplars; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "loca",
        "LOCA",
        "pairtally",
        "MAE",
        72.80,
        "PairTally test split; bounding-box exemplars; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "famnet",
        "FamNet",
        "pairtally",
        "MAE",
        75.83,
        "PairTally test split; bounding-box exemplars; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "countgd",
        "CountGD",
        "pairtally",
        "MAE",
        46.67,
        "PairTally test split; text plus exemplar prompts; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "countgd",
        "CountGD (text-only)",
        "pairtally",
        "MAE",
        50.32,
        "PairTally test split; text-only prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "llmdet",
        "LLMDet",
        "pairtally",
        "MAE",
        77.23,
        "PairTally test split; text-only object detector prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
    ),
    EvalRow(
        "ovis",
        "Ovis2",
        "pairtally",
        "MAE",
        65.15,
        "PairTally test split; Ovis2 16B with unified text prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
        num_parameters=16_000_000_000,
    ),
    EvalRow(
        "qwen25vl",
        "Qwen2.5-VL",
        "pairtally",
        "MAE",
        59.36,
        "PairTally test split; Qwen2.5-VL 7B with unified text prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
        num_parameters=7_000_000_000,
    ),
    EvalRow(
        "llama32",
        "LLaMA-3.2",
        "pairtally",
        "MAE",
        54.67,
        "PairTally test split; LLaMA-3.2 11B with unified text prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
        num_parameters=11_000_000_000,
    ),
    EvalRow(
        "internvl3",
        "InternVL3",
        "pairtally",
        "MAE",
        63.41,
        "PairTally test split; InternVL3 14B with unified text prompt; target-category error |f(A)-a| from Table 2.",
        PAIR_TALLY_SOURCE,
        num_parameters=14_000_000_000,
    ),
]


PRACO_METRIC_ROWS = [
    ("countx", "CounTX", 0.95, 64.51, 0.686, 0.712),
    ("clip_count", "CLIP-Count", 1.27, 38.13, 0.495, 0.761),
    ("vlcounter", "VLCounter", 1.15, 53.36, 0.517, 0.781),
    ("tfpoc", "TFPOC", 0.75, 66.04, 0.687, 0.848),
    ("dave", "DAVE", 0.08, 97.62, 0.843, 0.799),
]


def praco_rows() -> list[EvalRow]:
    rows: list[EvalRow] = []
    for paper_key, model_name, nmn, pccn, cntp, cntr in PRACO_METRIC_ROWS:
        for metric, score in [
            ("NMN", nmn),
            ("PCCN", pccn),
            ("CntP", cntp),
            ("CntR", cntr),
        ]:
            rows.append(
                EvalRow(
                    paper_key,
                    model_name,
                    "praco",
                    metric,
                    score,
                    f"PrACo test split; {metric} from Table 1. CntF1 was reported but is not configured on this leaderboard.",
                    PRACO_SOURCE,
                )
            )
    return rows


PRACO_FSC147_ROWS = [
    EvalRow(
        "clip_count",
        "CLIP-Count",
        "fsc-147",
        "MAE",
        17.59,
        "FSC-147 test split; classic MAE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
    EvalRow(
        "clip_count",
        "CLIP-Count",
        "fsc-147",
        "RMSE",
        109.97,
        "FSC-147 test split; classic RMSE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
    EvalRow(
        "vlcounter",
        "VLCounter",
        "fsc-147",
        "MAE",
        17.02,
        "FSC-147 test split; classic MAE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
    EvalRow(
        "vlcounter",
        "VLCounter",
        "fsc-147",
        "RMSE",
        106.93,
        "FSC-147 test split; classic RMSE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
    EvalRow(
        "tfpoc",
        "TFPOC",
        "fsc-147",
        "MAE",
        24.79,
        "FSC-147 test split; classic MAE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
    EvalRow(
        "tfpoc",
        "TFPOC",
        "fsc-147",
        "RMSE",
        138.11,
        "FSC-147 test split; classic RMSE from PrACo Table 1.",
        PRACO_SOURCE,
    ),
]


FSCD_TO_FSC_MODELS = {
    "Counting-DETR",
    "DAVE",
    "DAVE (zero-shot)",
    "GeCo",
    "GECO2",
    "PseCo",
    "PseCo (zero-shot)",
}


def source_url_for_paper(paper: Paper) -> str:
    if paper.arxiv_id:
        return f"https://arxiv.org/abs/{paper.arxiv_id}"
    if paper.source_url:
        return paper.source_url
    return f"https://paperswithcode.co/paper/{paper.id}"


async def ensure_arxiv_paper(session, arxiv_id: str) -> Paper:
    existing = (
        session.query(Paper)
        .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
        .first()
    )
    if existing:
        return existing

    metadata = await ArxivService().get_paper_metadata(arxiv_id)
    if not metadata.success:
        raise RuntimeError(
            f"Failed to fetch arXiv metadata for {arxiv_id}: {metadata.error_message}"
        )

    paper_service = PaperService(session)
    paper_id = paper_service.add_paper(
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
    if not paper_id:
        existing = (
            session.query(Paper)
            .filter(Paper.arxiv_id == arxiv_id, Paper.is_latest_version.is_(True))
            .first()
        )
        if existing:
            return existing
        raise RuntimeError(f"Failed to create paper row for {arxiv_id}")

    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Created paper {paper_id} but could not reload it")

    for order, author_name in enumerate(metadata.authors or [], start=1):
        author = session.query(Author).filter(Author.name == author_name).first()
        if not author:
            author = Author(name=author_name)
            session.add(author)
            session.flush()
        session.add(
            PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=order)
        )
    session.flush()
    return paper


def resolve_external_paper(session, source_url: str) -> Paper:
    paper = (
        session.query(Paper)
        .filter(Paper.source == "external", Paper.source_url == source_url)
        .first()
    )
    if paper is None:
        raise RuntimeError(f"Missing external paper source_url={source_url!r}")
    return paper


async def resolve_paper(session, paper_key: str, cache: dict[str, Paper]) -> Paper:
    if paper_key in cache:
        return cache[paper_key]

    source = PAPER_KEYS[paper_key]
    if source.startswith("external:"):
        paper = resolve_external_paper(session, source.removeprefix("external:"))
    else:
        paper = await ensure_arxiv_paper(session, source)
    cache[paper_key] = paper
    return paper


def link_paper_task(session, paper_id: int) -> None:
    session.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:paper_id, :task_id, 'manual')
            ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual'
            """
        ),
        {"paper_id": paper_id, "task_id": TASK_ID},
    )


def dataset_ids(session) -> dict[str, int]:
    rows = session.execute(
        text(
            """
            SELECT slug, id FROM datasets
            WHERE slug = ANY(:slugs)
            """
        ),
        {"slugs": ["fsc-147", "fscd-147", "mcac", "pairtally", "praco"]},
    ).mappings()
    out = {row["slug"]: int(row["id"]) for row in rows}
    missing = {"fsc-147", "fscd-147", "mcac", "pairtally", "praco"} - set(out)
    if missing:
        raise RuntimeError(f"Missing datasets: {sorted(missing)}")
    return out


def create_if_missing(
    session,
    svc: EvaluationService,
    row: EvalRow,
    paper: Paper,
    dataset_id: int,
) -> bool:
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
            """
        ),
        {
            "paper_id": paper.id,
            "task_id": TASK_ID,
            "dataset_id": dataset_id,
            "model_name": row.model_name,
            "best_metric": row.metric,
        },
    ).first()
    if existing:
        return False

    svc.create_evaluation(
        paper_id=paper.id,
        task_id=TASK_ID,
        dataset_id=dataset_id,
        model_name=row.model_name,
        methodology=row.methodology,
        metrics={row.metric: row.score},
        best_metric=row.metric,
        source_url=row.source_url,
        num_parameters=row.num_parameters,
        is_open=row.is_open,
    )
    return True


async def build_fscd_to_fsc_rows(session) -> list[EvalRow]:
    rows = session.execute(
        text(
            """
            SELECT e.paper_id, p.arxiv_id, p.source_url AS paper_source_url,
                   e.model_name, e.best_metric, e.metrics, e.methodology,
                   e.source_url, e.external_source_url, e.is_open, e.num_parameters
            FROM evaluations e
            JOIN datasets d ON d.id = e.dataset_id
            JOIN papers p ON p.id = e.paper_id
            WHERE d.slug = 'fscd-147'
              AND e.task_id = :task_id
              AND e.best_metric IN ('MAE', 'RMSE')
              AND e.model_name = ANY(:models)
            ORDER BY e.paper_id, e.model_name, e.best_metric
            """
        ),
        {"task_id": TASK_ID, "models": sorted(FSCD_TO_FSC_MODELS)},
    ).mappings()

    out: list[EvalRow] = []
    for row in rows:
        source_url = (
            row["source_url"]
            or row["external_source_url"]
            or (
                f"https://arxiv.org/abs/{row['arxiv_id']}"
                if row["arxiv_id"]
                else row["paper_source_url"]
            )
            or f"https://paperswithcode.co/paper/{row['paper_id']}"
        )
        methodology = (
            "FSC-147 counting metric copied from the FSCD-147 leaderboard; "
            "FSCD-147 uses the same counting targets and additionally evaluates "
            f"bounding boxes. Original row: {row['methodology'] or 'source paper leaderboard table'}."
        )
        out.append(
            EvalRow(
                f"paper_id:{row['paper_id']}",
                row["model_name"],
                "fsc-147",
                row["best_metric"],
                row["metrics"][row["best_metric"]],
                methodology,
                source_url,
                is_open=row["is_open"],
                num_parameters=row["num_parameters"],
            )
        )
    return out


def resolve_paper_id_key(session, paper_key: str) -> Paper:
    paper_id = int(paper_key.split(":", 1)[1])
    paper = session.get(Paper, paper_id)
    if paper is None:
        raise RuntimeError(f"Missing paper_id={paper_id}")
    return paper


def update_mcac_provenance(session) -> int:
    result = session.execute(
        text(
            """
            UPDATE evaluations e
            SET source_url = :source_url,
                external_source_url = :source_url,
                external = TRUE,
                methodology = :methodology
            FROM datasets d
            WHERE d.id = e.dataset_id
              AND d.slug = 'mcac'
              AND e.task_id = :task_id
              AND e.paper_id = (
                  SELECT id FROM papers
                  WHERE arxiv_id = '2409.18686' AND is_latest_version
                  LIMIT 1
              )
              AND e.model_name = 'GeCo'
              AND e.best_metric IN ('MAE', 'RMSE')
            """
        ),
        {
            "task_id": TASK_ID,
            "source_url": GECO2_SOURCE,
            "methodology": "MCAC test split; few-shot with 3 exemplars per category. GECO2 Table 3; arXiv:2511.08048.",
        },
    )
    session.execute(
        text(
            """
            UPDATE evaluations e
            SET source_url = :source_url,
                external_source_url = :source_url,
                external = FALSE,
                methodology = :methodology
            FROM datasets d
            WHERE d.id = e.dataset_id
              AND d.slug = 'mcac'
              AND e.task_id = :task_id
              AND e.paper_id = (
                  SELECT id FROM papers
                  WHERE arxiv_id = '2511.08048' AND is_latest_version
                  LIMIT 1
              )
              AND e.model_name = 'GECO2'
              AND e.best_metric IN ('MAE', 'RMSE')
            """
        ),
        {
            "task_id": TASK_ID,
            "source_url": GECO2_SOURCE,
            "methodology": "MCAC test split; few-shot with 3 exemplars per category. GECO2 Table 3; arXiv:2511.08048.",
        },
    )
    session.commit()
    return int(result.rowcount or 0)


async def main() -> None:
    session = db_manager.session_local()
    paper_cache: dict[str, Paper] = {}
    created_by_group = {
        "pairtally": 0,
        "praco": 0,
        "praco_fsc147": 0,
        "fscd_to_fsc147": 0,
    }
    skipped_by_group = {key: 0 for key in created_by_group}
    try:
        datasets = dataset_ids(session)
        svc = EvaluationService(session)

        for group, rows in [
            ("pairtally", PAIR_TALLY_ROWS),
            ("praco", praco_rows()),
            ("praco_fsc147", PRACO_FSC147_ROWS),
        ]:
            for row in rows:
                paper = await resolve_paper(session, row.paper_key, paper_cache)
                link_paper_task(session, paper.id)
                created = create_if_missing(
                    session, svc, row, paper, datasets[row.dataset_slug]
                )
                created_by_group[group] += int(created)
                skipped_by_group[group] += int(not created)

        for row in await build_fscd_to_fsc_rows(session):
            paper = resolve_paper_id_key(session, row.paper_key)
            link_paper_task(session, paper.id)
            created = create_if_missing(session, svc, row, paper, datasets["fsc-147"])
            created_by_group["fscd_to_fsc147"] += int(created)
            skipped_by_group["fscd_to_fsc147"] += int(not created)

        mcac_updated = update_mcac_provenance(session)

        for slug in ["fsc-147", "fscd-147", "mcac", "pairtally", "praco"]:
            dataset_id = datasets[slug]
            for metric in ["AP", "AP50", "CntP", "CntR", "MAE", "NMN", "PCCN", "RMSE"]:
                svc.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)

        session.commit()
        print("created", created_by_group)
        print("skipped", skipped_by_group)
        print(f"mcac_geco_rows_updated={mcac_updated}")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    asyncio.run(main())
