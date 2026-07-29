"""Daily append-only synchronization of the 21 featured HF organizations."""

import asyncio

from backend.database.connection import db_manager
from backend.database.organizations_setup.organizations import FEATURED_ORGANIZATIONS
from backend.services.organization_sync_service import OrganizationSyncService
from scripts.utils.cron_helpers import DatabaseCronJob


class SyncHFOrganizationsJob(DatabaseCronJob):
    def __init__(self):
        super().__init__(job_name="sync_hf_organizations", log_level="INFO")

    def run(self):
        failures = 0
        papers_processed = 0
        for manifest in FEATURED_ORGANIZATIONS:
            session = db_manager.session_local()
            service = OrganizationSyncService(session)
            try:
                stats = asyncio.run(service.sync(manifest.slug))
                self.logger.info("organization_sync %s", stats.to_dict())
                failures += stats.failed
                papers_processed += stats.fetched
            except Exception as exc:
                session.rollback()
                failures += 1
                self.logger.error(
                    "organization_sync_failed slug=%s error=%s",
                    manifest.slug,
                    exc,
                )
            finally:
                service.close()
                session.close()
        if failures:
            raise RuntimeError(
                f"HF organization sync completed with {failures} failures"
            )
        self.logger.info("Papers processed: %s", papers_processed)


if __name__ == "__main__":
    raise SystemExit(0 if SyncHFOrganizationsJob().execute() else 1)
