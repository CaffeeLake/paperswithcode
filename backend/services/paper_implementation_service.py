"""Paper-family implementation coverage predicates."""

from __future__ import annotations

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import aliased

from backend.models.database import Paper as DBPaper
from backend.models.database import PaperRepository as DBPaperRepository


def family_repository_exists_clause(
    paper=DBPaper,
    *,
    official_only: bool = False,
):
    """Return whether any version in ``paper``'s family links a repository."""
    family = aliased(DBPaper)
    conditions = [
        or_(
            and_(
                paper.arxiv_id.is_not(None),
                family.arxiv_id == paper.arxiv_id,
            ),
            and_(paper.arxiv_id.is_(None), family.id == paper.id),
        )
    ]
    if official_only:
        conditions.append(DBPaperRepository.is_official)
    return exists(
        select(1)
        .select_from(family)
        .join(DBPaperRepository, DBPaperRepository.paper_id == family.id)
        .where(*conditions)
    )
