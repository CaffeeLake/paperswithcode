"""Refresh paper-linked evaluation rows from the living TabArena leaderboard."""

import argparse

from backend.database.connection import db_manager
from backend.services.tabarena_sync_service import (
    TabArenaSyncService,
    fetch_tabarena_leaderboard,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncTabArenaJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_tabarena", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        entries = fetch_tabarena_leaderboard()
        session = db_manager.session_local()
        try:
            stats = TabArenaSyncService(session).sync(entries, commit=not self.dry_run)
            self.logger.info("tabarena_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unmatched_sources:
                self.logger.warning(
                    "tabarena_unmatched_sources values=%s",
                    ",".join(stats.unmatched_sources),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "tabarena_missing_papers values=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncTabArenaJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
