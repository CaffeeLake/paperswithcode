"""Method usage trends derived from paper-to-method links."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.models.api import MethodTrend, MethodTrendPoint
from backend.models.database import Method as DBMethod
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperMethod
from backend.utils.exceptions import PaperNotFoundError


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _shift_month(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    return date(month_index // 12, month_index % 12 + 1, 1)


class MethodTrendService:
    """Calculate bounded monthly histories for method usage."""

    def __init__(self, db: Session):
        self.db = db

    def get_method_trend(
        self,
        method_id: str,
        *,
        recent_days: int = 90,
        baseline_days: int = 180,
        history_months: int = 24,
        today: date | None = None,
    ) -> MethodTrend:
        method = self._resolve_method(method_id)
        generated_on = today or datetime.now(UTC).date()
        recent_start = generated_on - timedelta(days=recent_days)
        baseline_start = recent_start - timedelta(days=baseline_days)
        history_start = _shift_month(_month_start(generated_on), 1 - history_months)
        query_start = min(history_start, baseline_start)

        rows = (
            self.db.query(DBPaper.id, DBPaper.date_published)
            .join(PaperMethod, PaperMethod.paper_id == DBPaper.id)
            .filter(
                PaperMethod.method_id == method.id,
                DBPaper.is_latest_version,
                DBPaper.date_published >= query_start,
                DBPaper.date_published <= generated_on,
            )
            .all()
        )

        recent_count = 0
        baseline_count = 0
        history_counts = [0] * history_months
        first_history_month = history_start.year * 12 + history_start.month - 1

        for _paper_id, published_on in rows:
            if published_on > recent_start:
                recent_count += 1
            elif published_on > baseline_start:
                baseline_count += 1

            month_index = (
                published_on.year * 12 + published_on.month - 1 - first_history_month
            )
            if 0 <= month_index < history_months:
                history_counts[month_index] += 1

        recent_velocity = recent_count * 30.0 / recent_days
        baseline_velocity = baseline_count * 30.0 / baseline_days
        history = []
        for index, paper_count in enumerate(history_counts):
            start = _shift_month(history_start, index)
            next_start = _shift_month(start, 1)
            history.append(
                MethodTrendPoint(
                    start_date=start,
                    end_date=min(generated_on, next_start - timedelta(days=1)),
                    paper_count=paper_count,
                )
            )

        return MethodTrend(
            method_id=method.id,
            method_slug=method.slug,
            recent_days=recent_days,
            baseline_days=baseline_days,
            history_months=history_months,
            generated_on=generated_on,
            recent_paper_count=recent_count,
            baseline_paper_count=baseline_count,
            trend_score=round(recent_velocity, 4),
            rate_change=(
                round(recent_velocity / baseline_velocity, 4)
                if baseline_velocity
                else None
            ),
            history=history,
        )

    def _resolve_method(self, method_id: str) -> DBMethod:
        if str(method_id).isdigit():
            method = (
                self.db.query(DBMethod).filter(DBMethod.id == int(method_id)).first()
            )
        else:
            method = (
                self.db.query(DBMethod)
                .filter(
                    or_(
                        func.lower(DBMethod.slug) == str(method_id).lower(),
                        func.lower(DBMethod.name) == str(method_id).lower(),
                    )
                )
                .order_by(DBMethod.id)
                .first()
            )
        if method is None:
            raise PaperNotFoundError(
                f"Method with ID, slug, or name '{method_id}' not found"
            )
        return method
