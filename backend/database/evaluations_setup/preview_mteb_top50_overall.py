"""Read-only fetch of the MTEB (English) top-50 leaderboard with paper resolution.

Memory-safe for the 4GB VPS:

- Does NOT import the `mteb` package.
- Does NOT clone `embeddings-benchmark/results`.
- Does NOT download `__cached_results.json.gz` or per-task result files.
- Does NOT write to the database.

Important: the `mteb/leaderboard` Space defaults its dataframe to MMTEB
(Multilingual), so a naive scrape of `/config` returns the wrong scores for
the English benchmark. We drive the Space's Gradio API the same way the
browser does, identically to the sibling MMTEB script:

1. POST `/_update_value_1` -> simulates clicking the "English" button
   (dep `[[14, 'click']]`), which sets state 11 = "English" for our session.
2. POST `/on_benchmark_select` -> returns English defaults for tasks and
   languages (41 tasks, 1 language `eng`). Both come back as Gradio "update"
   dicts, so we extract `.value`.
3. POST `/update_tables` with `(tasks, languages)` -> returns three dataframes
   wrapped in update dicts. The first one's `.value` carries `headers` + `data`
   for the MTEB English leaderboard.

Everything else (per-row HF metadata calls, override resolution, local-paper
lookup, CSV manifests) is shared with `preview_mmteb_top50_overall.py`.

Usage:

    uv add gradio-client  # one-time
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/preview_mteb_top50_overall.py

Outputs are written under `_mteb_top50_preview/` next to this script.
"""

from __future__ import annotations

import csv
import json
import logging
import re
import resource
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

# Bump httpx defaults before importing gradio_client: the Space's `/config`
# response is ~2MB and the default 5s timeout on a cold worker is too tight,
# and `/update_tables` posts can take 20-30s on the hot path.
_orig_httpx_get = httpx.get
_orig_httpx_post = httpx.post


def _patched_httpx_get(url, *a, **k):  # type: ignore[no-untyped-def]
    k.setdefault("timeout", 120)
    return _orig_httpx_get(url, *a, **k)


def _patched_httpx_post(url, *a, **k):  # type: ignore[no-untyped-def]
    k.setdefault("timeout", 120)
    return _orig_httpx_post(url, *a, **k)


httpx.get = _patched_httpx_get  # type: ignore[assignment]
httpx.post = _patched_httpx_post  # type: ignore[assignment]

from gradio_client import Client  # noqa: E402  (after httpx monkey-patch)
from sqlalchemy import text  # noqa: E402

from backend.database.connection import get_engine  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("preview_mteb_top50_overall")

SPACE_ID = "mteb/leaderboard"
# /_update_value_1 corresponds to dep target [[14, 'click']] = "English" button.
BENCHMARK_BUTTON_API = "/_update_value_1"
BENCHMARK_SELECT_API = "/on_benchmark_select"
UPDATE_TABLES_API = "/update_tables"

HF_MODEL_API = "https://huggingface.co/api/models/{repo}"
HF_USER_AGENT = "paperswithcode-mteb-top50-fetch/1.0"
PREVIEW_DIR = Path(__file__).parent / "_mteb_top50_preview"

TOP_N = 50
SUMMARY_COLUMN = "Mean (Task)"
RANK_COLUMN = "Rank (Borda)"
MODEL_COLUMN = "Model"
METRIC_LABEL = "MTEB Score"

MAX_RSS_MB = 512


# Manual overrides for models whose HF metadata cannot be auto-resolved
# unambiguously (or that are non-HF). Keys are matched first by HF
# `owner/name` repo (when the leaderboard cell links to a HF model) and
# then by the leaderboard display name (for proprietary/non-HF entries).
#
# Each override is either:
#   {"kind": "arxiv", "arxiv_id": "YYMM.NNNNN"} — resolve via local
#     `papers` row by arxiv_id. If the local row is missing, the entry
#     is reported as `arxiv_pending_import` rather than skipped.
#   {"kind": "external", "title": "..."} — emit a candidate row that
#     will need a future external `papers` row with that title before
#     evaluation import. No DB write is done here.
#
# This map is shared with `preview_mmteb_top50_overall.py`; entries for
# models that don't appear in a given benchmark's top-50 are harmless.
MODEL_OVERRIDES: dict[str, dict[str, str]] = {
    "tencent/KaLM-Embedding-Gemma3-12B-2511": {
        "kind": "arxiv",
        "arxiv_id": "2506.20923",
    },
    "nvidia/llama-embed-nemotron-8b": {"kind": "arxiv", "arxiv_id": "2511.07025"},
    "intfloat/multilingual-e5-large-instruct": {
        "kind": "arxiv",
        "arxiv_id": "2402.05672",
    },
    "intfloat/multilingual-e5-large": {"kind": "arxiv", "arxiv_id": "2402.05672"},
    "intfloat/e5-mistral-7b-instruct": {"kind": "arxiv", "arxiv_id": "2401.00368"},
    "nvidia/NV-Embed-v2": {"kind": "arxiv", "arxiv_id": "2405.17428"},
    "NovaSearch/stella_en_1.5B_v5": {"kind": "arxiv", "arxiv_id": "2412.19048"},
    "gemini-embedding-001": {"kind": "arxiv", "arxiv_id": "2503.07891"},
    "embeddinggemma-300m": {"kind": "arxiv", "arxiv_id": "2509.20354"},
    "Linq-AI-Research/Linq-Embed-Mistral": {
        "kind": "external",
        "title": "Linq-Embed-Mistral",
    },
    "Salesforce/SFR-Embedding-Mistral": {
        "kind": "external",
        "title": "SFR-Embedding-Mistral",
    },
    "microsoft/harrier-oss-v1-27b": {"kind": "external", "title": "Microsoft Harrier"},
    "microsoft/harrier-oss-v1-0.6b": {"kind": "external", "title": "Microsoft Harrier"},
    "microsoft/harrier-oss-v1-270m": {"kind": "external", "title": "Microsoft Harrier"},
    # Disambiguate models whose HF model card declares multiple arXiv tags.
    "infgrad/Jasper-Token-Compression-600M": {
        "kind": "arxiv",
        "arxiv_id": "2511.14405",
    },
    "NovaSearch/stella_en_400M_v5": {"kind": "arxiv", "arxiv_id": "2412.19048"},
    "KaLM-Embedding/KaLM-embedding-multilingual-mini-instruct-v2.5": {
        "kind": "arxiv",
        "arxiv_id": "2506.20923",
    },
    "nvidia/NV-Embed-v1": {"kind": "arxiv", "arxiv_id": "2405.17428"},
    "avsolatorio/GIST-large-Embedding-v0": {"kind": "arxiv", "arxiv_id": "2402.16829"},
}


def peak_rss_mb() -> float:
    """Peak resident set size in MiB. Linux reports ru_maxrss in KiB."""
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def assert_memory_ok(stage: str) -> None:
    rss = peak_rss_mb()
    logger.info("Peak RSS at %s: %.1f MiB", stage, rss)
    if rss > MAX_RSS_MB:
        logger.error(
            "Aborting: peak RSS %.1f MiB exceeds guardrail %d MiB at stage %s",
            rss,
            MAX_RSS_MB,
            stage,
        )
        sys.exit(2)


def _unwrap(update: Any) -> Any:
    """Return `.value` from a Gradio "update" dict, or the input unchanged."""
    if isinstance(update, dict) and "value" in update:
        return update["value"]
    return update


def fetch_top_rows() -> list[dict[str, Any]]:
    """Drive the Space's Gradio API to fetch the MTEB English top-N leaderboard rows.

    Explicitly clicks the "English" button before requesting the table so we
    do NOT inherit whatever default benchmark the Space currently ships with
    (which has historically been Multilingual / MMTEB).
    """
    logger.info("Opening Gradio client for Space: %s", SPACE_ID)
    client = Client(SPACE_ID, download_files=False)

    logger.info("Clicking the English benchmark button (%s)", BENCHMARK_BUTTON_API)
    client.predict(api_name=BENCHMARK_BUTTON_API)

    logger.info(
        "Fetching MTEB English task/language defaults (%s)", BENCHMARK_SELECT_API
    )
    bench = client.predict(api_name=BENCHMARK_SELECT_API)
    if not isinstance(bench, (list, tuple)) or len(bench) < 5:
        sys.exit(
            f"Unexpected on_benchmark_select return shape: "
            f"{type(bench).__name__} len={len(bench) if hasattr(bench, '__len__') else 'n/a'}"
        )
    # Output ordering from /config dep 118 is [3, 5, 4, 7, 6, 82, 113, 83, 127, ...].
    # Index 0 -> languages (comp 3), Index 4 -> tasks (comp 6).
    languages = _unwrap(bench[0])
    tasks = _unwrap(bench[4])
    if not isinstance(tasks, list) or not isinstance(languages, list):
        sys.exit(
            f"Unexpected MTEB English defaults: tasks={type(tasks).__name__}, "
            f"languages={type(languages).__name__}"
        )
    logger.info(
        "MTEB English defaults: %d tasks, %d languages",
        len(tasks),
        len(languages),
    )

    logger.info("Requesting full leaderboard table (%s)", UPDATE_TABLES_API)
    tables = client.predict(tasks, languages, api_name=UPDATE_TABLES_API)
    if not isinstance(tables, (list, tuple)) or not tables:
        sys.exit(f"Unexpected update_tables return: {type(tables).__name__}")
    df = _unwrap(tables[0])
    if not isinstance(df, dict):
        sys.exit(f"Unexpected leaderboard dataframe shape: {type(df).__name__}")
    headers = df.get("headers") or []
    data = df.get("data") or []
    for required in (RANK_COLUMN, MODEL_COLUMN, SUMMARY_COLUMN):
        if required not in headers:
            sys.exit(
                f"Expected column {required!r} missing from leaderboard; got: {headers}"
            )

    top_rows = data[:TOP_N]
    rows = [dict(zip(headers, row)) for row in top_rows]

    del client, bench, tables, df, headers, data, top_rows, tasks, languages
    return rows


MODEL_MD_RE = re.compile(r"\[(?P<name>.*?)\]\((?P<url>.*?)\)")


def parse_model_cell(cell: str) -> tuple[str, str]:
    """Pull the model display name and target URL out of the cell markdown."""
    m = MODEL_MD_RE.match(cell or "")
    if m:
        return m.group("name").strip(), m.group("url").strip()
    return (cell or "").strip(), ""


def extract_hf_repo(url: str) -> str | None:
    """Return `owner/name` if this points at a Hugging Face model repo."""
    if not url.startswith("https://huggingface.co/"):
        return None
    parts = url[len("https://huggingface.co/") :].split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def fetch_hf_arxiv_tags(repo: str) -> list[str]:
    """Return arXiv ids declared in the model's tags. One request per model."""
    url = HF_MODEL_API.format(repo=urllib.parse.quote(repo, safe="/"))
    req = urllib.request.Request(url, headers={"User-Agent": HF_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            info = json.load(resp)
    except urllib.error.HTTPError as exc:
        logger.warning("HF metadata HTTP %s for %s", exc.code, repo)
        return []
    except urllib.error.URLError as exc:
        logger.warning("HF metadata fetch failed for %s: %s", repo, exc)
        return []

    tags = info.get("tags") or []
    arxiv = []
    for tag in tags:
        if not isinstance(tag, str) or not tag.startswith("arxiv:"):
            continue
        candidate = tag.split(":", 1)[1].strip()
        if re.fullmatch(r"\d{4}\.\d{4,5}", candidate):
            arxiv.append(candidate)

    del info, tags
    return arxiv


@dataclass
class Candidate:
    rank: str
    model_name: str
    model_url: str
    score: float
    resolution: str  # local_arxiv | arxiv_pending_import | external_pending
    arxiv_id: str
    paper_id: str  # int as str (or "" when not yet known)
    paper_title: str


@dataclass
class Skipped:
    rank: str
    model_name: str
    model_url: str
    reason: str


def resolve_local_papers(arxiv_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Look up local `papers` rows for the given arXiv ids in a single query."""
    if not arxiv_ids:
        return {}
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT arxiv_id, id, title "
                "FROM papers "
                "WHERE arxiv_id = ANY(:ids) AND is_latest_version"
            ),
            {"ids": sorted(arxiv_ids)},
        ).fetchall()
    return {r._mapping["arxiv_id"]: dict(r._mapping) for r in rows}


def build_manifest() -> tuple[list[Candidate], list[Skipped]]:
    """Fetch the MTEB English top-N leaderboard and resolve papers.

    Memory-safe by construction (see module docstring). Used both by this
    script's CSV writer and by the downstream importer so the two paths
    cannot drift.
    """
    assert_memory_ok("startup")

    rows = fetch_top_rows()
    logger.info("Fetched %d top-N leaderboard rows", len(rows))
    assert_memory_ok("post-config")

    parsed: list[dict[str, Any]] = []
    for row in rows:
        rank = row.get(RANK_COLUMN)
        model_name, model_url = parse_model_cell(row.get(MODEL_COLUMN) or "")
        score = row.get(SUMMARY_COLUMN)
        parsed.append(
            {
                "rank": str(rank) if rank is not None else "",
                "model_name": model_name,
                "model_url": model_url,
                "score": score,
            }
        )

    override_by_idx: dict[int, dict[str, str]] = {}
    repos_to_check: list[tuple[int, str]] = []
    for idx, p in enumerate(parsed):
        repo = extract_hf_repo(p["model_url"])
        override = None
        if repo is not None and repo in MODEL_OVERRIDES:
            override = MODEL_OVERRIDES[repo]
        elif p["model_name"] in MODEL_OVERRIDES:
            override = MODEL_OVERRIDES[p["model_name"]]
        if override is not None:
            override_by_idx[idx] = override
            continue
        if repo is not None:
            repos_to_check.append((idx, repo))

    arxiv_by_idx: dict[int, list[str]] = {}
    for idx, repo in repos_to_check:
        tags = fetch_hf_arxiv_tags(repo)
        arxiv_by_idx[idx] = tags
        time.sleep(0.1)
    assert_memory_ok("post-hf-metadata")

    all_arxiv: set[str] = set()
    for tags in arxiv_by_idx.values():
        all_arxiv.update(tags)
    for override in override_by_idx.values():
        if override["kind"] == "arxiv":
            all_arxiv.add(override["arxiv_id"])
    local_by_arxiv = resolve_local_papers(all_arxiv)
    logger.info(
        "Looked up %d unique arXiv ids, %d found locally",
        len(all_arxiv),
        len(local_by_arxiv),
    )

    candidates: list[Candidate] = []
    skipped: list[Skipped] = []

    repo_index = {idx for idx, _ in repos_to_check}
    for idx, p in enumerate(parsed):
        rank = p["rank"]
        name = p["model_name"]
        url = p["model_url"]
        score = p["score"]

        if not isinstance(score, (int, float)):
            skipped.append(
                Skipped(rank, name, url, f"No numeric overall score (value={score!r})")
            )
            continue

        override = override_by_idx.get(idx)
        if override is not None:
            if override["kind"] == "arxiv":
                arxiv_id = override["arxiv_id"]
                paper = local_by_arxiv.get(arxiv_id)
                if paper is not None:
                    candidates.append(
                        Candidate(
                            rank=rank,
                            model_name=name,
                            model_url=url,
                            score=float(score),
                            resolution="local_arxiv",
                            arxiv_id=arxiv_id,
                            paper_id=str(int(paper["id"])),
                            paper_title=str(paper["title"]),
                        )
                    )
                else:
                    candidates.append(
                        Candidate(
                            rank=rank,
                            model_name=name,
                            model_url=url,
                            score=float(score),
                            resolution="arxiv_pending_import",
                            arxiv_id=arxiv_id,
                            paper_id="",
                            paper_title="",
                        )
                    )
                continue
            if override["kind"] == "external":
                candidates.append(
                    Candidate(
                        rank=rank,
                        model_name=name,
                        model_url=url,
                        score=float(score),
                        resolution="external_pending",
                        arxiv_id="",
                        paper_id="",
                        paper_title=override["title"],
                    )
                )
                continue

        if idx not in repo_index:
            skipped.append(Skipped(rank, name, url, "Non-HF or proprietary model URL"))
            continue

        tags = arxiv_by_idx.get(idx, [])
        if not tags:
            skipped.append(Skipped(rank, name, url, "No arxiv: tags on HF model card"))
            continue

        matched = [a for a in tags if a in local_by_arxiv]
        if not matched:
            skipped.append(
                Skipped(
                    rank,
                    name,
                    url,
                    f"No local paper matches arxiv tags ({','.join(tags)})",
                )
            )
            continue
        if len(matched) > 1:
            skipped.append(
                Skipped(
                    rank,
                    name,
                    url,
                    f"Ambiguous: multiple local papers match arxiv tags "
                    f"({','.join(matched)})",
                )
            )
            continue

        arxiv_id = matched[0]
        paper = local_by_arxiv[arxiv_id]
        candidates.append(
            Candidate(
                rank=rank,
                model_name=name,
                model_url=url,
                score=float(score),
                resolution="local_arxiv",
                arxiv_id=arxiv_id,
                paper_id=str(int(paper["id"])),
                paper_title=str(paper["title"]),
            )
        )

    return candidates, skipped


def main() -> None:
    PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Writing manifests to %s", PREVIEW_DIR)

    candidates, skipped = build_manifest()

    candidates_path = PREVIEW_DIR / "mteb_top50_candidates.csv"
    skipped_path = PREVIEW_DIR / "mteb_top50_skipped.csv"

    with candidates_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "rank",
                "model_name",
                "model_url",
                "score",
                "metric_label",
                "resolution",
                "arxiv_id",
                "paper_id",
                "paper_title",
                "paper_url",
            ]
        )
        for c in candidates:
            if c.resolution == "local_arxiv":
                paper_url = f"https://paperswithcode.co/paper/{c.arxiv_id}"
            elif c.resolution == "arxiv_pending_import":
                paper_url = f"https://arxiv.org/abs/{c.arxiv_id}"
            else:
                paper_url = ""
            writer.writerow(
                [
                    c.rank,
                    c.model_name,
                    c.model_url,
                    f"{c.score:.4f}",
                    METRIC_LABEL,
                    c.resolution,
                    c.arxiv_id,
                    c.paper_id,
                    c.paper_title,
                    paper_url,
                ]
            )

    with skipped_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["rank", "model_name", "model_url", "reason"])
        for s in skipped:
            writer.writerow([s.rank, s.model_name, s.model_url, s.reason])

    total = len(candidates) + len(skipped)
    n_cand = len(candidates)
    n_local = sum(1 for c in candidates if c.resolution == "local_arxiv")
    n_pending_arxiv = sum(
        1 for c in candidates if c.resolution == "arxiv_pending_import"
    )
    n_external = sum(1 for c in candidates if c.resolution == "external_pending")
    n_skip = len(skipped)
    n_ambig = sum(1 for s in skipped if s.reason.startswith("Ambiguous"))

    print()
    print("=== MTEB English Overall Top-50 read-only fetch ===")
    print(f"Source: https://huggingface.co/spaces/{SPACE_ID} (English)")
    print(f"Rows fetched: {total} (expected up to {TOP_N})")
    print(
        f"Candidate eval rows: {n_cand} "
        f"(local_arxiv={n_local}, arxiv_pending_import={n_pending_arxiv}, "
        f"external_pending={n_external})"
    )
    print(f"Skipped rows: {n_skip} (ambiguous: {n_ambig})")
    print("Outputs:")
    print(f"  {candidates_path}")
    print(f"  {skipped_path}")

    if candidates:
        print()
        print("Candidates:")
        print("rank\tscore\tresolution\tarxiv\tpaper_id\tmodel_name\tpaper_title")
        for c in candidates:
            print(
                f"{c.rank}\t{c.score:.2f}\t{c.resolution}\t{c.arxiv_id or '-'}\t"
                f"{c.paper_id or '-'}\t{c.model_name}\t{c.paper_title}"
            )

    if skipped:
        print()
        print("Skipped:")
        print("rank\tmodel_name\treason")
        for s in skipped:
            print(f"{s.rank}\t{s.model_name}\t{s.reason}")

    assert_memory_ok("end")


if __name__ == "__main__":
    main()
