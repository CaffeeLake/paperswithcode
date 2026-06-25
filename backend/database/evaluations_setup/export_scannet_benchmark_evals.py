#!/usr/bin/env python3
"""Export ScanNet benchmark leaderboard rows to CSV for later DB import.

Scrapes the four 3D semantic/instance leaderboards on kaldir, enriches each
submission from result_details, annotates against the local DB (readonly), and
writes:

  data/scannet_benchmark_evals_to_add.csv
  data/scannet_benchmark_evals_reference.csv

Run with:

    uv run --env-file backend/keys.env \\
        python backend/database/evaluations_setup/export_scannet_benchmark_evals.py
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

BASE_URL = "https://kaldir.vc.in.tum.de"
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_TO_ADD = REPO_ROOT / "data" / "scannet_benchmark_evals_to_add.csv"
OUT_REFERENCE = REPO_ROOT / "data" / "scannet_benchmark_evals_reference.csv"

TOP_N_PER_BOARD = 20
SCORE_MATCH_TOLERANCE = 0.25

BOARDS = {
    "scannet_sem": {
        "benchmark_page": "semantic_label_3d",
        "metric_hint": "avg iou",
        "task_slug": "3d-semantic-segmentation",
        "task_id": 326,
        "dataset_slug": "scannet",
        "dataset_id": 276,
        "best_metric": "mIoU",
    },
    "scannet_inst": {
        "benchmark_page": "semantic_instance_3d",
        "metric_hint": "avg ap",
        "task_slug": "3d-instance-segmentation",
        "task_id": 327,
        "dataset_slug": "scannet",
        "dataset_id": 276,
        "best_metric": "AP50",
    },
    "scannet200_sem": {
        "benchmark_page": "scannet200_semantic_label_3d",
        "metric_hint": "avg iou",
        "task_slug": "3d-semantic-segmentation",
        "task_id": 326,
        "dataset_slug": "scannet200",
        "dataset_id": 675,
        "best_metric": "mIoU",
    },
    "scannet200_inst": {
        "benchmark_page": "scannet200_semantic_instance_3d",
        "metric_hint": "avg ap",
        "task_slug": "3d-instance-segmentation",
        "task_id": 327,
        "dataset_slug": "scannet200",
        "dataset_id": 675,
        "best_metric": "AP50",
    },
}

CSV_COLUMNS = [
    "board",
    "benchmark_page",
    "submission_id",
    "method_name",
    "model_name",
    "arxiv_id",
    "publication_title",
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
    board: str
    submission_id: str
    method_name: str
    score_raw: float
    info_links: list[str] = field(default_factory=list)
    publication_url: str = ""
    publication_title: str = ""
    source_code_url: str = ""
    arxiv_id: str | None = None

    @property
    def score_pct(self) -> float:
        return round(self.score_raw * 100, 2)

    @property
    def result_details_url(self) -> str:
        return f"{BASE_URL}/scannet_benchmark/result_details?id={self.submission_id}"


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


def normalize_model_name(method_name: str) -> str:
    return re.sub(r"\s+", " ", method_name).strip()


def parse_leaderboard(
    html: str, metric_hint: str
) -> list[tuple[str, str, float, list[str]]]:
    thead = re.search(r"<thead>(.*?)</thead>", html, re.S)
    headers: list[str] = []
    if thead:
        for th in re.findall(r"<th[^>]*>(.*?)</th>", thead.group(1), re.S):
            headers.append(
                re.sub(r"<[^>]+>", "", th).replace("&nbsp;", " ").strip().lower()
            )
    avg_idx = next((i for i, h in enumerate(headers) if metric_hint in h), 2)

    rows: list[tuple[str, str, float, list[str]]] = []
    for tr in re.findall(r"<tr>.*?</tr>", html, re.S):
        match = re.search(
            r"<td><a href=/scannet_benchmark/result_details\?id=(\d+)>([^<]+)</a></td>",
            tr,
        )
        if not match:
            continue
        submission_id, method_name = match.group(1), match.group(2).strip()
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) <= avg_idx:
            continue
        score_td = tds[avg_idx]
        score_match = re.search(r"(?:<b>)?([\d.]+)(?:</b>)?", score_td)
        if not score_match:
            continue
        score = float(score_match.group(1))
        info_links = re.findall(r'href="([^"]+)"', tds[1] if len(tds) > 1 else "")
        rows.append((submission_id, method_name, score, info_links))
    return rows


def parse_result_details(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in (
        "Publication URL",
        "Publication title",
        "Full name",
        "Source code or download URL",
    ):
        match = re.search(
            rf"<tr><td><b>{re.escape(key)}</b></td><td>(.*?)</td></tr>",
            html,
            re.S,
        )
        if not match:
            continue
        cell = match.group(1)
        link = re.search(r'href="([^"]+)"', cell)
        text_value = re.sub(r"<[^>]+>", "", cell).strip()
        out[key] = link.group(1) if link else text_value
    return out


def scrape_submissions() -> list[Submission]:
    submissions: list[Submission] = []
    seen_ids: set[str] = set()

    for board, spec in BOARDS.items():
        path = f"/scannet_benchmark/{spec['benchmark_page']}"
        logger.info("Fetching %s", path)
        html = fetch(path)
        for submission_id, method_name, score, info_links in parse_leaderboard(
            html, spec["metric_hint"]
        ):
            if submission_id in seen_ids:
                continue
            seen_ids.add(submission_id)

            details_html = fetch(
                f"/scannet_benchmark/result_details?id={submission_id}"
            )
            details = parse_result_details(details_html)
            publication_url = details.get("Publication URL", "")
            publication_title = (
                details.get("Publication title") or details.get("Full name") or ""
            )
            source_code_url = details.get("Source code or download URL", "")
            if not source_code_url:
                for link in info_links:
                    if "github.com" in link:
                        source_code_url = link
                        break

            submissions.append(
                Submission(
                    board=board,
                    submission_id=submission_id,
                    method_name=method_name,
                    score_raw=score,
                    info_links=info_links,
                    publication_url=publication_url,
                    publication_title=publication_title,
                    source_code_url=source_code_url,
                    arxiv_id=extract_arxiv_id(publication_url),
                )
            )
    return submissions


def dedupe_by_board_arxiv(submissions: list[Submission]) -> list[Submission]:
    best: dict[tuple[str, str], Submission] = {}
    for sub in submissions:
        if not sub.arxiv_id:
            continue
        key = (sub.board, sub.arxiv_id)
        if key not in best or sub.score_raw > best[key].score_raw:
            best[key] = sub
    return list(best.values())


def dedupe_by_board_method(submissions: list[Submission]) -> list[Submission]:
    best: dict[tuple[str, str], Submission] = {}
    for sub in submissions:
        key = (sub.board, sub.method_name)
        if key not in best or sub.score_raw > best[key].score_raw:
            best[key] = sub
    return list(best.values())


@dataclass
class ExistingEval:
    model_name: str
    best_metric: str
    score: float


def load_db_state() -> tuple[
    dict[str, int], dict[tuple[int, int, int], list[ExistingEval]]
]:
    papers_by_arxiv: dict[str, int] = {}
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
                SELECT e.paper_id, e.task_id, e.dataset_id, e.model_name,
                       e.best_metric, e.metrics
                FROM evaluations e
                JOIN datasets d ON d.id = e.dataset_id
                JOIN tasks t ON t.id = e.task_id
                WHERE d.slug IN ('scannet', 'scannet200')
                  AND t.slug IN (
                      '3d-semantic-segmentation', '3d-instance-segmentation'
                  )
                """
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            key = (row["paper_id"], row["task_id"], row["dataset_id"])
            metric_value = row["metrics"].get(row["best_metric"])
            if metric_value is None:
                continue
            evals_by_key.setdefault(key, []).append(
                ExistingEval(
                    model_name=row["model_name"],
                    best_metric=row["best_metric"],
                    score=float(metric_value),
                )
            )
    return papers_by_arxiv, evals_by_key


def is_open_submission(sub: Submission) -> bool:
    if sub.source_code_url and "github.com" in sub.source_code_url:
        return True
    return any("github.com" in link for link in sub.info_links)


def methodology_for(sub: Submission, spec: dict) -> str:
    dataset_label = "ScanNet200" if "200" in sub.board else "ScanNet(v2)"
    split_label = "test"
    metric_label = spec["best_metric"]
    return (
        f"{dataset_label} {split_label} {metric_label} from official benchmark "
        f"leaderboard ({spec['benchmark_page']}); "
        f"source: {sub.result_details_url}"
    )


def find_existing_evals(
    paper_id: int | None,
    task_id: int,
    dataset_id: int,
    evals_by_key: dict[tuple[int, int, int], list[ExistingEval]],
) -> list[ExistingEval]:
    if paper_id is None:
        return []
    return evals_by_key.get((paper_id, task_id, dataset_id), [])


def classify_submission(
    sub: Submission,
    spec: dict,
    papers_by_arxiv: dict[str, int],
    evals_by_key: dict[tuple[int, int, int], list[ExistingEval]],
) -> dict:
    paper_id = papers_by_arxiv.get(sub.arxiv_id) if sub.arxiv_id else None
    existing = find_existing_evals(
        paper_id, spec["task_id"], spec["dataset_id"], evals_by_key
    )

    action = "add"
    existing_model_name = ""
    existing_score = ""
    notes = ""
    skip_reason = ""

    close_match = next(
        (
            ev
            for ev in existing
            if abs(ev.score - sub.score_pct) <= SCORE_MATCH_TOLERANCE
        ),
        None,
    )
    if close_match:
        action = "skip"
        skip_reason = "already_in_db"
        existing_model_name = close_match.model_name
        existing_score = str(close_match.score)
    elif existing:
        best_existing = max(existing, key=lambda ev: ev.score)
        if abs(best_existing.score - sub.score_pct) > SCORE_MATCH_TOLERANCE:
            action = "update"
            existing_model_name = best_existing.model_name
            existing_score = str(best_existing.score)
            notes = f"replaces stored score {best_existing.score}"

    if paper_id is None and sub.arxiv_id:
        notes = "; ".join(filter(None, [notes, "paper import required"]))

    return {
        "board": sub.board,
        "benchmark_page": spec["benchmark_page"],
        "submission_id": sub.submission_id,
        "method_name": sub.method_name,
        "model_name": normalize_model_name(sub.method_name),
        "arxiv_id": sub.arxiv_id or "",
        "publication_title": sub.publication_title,
        "publication_url": sub.publication_url,
        "paper_exists": "true" if paper_id is not None else "false",
        "paper_id": str(paper_id) if paper_id is not None else "",
        "task_slug": spec["task_slug"],
        "task_id": spec["task_id"],
        "dataset_slug": spec["dataset_slug"],
        "dataset_id": spec["dataset_id"],
        "best_metric": spec["best_metric"],
        "score": sub.score_pct,
        "action": action,
        "existing_model_name": existing_model_name,
        "existing_score": existing_score,
        "source_code_url": sub.source_code_url,
        "is_open": "true" if is_open_submission(sub) else "false",
        "methodology": methodology_for(sub, spec),
        "external_source_url": sub.result_details_url,
        "notes": notes,
        "skip_reason": skip_reason,
        "_score_raw": sub.score_raw,
    }


def classify_no_arxiv(sub: Submission, spec: dict) -> dict:
    return {
        "board": sub.board,
        "benchmark_page": spec["benchmark_page"],
        "submission_id": sub.submission_id,
        "method_name": sub.method_name,
        "model_name": normalize_model_name(sub.method_name),
        "arxiv_id": "",
        "publication_title": sub.publication_title,
        "publication_url": sub.publication_url,
        "paper_exists": "false",
        "paper_id": "",
        "task_slug": spec["task_slug"],
        "task_id": spec["task_id"],
        "dataset_slug": spec["dataset_slug"],
        "dataset_id": spec["dataset_id"],
        "best_metric": spec["best_metric"],
        "score": sub.score_pct,
        "action": "skip",
        "existing_model_name": "",
        "existing_score": "",
        "source_code_url": sub.source_code_url,
        "is_open": "true" if is_open_submission(sub) else "false",
        "methodology": methodology_for(sub, spec),
        "external_source_url": sub.result_details_url,
        "notes": "",
        "skip_reason": "no_arxiv",
        "_score_raw": sub.score_raw,
    }


def select_top_missing(
    rows: list[dict], board: str, limit: int = TOP_N_PER_BOARD
) -> tuple[list[dict], list[dict]]:
    board_rows = [r for r in rows if r["board"] == board and r["arxiv_id"]]
    ranked = sorted(board_rows, key=lambda r: r["_score_raw"], reverse=True)

    selected: list[dict] = []
    deferred: list[dict] = []
    for row in ranked:
        if row["action"] == "skip" and row["skip_reason"] == "already_in_db":
            deferred.append(row)
            continue
        if len(selected) < limit:
            if row["action"] == "skip":
                row = {**row, "action": "add", "skip_reason": ""}
            selected.append(row)
        else:
            deferred.append({**row, "skip_reason": "below_top20"})
    return selected, deferred


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in CSV_COLUMNS})


def main() -> None:
    submissions = scrape_submissions()
    logger.info("Fetched %s unique submissions", len(submissions))

    arxiv_submissions = dedupe_by_board_arxiv(submissions)
    no_arxiv_submissions = dedupe_by_board_method(
        [s for s in submissions if not s.arxiv_id]
    )
    papers_by_arxiv, evals_by_key = load_db_state()

    annotated_arxiv: list[dict] = []
    for sub in arxiv_submissions:
        spec = BOARDS[sub.board]
        annotated_arxiv.append(
            classify_submission(sub, spec, papers_by_arxiv, evals_by_key)
        )

    to_add: list[dict] = []
    reference: list[dict] = []

    for board in BOARDS:
        selected, deferred = select_top_missing(annotated_arxiv, board)
        to_add.extend(selected)
        reference.extend(deferred)

    for sub in no_arxiv_submissions:
        reference.append(classify_no_arxiv(sub, BOARDS[sub.board]))

    to_add.sort(key=lambda r: (r["board"], -r["_score_raw"]))
    reference.sort(
        key=lambda r: (
            r.get("skip_reason", ""),
            r["board"],
            -r["_score_raw"],
        )
    )

    for row in to_add + reference:
        row.pop("_score_raw", None)

    write_csv(OUT_TO_ADD, to_add)
    write_csv(OUT_REFERENCE, reference)

    logger.info("Wrote %s rows to %s", len(to_add), OUT_TO_ADD)
    logger.info("Wrote %s rows to %s", len(reference), OUT_REFERENCE)

    by_board_action: dict[tuple[str, str], int] = {}
    for row in to_add:
        key = (row["board"], row["action"])
        by_board_action[key] = by_board_action.get(key, 0) + 1
    print("\n=== evals_to_add.csv summary ===")
    for (board, action), count in sorted(by_board_action.items()):
        print(f"  {board} / {action}: {count}")

    print("\n=== reconciliation spot-check ===")
    for arxiv_id in ("2401.02416", "2604.19609", "2204.07761"):
        matches = [r for r in to_add if r["arxiv_id"] == arxiv_id]
        for row in matches:
            print(
                f"  {row['board']}: {row['action']} {row['method_name']} "
                f"score={row['score']} existing={row['existing_score'] or '-'}"
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
