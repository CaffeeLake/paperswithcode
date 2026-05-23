"""Build a reviewable evaluation manifest for the GIFT-Eval benchmark.

Streams the public ``Salesforce/GIFT-Eval`` Hugging Face Space, computes
per-model aggregate MASE / CRPS (geometric means standardized by
Seasonal_Naive) and average MASE / CRPS rank, and writes one row per
submitted model to ``data/gift_eval_evaluation_manifest.csv``.

The script is read-only at the database layer. It only resolves
``local_paper_id`` for ArXiv papers that are already present in our
``papers`` table; missing rows stay blank so the reviewer can decide
how to fill them. It does NOT add any evaluation rows or model paper
rows.

Memory profile: per-slice metrics are accumulated incrementally; only
the standardized metric values for the current ``(dataset, frequency,
horizon)`` slice (~88 rows of ~2 floats each) are held in RAM at a time.

Run with:

    uv run --env-file backend/keys.env \
        python backend/database/datasets_setup/build_gift_eval_manifest.py
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable

from sqlalchemy import text

from backend.database.connection import db_manager

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

HF_BASE = "https://huggingface.co"
SPACE_ID = "Salesforce/GIFT-Eval"
RANK_METRIC_MASE = "eval_metrics/MASE[0.5]"
RANK_METRIC_CRPS = "eval_metrics/mean_weighted_sum_quantile_loss"
SEASONAL_NAIVE_KEY = "Seasonal_Naive"

OUTPUT_PATH = Path("data/gift_eval_evaluation_manifest.csv")

# Manual paper resolution per submitted model. Resolutions were derived
# from each model's HF model card (when ``model_link`` points at the
# Hugging Face Hub) plus public web search for the rest. Values are
# either an arXiv id or a tuple ``("external", source_url)`` for models
# without a peer-reviewed paper. Keys are the ``model`` string used
# inside ``all_results.csv`` (which can differ slightly from the folder
# name on the Space, e.g. ``Auto_Arima`` vs folder ``auto_arima``).
PAPER_RESOLUTIONS: dict[str, tuple[str, str]] = {
    # arXiv-backed entries
    "Chronos_small": ("arxiv", "2403.07815"),
    "Chronos_base": ("arxiv", "2403.07815"),
    "Chronos_large": ("arxiv", "2403.07815"),
    "chronos_bolt_small": ("arxiv", "2403.07815"),
    "chronos_bolt_base": ("arxiv", "2403.07815"),
    "Chronos-2": ("arxiv", "2510.15821"),
    "Chronos-2-Synth": ("arxiv", "2510.15821"),
    "DLinear": ("arxiv", "2205.13504"),
    "FlowState-9.1M": ("arxiv", "2508.05287"),
    "FlowState-r1.1": ("arxiv", "2508.05287"),
    "Granite-FlowState-r1.1": ("arxiv", "2508.05287"),
    "Granite-PatchTST-FM-r1": ("arxiv", "2602.06909"),
    "PatchTST-FM-r1": ("arxiv", "2602.06909"),
    "PatchTST": ("arxiv", "2211.14730"),
    "Kairos_10m": ("arxiv", "2509.25826"),
    "Kairos_23m": ("arxiv", "2509.25826"),
    "Kairos_50m": ("arxiv", "2509.25826"),
    "Lag-Llama": ("arxiv", "2310.08278"),
    "Moirai2": ("arxiv", "2511.11698"),
    "Moirai_base": ("arxiv", "2402.02592"),
    "Moirai_large": ("arxiv", "2402.02592"),
    "Moirai_small": ("arxiv", "2402.02592"),
    "N-BEATS": ("arxiv", "1905.10437"),
    "Reverso": ("arxiv", "2602.17634"),
    "Reverso-Small": ("arxiv", "2602.17634"),
    "Reverso-Nano": ("arxiv", "2602.17634"),
    "STRIDE (+Chronos-2)": ("arxiv", "2605.08625"),
    "STRIDE (+Timer-S1)": ("arxiv", "2605.08625"),
    "Synapse": ("arxiv", "2511.05460"),
    "TSOrchestra": ("arxiv", "2512.16022"),
    "TSOrchestra-test": ("arxiv", "2310.04948"),
    "TTM-R1-Pretrained": ("arxiv", "2401.03955"),
    "TTM-R2-Finetuned": ("arxiv", "2401.03955"),
    "TTM-R2-Pretrained": ("arxiv", "2401.03955"),
    "TTM-R3-FT": ("arxiv", "2401.03955"),
    "TTM-R3-PT": ("arxiv", "2401.03955"),
    "TempoPFN": ("arxiv", "2510.25502"),
    "TiRex": ("arxiv", "2505.23719"),
    "TimeCopilot": ("arxiv", "2509.00616"),
    "Timer-S1": ("arxiv", "2603.04791"),
    "TimesFM-2.5": ("arxiv", "2310.10688"),
    "TimesFM": ("arxiv", "2310.10688"),
    "timesfm_2_0_500m": ("arxiv", "2310.10688"),
    "Toto-2.0-1B": ("arxiv", "2602.12147"),
    "Toto-2.0-2.5B": ("arxiv", "2602.12147"),
    "Toto-2.0-2.5B-FT": ("arxiv", "2602.12147"),
    "Toto-2.0-22m": ("arxiv", "2602.12147"),
    "Toto-2.0-313m": ("arxiv", "2602.12147"),
    "Toto-2.0-4m": ("arxiv", "2602.12147"),
    "Toto-2.0-FnF": ("arxiv", "2602.12147"),
    "Toto_Open_Base_1.0": ("arxiv", "2505.14766"),
    "VisionTS": ("arxiv", "2408.17253"),
    "Xihe-max": ("arxiv", "2510.21795"),
    "Xihe-ultra": ("arxiv", "2510.21795"),
    "YingLong_50m": ("arxiv", "2410.04803"),
    "YingLong_6m": ("arxiv", "2410.04803"),
    "YingLong_110m": ("arxiv", "2506.11029"),
    "YingLong_300m": ("arxiv", "2506.11029"),
    "ZooCast-Top1": ("arxiv", "2509.04208"),
    "DeepAR": ("arxiv", "1704.04110"),
    "iTransformer": ("arxiv", "2310.06625"),
    "TFT": ("arxiv", "1912.09363"),
    "TIDE": ("arxiv", "2304.08424"),
    "FLAIR": ("arxiv", "2605.07222"),
    "TabPFN-TS": ("arxiv", "2501.02945"),
    "TEMPO_ENSEMBLE": ("arxiv", "2310.04948"),
    "sundial_base_128m": ("arxiv", "2502.00816"),
    "xLSTM-Mixer": ("arxiv", "2410.16928"),
    "CleanTS-65M": ("external", "https://huggingface.co/EINK/CleanTS-65M"),
    "Credence": ("external", "https://app.credence.continualist.ai"),
    "DeOSAlphaTimeGPTPredictor-2025": (
        "external",
        "https://huggingface.co/vencortexio/DeOSAlphaTimeGPTPredictor-2025",
    ),
    "FFM": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/FFM/config.json",
    ),
    "Lingjiang": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/Lingjiang/config.json",
    ),
    "LongSeer-v1.0": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/LongSeer-v1.0/config.json",
    ),
    "Migas-1.0": (
        "external",
        "https://www.synthefy.com/blog/introducing-synthefy-migas",
    ),
    "MoiraiAgent": ("external", "https://huggingface.co/Salesforce/moirai-agent"),
    "MoiraiAgent-leaking": (
        "external",
        "https://huggingface.co/Salesforce/moirai-agent",
    ),
    "RAES-Conductance-Ensemble": (
        "external",
        "https://github.com/AriGoldbach/raes-gift-eval",
    ),
    "RAES-Conductance-Ensemble-V": (
        "external",
        "https://github.com/AriGoldbach/raes-conductance-v",
    ),
    "Samay": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/Samay/config.json",
    ),
    "VISIT-1.0": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/VISIT-1.0/config.json",
    ),
    "VISIT-2.0": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/VISIT-2.0/config.json",
    ),
    "Auto_Arima": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/auto_arima/config.json",
    ),
    "Auto_ETS": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/auto_ets/config.json",
    ),
    "Auto_Theta": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/results/auto_theta/config.json",
    ),
    "Crossformer": ("external", "https://openreview.net/forum?id=vSVLM2j9eie"),
    "Naive": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/notebooks/naive.ipynb",
    ),
    "Seasonal_Naive": (
        "external",
        "https://github.com/SalesforceAIResearch/gift-eval/blob/main/notebooks/naive.ipynb",
    ),
}


def _hf_url(path: str) -> str:
    return f"{HF_BASE}/spaces/{SPACE_ID}/raw/main/" + urllib.parse.quote(
        path, safe="/-_.()"
    )


def _fetch_text(path: str) -> str:
    with urllib.request.urlopen(_hf_url(path), timeout=30) as resp:
        return resp.read().decode("utf-8")


def _list_space_files() -> list[str]:
    api_url = f"{HF_BASE}/api/spaces/{SPACE_ID}"
    with urllib.request.urlopen(api_url, timeout=30) as resp:
        meta = json.load(resp)
    return [s["rfilename"] for s in meta.get("siblings", [])]


def _csv_value_to_float(value: str) -> float | None:
    if value in ("", "nan", "None"):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _stream_results_csv(path: str) -> Iterable[dict]:
    text_blob = _fetch_text(path)
    reader = csv.DictReader(io.StringIO(text_blob))
    folder = path.split("/")[1]
    for row in reader:
        ds_parts = (row.get("dataset") or "").split("/")
        row["_folder"] = folder
        row["_dataset"] = ds_parts[0] if len(ds_parts) > 0 else ""
        row["_frequency"] = ds_parts[1] if len(ds_parts) > 1 else ""
        row["_term_length"] = ds_parts[2] if len(ds_parts) > 2 else ""
        yield row


def _gmean(values: Iterable[float]) -> float | None:
    pos = [v for v in values if v is not None and v > 0 and math.isfinite(v)]
    if not pos:
        return None
    return math.exp(sum(math.log(v) for v in pos) / len(pos))


def _build_aggregates() -> dict[str, dict]:
    """Compute per-model standardized aggregates without holding all rows.

    The Space normalises every metric per ``(dataset, frequency, horizon)``
    slice by the Seasonal_Naive baseline. We replicate that here by
    streaming each model's ``all_results.csv`` once into per-slice
    buffers, then ranking each slice and updating per-model running
    aggregates before discarding the buffer.
    """
    files = _list_space_files()
    config_paths = [p for p in files if p.endswith("/config.json")]
    csv_paths = [p for p in files if p.endswith("/all_results.csv")]
    logger.info(
        "Discovered %d config.json files and %d all_results.csv files",
        len(config_paths),
        len(csv_paths),
    )

    # Folder -> config metadata, indexed by the folder name (which
    # matches the path component used in CSV downloads).
    configs: dict[str, dict] = {}
    for path in config_paths:
        cfg = json.loads(_fetch_text(path))
        cfg["_folder"] = path.split("/")[1]
        configs[cfg["_folder"]] = cfg

    # First pass: gather every (slice key, model) -> metric values.
    # Each slice has at most ~88 rows; we keep one slice in memory at a
    # time by streaming files but grouping on ``(dataset, freq, horizon)``.
    by_slice: dict[tuple[str, str, str], dict[str, dict[str, float | None]]] = (
        defaultdict(dict)
    )
    folder_to_models: dict[str, set[str]] = defaultdict(set)
    for path in csv_paths:
        for row in _stream_results_csv(path):
            key = (row["_dataset"], row["_frequency"], row["_term_length"])
            model = row.get("model") or row["_folder"]
            folder_to_models[row["_folder"]].add(model)
            by_slice[key][model] = {
                RANK_METRIC_MASE: _csv_value_to_float(row.get(RANK_METRIC_MASE, "")),
                RANK_METRIC_CRPS: _csv_value_to_float(row.get(RANK_METRIC_CRPS, "")),
            }

    # Second pass: for each slice, normalize by Seasonal_Naive, rank,
    # and feed running per-model aggregates.
    per_model: dict[str, dict] = defaultdict(
        lambda: {
            "eval_rows": 0,
            "mase_log_sum": 0.0,
            "mase_log_count": 0,
            "crps_log_sum": 0.0,
            "crps_log_count": 0,
            "mase_rank_sum": 0.0,
            "mase_rank_count": 0,
            "crps_rank_sum": 0.0,
            "crps_rank_count": 0,
        }
    )
    for slice_models in by_slice.values():
        baseline = slice_models.get(SEASONAL_NAIVE_KEY)
        if baseline is None:
            continue

        normalized: list[tuple[str, float | None, float | None]] = []
        for model, metrics in slice_models.items():
            mase = metrics.get(RANK_METRIC_MASE)
            crps = metrics.get(RANK_METRIC_CRPS)
            base_mase = baseline.get(RANK_METRIC_MASE)
            base_crps = baseline.get(RANK_METRIC_CRPS)
            mase_norm = (
                mase / base_mase
                if mase is not None and base_mase not in (None, 0)
                else None
            )
            crps_norm = (
                crps / base_crps
                if crps is not None and base_crps not in (None, 0)
                else None
            )
            normalized.append((model, mase_norm, crps_norm))

        # Rank the slice (lower is better; ties broken by index).
        for rank_idx, metric_idx in ((0, 1), (1, 2)):  # MASE col, CRPS col
            ranked = [
                (entry[metric_idx], i, entry[0])
                for i, entry in enumerate(normalized)
                if entry[metric_idx] is not None
            ]
            ranked.sort(key=lambda x: (x[0], x[1]))
            for rank, (_, _, model) in enumerate(ranked, start=1):
                if metric_idx == 1:
                    per_model[model]["mase_rank_sum"] += rank
                    per_model[model]["mase_rank_count"] += 1
                else:
                    per_model[model]["crps_rank_sum"] += rank
                    per_model[model]["crps_rank_count"] += 1

        # Feed running gmean aggregates.
        for model, mase_norm, crps_norm in normalized:
            agg = per_model[model]
            agg["eval_rows"] += 1
            if mase_norm is not None and mase_norm > 0 and math.isfinite(mase_norm):
                agg["mase_log_sum"] += math.log(mase_norm)
                agg["mase_log_count"] += 1
            if crps_norm is not None and crps_norm > 0 and math.isfinite(crps_norm):
                agg["crps_log_sum"] += math.log(crps_norm)
                agg["crps_log_count"] += 1

    # Finalise gmean / averages.
    finalized: dict[str, dict] = {}
    for model, agg in per_model.items():
        finalized[model] = {
            "eval_rows": agg["eval_rows"],
            "mase": (
                math.exp(agg["mase_log_sum"] / agg["mase_log_count"])
                if agg["mase_log_count"]
                else None
            ),
            "crps": (
                math.exp(agg["crps_log_sum"] / agg["crps_log_count"])
                if agg["crps_log_count"]
                else None
            ),
            "mase_rank_avg": (
                agg["mase_rank_sum"] / agg["mase_rank_count"]
                if agg["mase_rank_count"]
                else None
            ),
            "crps_rank_avg": (
                agg["crps_rank_sum"] / agg["crps_rank_count"]
                if agg["crps_rank_count"]
                else None
            ),
        }
    return {
        "configs": configs,
        "folder_to_models": folder_to_models,
        "per_model": finalized,
    }


def _resolve_local_paper_ids(arxiv_ids: set[str]) -> dict[str, int]:
    if not arxiv_ids:
        return {}
    with db_manager.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT arxiv_id, id FROM papers "
                "WHERE arxiv_id = ANY(:ids) AND is_latest_version"
            ),
            {"ids": list(arxiv_ids)},
        ).fetchall()
    return {arxiv: pid for arxiv, pid in rows}


def _format_float(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def main() -> None:
    snapshot = _build_aggregates()
    configs = snapshot["configs"]
    folder_to_models: dict[str, set[str]] = snapshot["folder_to_models"]
    per_model = snapshot["per_model"]

    arxiv_ids = {ref for kind, ref in PAPER_RESOLUTIONS.values() if kind == "arxiv"}
    local_paper_id_map = _resolve_local_paper_ids(arxiv_ids)

    rows: list[dict] = []
    skipped: list[str] = []
    seen_models: set[str] = set()
    for folder, cfg in sorted(configs.items()):
        # Each folder has exactly one model (per Space convention) but
        # the CSV ``model`` column is the canonical key.
        models = sorted(folder_to_models.get(folder, set()))
        if not models:
            skipped.append(folder)
            continue
        for model in models:
            if model in seen_models:
                continue
            seen_models.add(model)

            agg = per_model.get(model, {})
            resolution = PAPER_RESOLUTIONS.get(model)
            if resolution is None:
                paper_type = "unresolved"
                paper_ref = ""
                local_paper_id = ""
            elif resolution[0] == "arxiv":
                paper_type = "arxiv"
                paper_ref = resolution[1]
                local_paper_id = (
                    str(local_paper_id_map[paper_ref])
                    if paper_ref in local_paper_id_map
                    else ""
                )
            else:
                paper_type = "external"
                paper_ref = resolution[1]
                local_paper_id = ""

            rows.append(
                {
                    "model_name": model,
                    "folder": folder,
                    "paper_type": paper_type,
                    "paper_ref": paper_ref,
                    "local_paper_id": local_paper_id,
                    "MASE": _format_float(agg.get("mase"), 6),
                    "MASE_Rank": _format_float(agg.get("mase_rank_avg"), 3),
                    "CRPS": _format_float(agg.get("crps"), 6),
                    "CRPS_Rank": _format_float(agg.get("crps_rank_avg"), 3),
                    "raw_eval_rows": agg.get("eval_rows", 0),
                    "model_link": cfg.get("model_link", ""),
                    "model_type": cfg.get("model_type", ""),
                    "leakage": cfg.get("testdata_leakage", ""),
                    "replication_code": cfg.get("replication_code_available", ""),
                    "org": cfg.get("org", ""),
                }
            )

    # Sort by MASE ascending so the manifest is reviewer-friendly.
    rows.sort(
        key=lambda r: (
            float(r["MASE"]) if r["MASE"] else math.inf,
            r["model_name"],
        )
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "model_name",
                "folder",
                "paper_type",
                "paper_ref",
                "local_paper_id",
                "MASE",
                "MASE_Rank",
                "CRPS",
                "CRPS_Rank",
                "raw_eval_rows",
                "model_link",
                "model_type",
                "leakage",
                "replication_code",
                "org",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    logger.info(
        "Wrote %d rows to %s (skipped folders: %s, unresolved: %d)",
        len(rows),
        OUTPUT_PATH,
        ",".join(sorted(skipped)) or "<none>",
        sum(1 for r in rows if r["paper_type"] == "unresolved"),
    )


if __name__ == "__main__":
    main()
