#!/usr/bin/env python3
"""Synchronize the strict featured-organization manifest from Hugging Face.

Examples:
  uv run --env-file backend/keys.env python \
    backend/database/organizations_setup/import_hf_organization.py --dry-run
  uv run --env-file backend/keys.env python \
    backend/database/organizations_setup/import_hf_organization.py \
    --organization nvidia
"""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.database.connection import db_manager
from backend.database.organizations_setup.organizations import (
    BY_PWC_SLUG,
    FEATURED_ORGANIZATIONS,
)
from backend.services.organization_sync_service import OrganizationSyncService


async def run(args: argparse.Namespace) -> int:
    manifests = (
        [BY_PWC_SLUG[args.organization]]
        if args.organization
        else list(FEATURED_ORGANIZATIONS)
    )
    summaries: list[dict] = []
    for manifest in manifests:
        session = db_manager.session_local()
        service = OrganizationSyncService(session)
        try:
            summary = await service.sync(
                manifest.slug,
                dry_run=args.dry_run,
                skip_missing_papers=args.skip_missing_papers,
            )
            summaries.append(summary.to_dict())
            print(json.dumps(summary.to_dict(), sort_keys=True))
        except Exception as exc:
            session.rollback()
            summaries.append(
                {
                    "organization": manifest.slug,
                    "failed": 1,
                    "error": str(exc),
                }
            )
            print(json.dumps(summaries[-1], sort_keys=True))
        finally:
            service.close()
            session.close()

    totals: dict[str, int] = {}
    for summary in summaries:
        for key, value in summary.items():
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    print(
        json.dumps({"organizations": len(summaries), "totals": totals}, sort_keys=True)
    )
    return 1 if any(summary.get("failed", 0) for summary in summaries) else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organization", choices=sorted(BY_PWC_SLUG))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--skip-missing-papers",
        action="store_true",
        help="Diagnostics only: report missing papers without importing them.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=25,
        help="Reserved bounded import batch size (currently imports sequentially).",
    )
    args = parser.parse_args()
    if args.batch_size < 1 or args.batch_size > 100:
        parser.error("--batch-size must be between 1 and 100")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
