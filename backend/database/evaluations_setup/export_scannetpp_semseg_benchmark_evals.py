#!/usr/bin/env python3
"""Export ScanNet++ semseg benchmark leaderboard rows to CSV for later DB import.

Scrapes Top-1 and Top-3 mIoU leaderboards on the official ScanNet++ site,
annotates against the local DB (readonly), and writes:

  data/scannetpp_semseg_benchmark_evals_to_add.csv
  data/scannetpp_semseg_benchmark_evals_reference.csv

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/export_scannetpp_semseg_benchmark_evals.py
"""

from __future__ import annotations

import csv
import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import get_engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://scannetpp.mlsg.cit.tum.de"
BENCHMARK_SOURCE_URL = f"{BASE_URL}/scannetpp/benchmark/semseg"
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_TO_ADD = REPO_ROOT / "data" / "scannetpp_semseg_benchmark_evals_to_add.csv"
OUT_REFERENCE = REPO_ROOT / "data" / "scannetpp_semseg_benchmark_evals_reference.csv"

SCORE_MATCH_TOLERANCE = 0.25

TASK_ID = 326
TASK_SLUG = "3d-semantic-segmentation"
DATASET_ID = 676
DATASET_SLUG = "scannet-plus-plus"
BEST_METRIC = "mIoU"

CSV_COLUMNS = [
    "topk",
    "submission_id",
    "method_name",
    "model_name",
    "arxiv_id",
    "publication_url",
    "paper_exists",
    "paper_id",
    "task_slug",
    "task_id",
    "dataset_slug",
    "dataset_id",
    "best_metric",
    "score",
    "action",
    "existing_model_name",
    "existing_score",
    "source_code_url",
    "is_open",
    "methodology",
    "external_source_url",
    "notes",
    "skip_reason",
]


@dataclass
class Submission:
    topk: int
    submission_id: str
    method_name: str
    score_raw: float
    arxiv_id: str | None = None
    publication_url: str = ""
    source_code_url: str = ""
    info_links: list[str] = field(default_factory=list)

    @property
    def score_pct(self) -> float:
        return round(self.score_raw * 100, 2)

    @property
    def model_name(self) -> str:
        name = re.sub(r"\s+", " ", self.method_name).strip()
        if self.topk == 3:
            return f"{name} (Top-3)"
        return name


def fetch(path: str) -> str:
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    return subprocess.check_output(
        ["curl", "-sL", "--max-time", "45", url],
        text=True,
    )


def normalize_arxiv_id(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip().rstrip(".")
    return cleaned or None


def extract_arxiv_id(url: str) -> str | None:
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([\d.]+)", url or "")
    return normalize_arxiv_id(match.group(1)) if match else None


def parse_leaderboard(html: str, topk: int) -> list[Submission]:
    tbody = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    if not tbody:
        return []

    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1), re.S)
    submissions: list[Submission] = []

    for i, tr in enumerate(trs):
        method_match = re.search(
            r'<th[^>]*scope="row"[^>]*>.*?>([^<]+)</a>',
            tr,
            re.S,
        )
        if not method_match:
            continue

        method_name = method_match.group(1).strip()
        score_match = re.search(
            r"<th[^>]*>.*?</th>\s*<td[^>]*>(?:<b>)?([\d.]+)",
            tr,
            re.S,
        )
        if not score_match:
            continue

        submission_match = re.search(r"/benchmark/submission/view/(\d+)", tr)
        submission_id = submission_match.group(1) if submission_match else ""

        arxiv_id = None
        publication_url = ""
        source_code_url = ""
        info_links: list[str] = []
        if i + 1 < len(trs):
            citation_tr = trs[i + 1]
            arxiv_link = re.search(
                r'href="(https://arxiv\.org/[^"]+)"',
                citation_tr,
            )
            if arxiv_link:
                publication_url = arxiv_link.group(1)
                arxiv_id = extract_arxiv_id(publication_url)
            info_links = re.findall(r'href="([^"]+)"', citation_tr)
            for link in info_links:
                if "github.com" in link:
                    source_code_url = link
                    break

        submissions.append(
            Submission(
                topk=topk,
                submission_id=submission_id,
                method_name=method_name,
                score_raw=float(score_match.group(1)),
                arxiv_id=arxiv_id,
                publication_url=publication_url,
                source_code_url=source_code_url,
                info_links=info_links,
            )
        )

    return submissions


def scrape_submissions() -> list[Submission]:
    pages = [
        ("/scannetpp/benchmark/semseg", 1),
        ("/scannetpp/benchmark/semseg?topk=3", 3),
    ]
    submissions: list[Submission] = []
    for path, topk in pages:
        logger.info("Fetching %s", path)
        html = fetch(path)
        submissions.extend(parse_leaderboard(html, topk))
    return submissions


@dataclass
class ExistingEval:
    model_name: str
    best_metric: str
    score: float
    external: bool
    source_url: str | None


def load_db_state() -> tuple[
    dict[str, int],
    set[str],
    dict[tuple[int, int, int], list[ExistingEval]],
]:
    papers_by_arxiv: dict[str, int] = {}
    paper_reports_scannetpp: set[str] = set()
    evals_by_key: dict[tuple[int, int, int], list[ExistingEval]] = {}

    with get_engine().connect() as conn:
        for row in conn.execute(
            text(
                "SELECT id, arxiv_id FROM papers "
                "WHERE arxiv_id IS NOT NULL AND is_latest_version"
            )
        ):
            papers_by_arxiv[row.arxiv_id] = row.id

        rows = (
            conn.execute(
                text(
                    """
                SELECT p.arxiv_id, e.paper_id, e.task_id, e.dataset_id,
                       e.model_name, e.best_metric, e.metrics, e.external,
                       e.source_url
                FROM evaluations e
                JOIN papers p ON p.id = e.paper_id
                JOIN datasets d ON d.id = e.dataset_id
                WHERE d.slug = :dataset_slug
                  AND e.task_id = :task_id
                """
                ),
                {"dataset_slug": DATASET_SLUG, "task_id": TASK_ID},
            )
            .mappings()
            .all()
        )

        for row in rows:
            if row["arxiv_id"] and not row["external"]:
                paper_reports_scannetpp.add(row["arxiv_id"])

            key = (row["paper_id"], row["task_id"], row["dataset_id"])
            metric_value = row["metrics"].get(row["best_metric"])
            if metric_value is None:
                continue
            evals_by_key.setdefault(key, []).append(
                ExistingEval(
                    model_name=row["model_name"],
                    best_metric=row["best_metric"],
                    score=float(metric_value),
                    external=row["external"],
                    source_url=row["source_url"],
                )
            )

    return papers_by_arxiv, paper_reports_scannetpp, evals_by_key


def is_open_submission(sub: Submission) -> bool:
    if sub.source_code_url and "github.com" in sub.source_code_url:
        return True
    return any("github.com" in link for link in sub.info_links)


def methodology_for(sub: Submission) -> str:
    topk_label = "Top-1" if sub.topk == 1 else "Top-3"
    return (
        f"ScanNet++ v2 test {topk_label} mIoU from official benchmark leaderboard; "
        f"source: {BENCHMARK_SOURCE_URL}"
    )


def find_existing_evals(
    paper_id: int | None,
    evals_by_key: dict[tuple[int, int, int], list[ExistingEval]],
) -> list[ExistingEval]:
    if paper_id is None:
        return []
    return evals_by_key.get((paper_id, TASK_ID, DATASET_ID), [])


def classify_submission(
    sub: Submission,
    papers_by_arxiv: dict[str, int],
    paper_reports_scannetpp: set[str],
    evals_by_key: dict[tuple[int, int, int], list[ExistingEval]],
) -> dict:
    paper_id = papers_by_arxiv.get(sub.arxiv_id) if sub.arxiv_id else None
    existing = find_existing_evals(paper_id, evals_by_key)
    model_name = sub.model_name

    action = "add"
    existing_model_name = ""
    existing_score = ""
    notes = ""
    skip_reason = ""

    if not sub.arxiv_id:
        action = "skip"
        skip_reason = "no_arxiv"
    elif sub.topk == 1 and sub.arxiv_id in paper_reports_scannetpp:
        action = "skip"
        skip_reason = "paper_reports_score"
        notes = "paper already has non-external ScanNet++ mIoU row"
    else:
        close_match = next(
            (
                ev
                for ev in existing
                if ev.model_name == model_name
                and ev.best_metric == BEST_METRIC
                and abs(ev.score - sub.score_pct) <= SCORE_MATCH_TOLERANCE
                and (ev.source_url or "") == BENCHMARK_SOURCE_URL
            ),
            None,
        )
        if close_match:
            action = "skip"
            skip_reason = "already_in_db"
            existing_model_name = close_match.model_name
            existing_score = str(close_match.score)

    if paper_id is None and sub.arxiv_id:
        notes = "; ".join(filter(None, [notes, "paper import required"]))

    return {
        "topk": sub.topk,
        "submission_id": sub.submission_id,
        "method_name": sub.method_name,
        "model_name": model_name,
        "arxiv_id": sub.arxiv_id or "",
        "publication_url": sub.publication_url,
        "paper_exists": "true" if paper_id is not None else "false",
        "paper_id": str(paper_id) if paper_id is not None else "",
        "task_slug": TASK_SLUG,
        "task_id": TASK_ID,
        "dataset_slug": DATASET_SLUG,
        "dataset_id": DATASET_ID,
        "best_metric": BEST_METRIC,
        "score": sub.score_pct,
        "action": action,
        "existing_model_name": existing_model_name,
        "existing_score": existing_score,
        "source_code_url": sub.source_code_url,
        "is_open": "true" if is_open_submission(sub) else "false",
        "methodology": methodology_for(sub),
        "external_source_url": BENCHMARK_SOURCE_URL,
        "notes": notes,
        "skip_reason": skip_reason,
        "_score_raw": sub.score_raw,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def main() -> None:
    submissions = scrape_submissions()
    logger.info("Fetched %s leaderboard rows", len(submissions))

    papers_by_arxiv, paper_reports_scannetpp, evals_by_key = load_db_state()
    annotated = [
        classify_submission(sub, papers_by_arxiv, paper_reports_scannetpp, evals_by_key)
        for sub in submissions
    ]

    to_add = [r for r in annotated if r["action"] == "add"]
    reference = [r for r in annotated if r["action"] != "add"]

    to_add.sort(key=lambda r: (r["topk"], -r["_score_raw"]))
    reference.sort(
        key=lambda r: (r.get("skip_reason", ""), r["topk"], -r["_score_raw"])
    )

    for row in to_add + reference:
        row.pop("_score_raw", None)

    write_csv(OUT_TO_ADD, to_add)
    write_csv(OUT_REFERENCE, reference)

    logger.info("Wrote %s rows to %s", len(to_add), OUT_TO_ADD)
    logger.info("Wrote %s rows to %s", len(reference), OUT_REFERENCE)

    print("\n=== evals_to_add.csv summary ===")
    by_topk: dict[int, int] = {}
    for row in to_add:
        by_topk[row["topk"]] = by_topk.get(row["topk"], 0) + 1
    for topk, count in sorted(by_topk.items()):
        print(f"  topk={topk}: {count}")

    print("\n=== rows to add ===")
    for row in to_add:
        print(
            f"  topk={row['topk']} {row['model_name']:30} "
            f"score={row['score']} arxiv={row['arxiv_id']}"
        )

    ref_reasons: dict[str, int] = {}
    for row in reference:
        reason = row.get("skip_reason") or "unknown"
        ref_reasons[reason] = ref_reasons.get(reason, 0) + 1
    print("\n=== evals_reference.csv skip_reason counts ===")
    for reason, count in sorted(ref_reasons.items()):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
