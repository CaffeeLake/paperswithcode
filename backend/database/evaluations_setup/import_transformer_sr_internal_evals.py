"""Import internal transformer image super-resolution evals.

This curation pass is anchored by arXiv:2501.07855's survey table, but only
imports rows from each model's own paper. Comparator columns remain excluded.

Run:
    uv run --env-file backend/keys.env python \
        backend/database/evaluations_setup/import_transformer_sr_internal_evals.py
"""

from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from sqlalchemy import text

from backend.database.connection import get_database_session
from backend.models.database import Dataset as DBDataset
from backend.services.evaluation_service import EvaluationService

TASK_ID = 314
TASK_SLUG = "image-super-resolution"
PSNR = "PSNR"
SSIM = "SSIM"

PARENTS = {
    "set5": 748,
    "set14": 749,
    "bsd100": 750,
    "urban100": 751,
    "manga109": 752,
}

MISSING_PAPERS = [
    "2108.11084",  # ESRT
    "2112.10175",  # EDT
    "2210.01427",  # ART
]


@dataclass(frozen=True)
class EvalRow:
    arxiv_id: str
    model_name: str
    scale: str
    dataset_key: str
    psnr: str
    ssim: str | None
    methodology: str
    num_parameters: int | None = None


ROWS: list[EvalRow] = [
    # IPT, Table 1. IPT reports PSNR only.
    *[
        EvalRow(
            "2012.00364",
            "IPT",
            scale,
            dataset,
            psnr,
            None,
            "Internal result from IPT Table 1; classical SR on Y channel.",
        )
        for scale, vals in {
            "2x": {
                "set5": "38.37",
                "set14": "34.43",
                "bsd100": "32.48",
                "urban100": "33.76",
            },
            "3x": {
                "set5": "34.81",
                "set14": "30.85",
                "bsd100": "29.38",
                "urban100": "29.49",
            },
            "4x": {
                "set5": "32.64",
                "set14": "29.01",
                "bsd100": "27.82",
                "urban100": "27.26",
            },
        }.items()
        for dataset, psnr in vals.items()
    ],
    # SwinIR, Table 2. Existing x2 rows are updated with SSIM; x3/x4 rows are added.
    *[
        EvalRow(
            "2108.10257",
            "SwinIR",
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from SwinIR Table 2; classical SR, average PSNR/SSIM on Y channel.",
            11_900_000,
        )
        for scale, vals in {
            "2x": {
                "set5": ("38.42", "0.9623"),
                "set14": ("34.46", "0.9250"),
                "bsd100": ("32.53", "0.9041"),
                "urban100": ("33.81", "0.9427"),
                "manga109": ("39.92", "0.9797"),
            },
            "3x": {
                "set5": ("34.97", "0.9318"),
                "set14": ("30.93", "0.8534"),
                "bsd100": ("29.46", "0.8145"),
                "urban100": ("29.75", "0.8826"),
                "manga109": ("35.12", "0.9537"),
            },
            "4x": {
                "set5": ("32.92", "0.9044"),
                "set14": ("29.09", "0.7950"),
                "bsd100": ("27.92", "0.7489"),
                "urban100": ("27.45", "0.8254"),
                "manga109": ("32.03", "0.9260"),
            },
        }.items()
        for dataset, (psnr, ssim) in vals.items()
    ],
    # EDT-B†, Table 4. This is the paper's best eligible main model row.
    *[
        EvalRow(
            "2112.10175",
            "EDT-B†",
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from EDT Table 4; pre-trained EDT-B†, PSNR/SSIM on Y channel.",
            11_600_000 if scale == "4x" else 11_500_000,
        )
        for scale, vals in {
            "2x": {
                "set5": ("38.63", "0.9632"),
                "set14": ("34.80", "0.9273"),
                "bsd100": ("32.62", "0.9052"),
                "urban100": ("34.27", "0.9456"),
                "manga109": ("40.37", "0.9811"),
            },
            "3x": {
                "set5": ("35.13", "0.9328"),
                "set14": ("31.09", "0.8553"),
                "bsd100": ("29.53", "0.8165"),
                "urban100": ("30.07", "0.8863"),
                "manga109": ("35.47", "0.9550"),
            },
            "4x": {
                "set5": ("33.06", "0.9055"),
                "set14": ("29.23", "0.7971"),
                "bsd100": ("27.99", "0.7510"),
                "urban100": ("27.75", "0.8317"),
                "manga109": ("32.39", "0.9283"),
            },
        }.items()
        for dataset, (psnr, ssim) in vals.items()
    ],
    # HAT-L, Table 6. Existing PSNR rows are updated with SSIM.
    *[
        EvalRow(
            "2205.04437",
            "HAT-L",
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from HAT Table 6; classical SR, PSNR/SSIM on Y channel.",
        )
        for scale, vals in {
            "2x": {
                "set5": ("38.91", "0.9646"),
                "set14": ("35.29", "0.9293"),
                "bsd100": ("32.74", "0.9066"),
                "urban100": ("35.09", "0.9505"),
                "manga109": ("41.01", "0.9831"),
            },
            "4x": {
                "set5": ("33.30", "0.9083"),
                "set14": ("29.47", "0.8015"),
                "bsd100": ("28.09", "0.7551"),
                "urban100": ("28.60", "0.8498"),
                "manga109": ("33.09", "0.9335"),
            },
        }.items()
        for dataset, (psnr, ssim) in vals.items()
    ],
    # ART, Table 2. Main ART row; ART-S and ART+ are left out to avoid variant sprawl.
    *[
        EvalRow(
            "2210.01427",
            "ART",
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from ART Table 2; main ART model, PSNR/SSIM on Y channel.",
            16_550_000,
        )
        for scale, vals in {
            "2x": {
                "set5": ("38.56", "0.9629"),
                "set14": ("34.59", "0.9267"),
                "bsd100": ("32.58", "0.9048"),
                "urban100": ("34.30", "0.9452"),
                "manga109": ("40.24", "0.9808"),
            },
            "3x": {
                "set5": ("35.07", "0.9325"),
                "set14": ("31.02", "0.8541"),
                "bsd100": ("29.51", "0.8159"),
                "urban100": ("30.10", "0.8871"),
                "manga109": ("35.39", "0.9548"),
            },
            "4x": {
                "set5": ("33.04", "0.9051"),
                "set14": ("29.16", "0.7958"),
                "bsd100": ("27.97", "0.7510"),
                "urban100": ("27.77", "0.8321"),
                "manga109": ("32.31", "0.9283"),
            },
        }.items()
        for dataset, (psnr, ssim) in vals.items()
    ],
    # DAT/DAT+ own rows, Table 2. Existing rows are updated with SSIM; x3 rows are added.
    *[
        EvalRow(
            "2308.03364",
            model,
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from DAT Table 2; classical SR, PSNR/SSIM on Y channel.",
        )
        for scale, model, vals in [
            (
                "2x",
                "DAT+",
                {
                    "set5": ("38.63", "0.9631"),
                    "set14": ("34.86", "0.9274"),
                    "bsd100": ("32.63", "0.9053"),
                    "urban100": ("34.47", "0.9465"),
                    "manga109": ("40.43", "0.9809"),
                },
            ),
            (
                "3x",
                "DAT+",
                {
                    "set5": ("35.19", "0.9334"),
                    "set14": ("31.17", "0.8558"),
                    "bsd100": ("29.58", "0.8173"),
                    "urban100": ("30.30", "0.8902"),
                    "manga109": ("35.72", "0.9559"),
                },
            ),
            (
                "4x",
                "DAT+",
                {
                    "set5": ("33.15", "0.9062"),
                    "set14": ("29.29", "0.7983"),
                    "bsd100": ("28.03", "0.7518"),
                    "urban100": ("27.99", "0.8365"),
                    "manga109": ("32.67", "0.9301"),
                },
            ),
        ]
        for dataset, (psnr, ssim) in vals.items()
    ],
    # DRCT-L, Table 1. Existing rows are updated with SSIM; missing x3/x4 rows are added.
    *[
        EvalRow(
            "2404.00722",
            "DRCT-L",
            scale,
            dataset,
            psnr,
            ssim,
            "Internal result from DRCT Table 1; DRCT-L with progressive training, PSNR/SSIM on Y channel.",
            10_443_000,
        )
        for scale, vals in {
            "2x": {
                "set5": ("39.82", "0.9644"),
                "set14": ("35.24", "0.9284"),
                "bsd100": ("32.76", "0.9068"),
                "urban100": ("35.11", "0.9506"),
                "manga109": ("40.94", "0.9828"),
            },
            "3x": {
                "set5": ("35.32", "0.9348"),
                "set14": ("31.54", "0.8591"),
                "bsd100": ("29.68", "0.8211"),
                "urban100": ("31.14", "0.9004"),
                "manga109": ("36.16", "0.9585"),
            },
            "4x": {
                "set5": ("33.37", "0.9090"),
                "set14": ("29.54", "0.8025"),
                "bsd100": ("28.16", "0.7577"),
                "urban100": ("28.70", "0.8508"),
                "manga109": ("33.14", "0.9347"),
            },
        }.items()
        for dataset, (psnr, ssim) in vals.items()
    ],
]


def slug_for(dataset_key: str, scale: str) -> str:
    return f"{dataset_key}-{scale}-upscaling"


def normalize_arxiv_version(value: str | None) -> str:
    if not value:
        return "v1"
    match = re.search(r"v\d+$", value)
    return match.group(0) if match else "v1"


def fetch_arxiv_metadata(arxiv_id: str) -> dict[str, object]:
    url = "https://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id}
    )
    with urllib.request.urlopen(url, timeout=30) as response:
        root = ET.fromstring(response.read())
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise RuntimeError(f"arXiv metadata not found for {arxiv_id}")
    title = " ".join(
        (entry.findtext("atom:title", default="", namespaces=ns) or "").split()
    )
    abstract = " ".join(
        (entry.findtext("atom:summary", default="", namespaces=ns) or "").split()
    )
    published = entry.findtext("atom:published", namespaces=ns)
    date_published = dt.date.fromisoformat(published[:10]) if published else None
    version = normalize_arxiv_version(entry.findtext("atom:id", namespaces=ns))
    primary_category = None
    primary = entry.find("arxiv:primary_category", ns)
    if primary is not None:
        primary_category = primary.attrib.get("term")
    categories = [
        cat.attrib["term"]
        for cat in entry.findall("atom:category", ns)
        if cat.attrib.get("term")
    ]
    return {
        "title": title,
        "abstract": abstract,
        "date_published": date_published,
        "version": version,
        "primary_category": primary_category,
        "all_categories": categories,
    }


def ensure_paper(db, arxiv_id: str) -> int:
    row = (
        db.execute(
            text(
                "SELECT id FROM papers WHERE arxiv_id = :a ORDER BY is_latest_version DESC NULLS LAST, id DESC LIMIT 1"
            ),
            {"a": arxiv_id},
        )
        .mappings()
        .first()
    )
    if row:
        return int(row["id"])

    meta = fetch_arxiv_metadata(arxiv_id)
    paper_id = db.execute(
        text(
            """
            INSERT INTO papers (
                title, abstract, arxiv_id, version, is_latest_version,
                date_published, source, primary_category, all_categories,
                urls_extracted, created_at, updated_at
            )
            VALUES (
                :title, :abstract, :arxiv_id, :version, TRUE,
                :date_published, 'arxiv', :primary_category, :all_categories,
                FALSE, NOW(), NOW()
            )
            RETURNING id
            """
        ),
        {"arxiv_id": arxiv_id, **meta},
    ).scalar_one()
    return int(paper_id)


def ensure_task_tag(db, paper_id: int) -> None:
    db.execute(
        text(
            """
            INSERT INTO paper_tasks (paper_id, task_id, source)
            VALUES (:p, :t, 'manual')
            ON CONFLICT (paper_id, task_id)
            DO UPDATE SET source = 'manual'
            """
        ),
        {"p": paper_id, "t": TASK_ID},
    )


def ensure_scale_dataset(db, dataset_key: str, scale: str) -> int:
    slug = slug_for(dataset_key, scale)
    row = (
        db.execute(text("SELECT id FROM datasets WHERE slug = :slug"), {"slug": slug})
        .mappings()
        .first()
    )
    if row:
        return int(row["id"])

    parent = db.query(DBDataset).filter(DBDataset.id == PARENTS[dataset_key]).one()
    name = f"{parent.name} - {scale} upscaling"
    description = (
        f"{parent.name} benchmark for image super-resolution at {scale} upscaling. "
        "Results are comparable only within the same scale factor."
    )
    dataset = DBDataset(
        name=name,
        slug=slug,
        description=description,
        hf_url=parent.hf_url,
        homepage=parent.homepage,
        paper_url=parent.paper_url,
        introducing_paper_id=parent.introducing_paper_id,
        introducing_paper_title=parent.introducing_paper_title,
        introduced_year=parent.introduced_year,
        parent_dataset_id=parent.id,
        variant_type="variant",
        split_name=f"{scale} upscaling",
    )
    db.add(dataset)
    db.flush()
    return int(dataset.id)


def ensure_metric_links(db, dataset_id: int, metric_ids: dict[str, int]) -> None:
    db.execute(
        text(
            """
            INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
            VALUES (:t, :d, FALSE)
            ON CONFLICT (task_id, dataset_id) DO NOTHING
            """
        ),
        {"t": TASK_ID, "d": dataset_id},
    )
    for metric_id in metric_ids.values():
        db.execute(
            text(
                """
                INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
                VALUES (:t, :d, :m)
                ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING
                """
            ),
            {"t": TASK_ID, "d": dataset_id, "m": metric_id},
        )


def upsert_eval(
    db, service: EvaluationService, paper_id: int, dataset_id: int, row: EvalRow
) -> tuple[str, int]:
    metrics = {PSNR: row.psnr}
    if row.ssim is not None:
        metrics[SSIM] = row.ssim

    model_candidates = [row.model_name]
    if row.arxiv_id == "2205.04437" and row.model_name == "HAT-L":
        model_candidates.append("HAT-L†")

    existing = (
        db.execute(
            text(
                """
            SELECT id, metrics
            FROM evaluations
            WHERE paper_id = :p AND task_id = :t AND dataset_id = :d
              AND model_name = ANY(:models)
              AND COALESCE(harness, '') = ''
              AND best_metric = :metric
            ORDER BY CASE WHEN model_name = :model THEN 0 ELSE 1 END
            LIMIT 1
            """
            ),
            {
                "p": paper_id,
                "t": TASK_ID,
                "d": dataset_id,
                "model": row.model_name,
                "models": model_candidates,
                "metric": PSNR,
            },
        )
        .mappings()
        .first()
    )
    source_url = f"https://arxiv.org/abs/{row.arxiv_id}"
    if existing:
        merged = dict(existing["metrics"] or {})
        changed = False
        for key, value in metrics.items():
            if str(merged.get(key)) != str(value):
                merged[key] = value
                changed = True
        if changed:
            db.execute(
                text(
                    """
                    UPDATE evaluations
                    SET metrics = CAST(:metrics AS jsonb),
                        methodology = :methodology,
                        source_url = COALESCE(source_url, :source_url),
                        external_source_url = COALESCE(external_source_url, :source_url),
                        num_parameters = COALESCE(num_parameters, :num_parameters),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing["id"],
                    "metrics": json.dumps(merged),
                    "methodology": row.methodology,
                    "source_url": source_url,
                    "num_parameters": row.num_parameters,
                },
            )
            for metric in merged:
                service.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)
            return "updated", int(existing["id"])
        return "unchanged", int(existing["id"])

    created = service.create_evaluation(
        paper_id=paper_id,
        task_id=TASK_ID,
        dataset_id=dataset_id,
        model_name=row.model_name,
        methodology=row.methodology,
        metrics=metrics,
        best_metric=PSNR,
        external_source_url=source_url,
        num_parameters=row.num_parameters,
        is_open=True,
    )
    return "created", int(created.id)


def main() -> None:
    db = next(get_database_session())
    created = updated = unchanged = 0
    touched: set[tuple[int, str]] = set()
    try:
        metric_ids = {
            r["name"]: int(r["id"])
            for r in db.execute(
                text("SELECT id, name FROM metrics WHERE name IN ('PSNR', 'SSIM')")
            ).mappings()
        }
        if set(metric_ids) != {PSNR, SSIM}:
            raise RuntimeError(f"Missing metrics: {metric_ids}")

        paper_ids = {}
        for arxiv_id in sorted({row.arxiv_id for row in ROWS} | set(MISSING_PAPERS)):
            paper_id = ensure_paper(db, arxiv_id)
            ensure_task_tag(db, paper_id)
            paper_ids[arxiv_id] = paper_id

        dataset_ids = {}
        for dataset_key in PARENTS:
            for scale in ("2x", "3x", "4x"):
                did = ensure_scale_dataset(db, dataset_key, scale)
                ensure_metric_links(db, did, metric_ids)
                dataset_ids[(dataset_key, scale)] = did

        db.commit()

        service = EvaluationService(db)
        for row in ROWS:
            dataset_id = dataset_ids[(row.dataset_key, row.scale)]
            status, eval_id = upsert_eval(
                db, service, paper_ids[row.arxiv_id], dataset_id, row
            )
            if status == "created":
                created += 1
            elif status == "updated":
                updated += 1
            else:
                unchanged += 1
            touched.add((dataset_id, PSNR))
            if row.ssim is not None:
                touched.add((dataset_id, SSIM))
            print(
                status,
                eval_id,
                row.arxiv_id,
                row.model_name,
                slug_for(row.dataset_key, row.scale),
                row.psnr,
                row.ssim,
            )

        db.commit()
        for dataset_id, metric in sorted(touched):
            service.recalculate_ranks(TASK_ID, dataset_id, metric_name=metric)
        db.commit()
        print(
            f"summary created={created} updated={updated} unchanged={unchanged} touched={len(touched)}"
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
