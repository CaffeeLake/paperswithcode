"""Dry-run-first, fill-only Hugging Face metadata backfill for evaluations.

This is deliberately a one-time operator command.  The daily paper-curation
workflow remains the owner of metadata for evaluations imported in the future.
"""

from __future__ import annotations

import argparse
import hashlib
import json

from huggingface_hub import HfApi
from sqlalchemy import func, select

from backend.config import get_settings
from backend.database.connection import db_manager
from backend.models.database import Evaluation, Paper
from backend.services.evaluation_hf_metadata_backfill import (
    EvaluationMetadataBackfill,
    EvaluationRow,
    apply_fill_only,
    verify_applied_fill_only,
    verify_sibling_consistency,
)


def _plan_payload(plan) -> dict:
    proposals = [
        {
            "evaluation_id": row_id,
            "hf_model_url": proposal.hf_model_url,
            "num_parameters": proposal.num_parameters,
        }
        for row_id, proposal in sorted(plan.proposals.items())
    ]
    payload = {
        "proposals": proposals,
        "sibling_url_conflicts": plan.sibling_url_conflicts,
        "sibling_count_conflicts": plan.sibling_count_conflicts,
        "ambiguous_matches": plan.ambiguous_matches,
        "unavailable_repositories": plan.unavailable_repositories,
        "missing_safetensors": plan.missing_safetensors,
        "unchanged_rows": plan.unchanged_rows,
    }
    payload["proposal_hash"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return payload


def _build_plan(session, *, max_lookups: int):
    rows: list[EvaluationRow] = []
    paper_hf_models: dict[int, list[str]] = {}
    statement = (
        select(Evaluation, Paper.hf_models)
        .join(Paper, Evaluation.paper_id == Paper.id)
        .where(Evaluation.model_name.is_not(None))
        .order_by(Evaluation.id)
    )
    for evaluation, hf_models in session.execute(statement):
        rows.append(
            EvaluationRow(
                id=evaluation.id,
                paper_id=evaluation.paper_id,
                model_name=evaluation.model_name,
                hf_model_url=evaluation.hf_model_url,
                num_parameters=evaluation.num_parameters,
                task_id=evaluation.task_id,
                dataset_id=evaluation.dataset_id,
                harness=evaluation.harness,
            )
        )
        paper_hf_models[evaluation.paper_id] = hf_models or []

    api = HfApi(token=get_settings().hf_token or None)

    def lookup(repo_id: str):
        return api.model_info(repo_id, timeout=10, expand=["safetensors"])

    return EvaluationMetadataBackfill(lookup, max_lookups=max_lookups).plan(
        rows, paper_hf_models
    )


def _coverage(session) -> dict[str, int]:
    total, with_url, with_count = session.execute(
        select(
            func.count(Evaluation.id),
            func.count(Evaluation.hf_model_url),
            func.count(Evaluation.num_parameters),
        )
    ).one()
    return {
        "total": total,
        "with_hf_model_url": with_url,
        "with_num_parameters": with_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Write the explicitly confirmed plan"
    )
    parser.add_argument(
        "--proposal-hash",
        help="Hash printed by a reviewed dry-run; required together with --apply",
    )
    parser.add_argument(
        "--max-lookups",
        type=int,
        default=250,
        help="Maximum distinct Hub repositories to inspect (default: 250)",
    )
    args = parser.parse_args()
    if args.max_lookups < 1:
        parser.error("--max-lookups must be positive")
    if args.apply and not args.proposal_hash:
        parser.error("--apply requires the reviewed --proposal-hash")
    if args.proposal_hash and not args.apply:
        parser.error("--proposal-hash is only valid with --apply")

    with db_manager.session_local() as session:
        plan = _build_plan(session, max_lookups=args.max_lookups)
        payload = _plan_payload(plan)
        if not args.apply:
            print(json.dumps({"mode": "dry-run", **payload}, indent=2, sort_keys=True))
            return
        if args.proposal_hash != payload["proposal_hash"]:
            parser.error("proposal hash does not match the current dry-run plan")

        rows_for_apply = {
            row.id: row
            for row in session.scalars(
                select(Evaluation).where(
                    Evaluation.id.in_(
                        row_id
                        for row_ids in plan.sibling_groups.values()
                        for row_id in row_ids
                    )
                )
            )
        }
        changed_ids = apply_fill_only(rows_for_apply, plan.proposals)
        session.flush()
        verify_applied_fill_only(rows_for_apply, plan.proposals)
        applied_groups = {
            group_id: row_ids
            for group_id, row_ids in plan.sibling_groups.items()
            if any(row_id in plan.proposals for row_id in row_ids)
        }
        verified_sibling_groups = verify_sibling_consistency(
            rows_for_apply, applied_groups
        )
        coverage = _coverage(session)
        session.commit()
        print(
            json.dumps(
                {
                    "mode": "applied",
                    "changed_evaluation_ids": changed_ids,
                    "verified_sibling_groups": verified_sibling_groups,
                    "aggregate_coverage": coverage,
                    **payload,
                },
                indent=2,
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
