"""Index reviewed model papers and refresh Artificial Analysis evaluations."""

import argparse

from backend.database.connection import db_manager
from backend.services.artificial_analysis_sync_service import (
    ArtificialAnalysisSyncService,
    fetch_artificial_analysis_leaderboard,
    run_discovery,
)
from scripts.utils.cron_helpers import CronJobBase


class SyncArtificialAnalysisJob(CronJobBase):
    def __init__(self, *, dry_run: bool = False):
        super().__init__(job_name="sync_artificial_analysis", log_level="INFO")
        self.dry_run = dry_run

    def run(self):
        leaderboard = fetch_artificial_analysis_leaderboard()
        session = db_manager.session_local()
        try:
            discovery = run_discovery(session, persist=not self.dry_run)
            self.logger.info("artificial_analysis_discovery %s", discovery.to_dict())
            stats = ArtificialAnalysisSyncService(session).sync(
                leaderboard,
                discovery=discovery,
                commit=not self.dry_run,
            )
            self.logger.info("artificial_analysis_sync %s", stats.to_dict())
            self.logger.info("Papers processed: %s", stats.matched)
        finally:
            session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return 0 if SyncArtificialAnalysisJob(dry_run=args.dry_run).execute() else 1


if __name__ == "__main__":
    raise SystemExit(main())
