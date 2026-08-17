"""Refresh paper-linked evaluations from the three ARC Prize leaderboards."""

import argparse

from backend.database.connection import db_manager
from backend.services.arc_prize_sync_service import (
    ArcPrizeSyncService,
    fetch_arc_prize_leaderboards,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncArcPrizeJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_arc_prize", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        snapshots = fetch_arc_prize_leaderboards()
        session = db_manager.session_local()
        try:
            stats = ArcPrizeSyncService(session).sync(
                snapshots, commit=not self.dry_run
            )
            self.logger.info("arc_prize_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
            if stats.unmatched_model_families:
                self.logger.warning(
                    "arc_prize_unmatched_model_families ids=%s",
                    ",".join(stats.unmatched_model_families),
                )
            if stats.missing_papers:
                self.logger.warning(
                    "arc_prize_missing_papers identities=%s",
                    ",".join(stats.missing_papers),
                )
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncArcPrizeJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
