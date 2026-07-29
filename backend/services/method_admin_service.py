"""Rule-based creation and updating of method taxonomy rows."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.database import Area, Method, PaperMethod
from backend.services.paper_method_link_service import sync_method_source_evidence
from backend.utils.paper_reference import resolve_paper


@dataclass(frozen=True)
class MethodUpsertResult:
    id: int
    slug: str
    name: str
    status: str
    source_reference: str | None
    source_link_status: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "status": self.status,
            "source_reference": self.source_reference,
            "source_link_status": self.source_link_status,
        }


def add_or_update_method(
    db: Session,
    *,
    slug: str,
    name: str,
    full_name: str,
    description: str,
    keywords: str,
    area_name: str,
    introduced_year: int,
    source_title: str,
    source_paper: str | None = None,
    source_url: str | None = None,
    code_snippet_url: str | None = None,
    image_credit: str | None = None,
) -> MethodUpsertResult:
    """Idempotently upsert one method and link its introducing paper."""
    if bool(source_paper) == bool(source_url):
        raise ValueError("Provide exactly one of source_paper or source_url")

    area = db.execute(select(Area).where(Area.name == area_name)).scalar_one_or_none()
    if area is None:
        raise ValueError(f"Area not found: {area_name}")

    paper = None
    source_reference = None
    if source_paper:
        paper, source_reference = resolve_paper(db, source_paper)

    method = db.execute(select(Method).where(Method.slug == slug)).scalar_one_or_none()
    status = "updated" if method else "created"
    if method is None:
        method = Method(slug=slug, name=name)
        db.add(method)

    method.name = name
    method.full_name = full_name
    method.description = description
    method.keywords = keywords
    method.area_id = area.id
    method.introduced_year = introduced_year
    method.source_paper_id = paper.id if paper else None
    method.source_url = None if paper else source_url
    method.source_title = source_title
    method.code_snippet_url = code_snippet_url
    method.image_url = None
    method.image_credit = image_credit
    db.flush()

    source_link_status = "not_applicable"
    if paper:
        link = db.get(PaperMethod, (paper.id, method.id))
        source_link_status = "existing" if link else "created"
    source_links_created = sync_method_source_evidence(
        db, method_id=method.id, source_paper_id=paper.id if paper else None
    )
    if paper and not source_links_created and source_link_status == "created":
        source_link_status = "excluded"

    db.commit()
    return MethodUpsertResult(
        id=method.id,
        slug=slug,
        name=name,
        status=status,
        source_reference=source_reference,
        source_link_status=source_link_status,
    )
