"""Write today's organization snapshots and rolling 30-day scores."""

from backend.database.connection import db_manager
from backend.services.organization_trending_service import OrganizationTrendingService
from scripts.utils.cron_helpers import DatabaseCronJob


class CalculateOrganizationTrendingScoresJob(DatabaseCronJob):
    def __init__(self):
        super().__init__(
            job_name="calculate_organization_trending_scores", log_level="INFO"
        )

    def run(self):
        session = db_manager.session_local()
        try:
            stats = OrganizationTrendingService(session).calculate()
            self.logger.info("organization_trending %s", stats)
            self.logger.info("Papers processed: %s", stats["snapshots"])
            if stats["snapshots"] == 0:
                raise RuntimeError("No featured organization snapshots were written")
        finally:
            session.close()


if __name__ == "__main__":
    raise SystemExit(0 if CalculateOrganizationTrendingScoresJob().execute() else 1)
