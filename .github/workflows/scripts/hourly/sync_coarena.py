"""Refresh paper-linked evaluations from the living CoArena leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.coarena_sync_service import (
    CoArenaSyncService,
    fetch_coarena_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncCoArenaJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_coarena", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_coarena_leaderboard()
        session = db_manager.session_local()
        try:
            stats = CoArenaSyncService(session).sync(entries, commit=not self.dry_run)
            self.logger.info("coarena_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unmatched_models:
                self.logger.warning(
                    "coarena_unmatched_models ids=%s",
                    ",".join(stats.unmatched_models),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "coarena_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncCoArenaJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
