"""Idempotent, append-only synchronization of Hugging Face organizations."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database.organizations_setup.organizations import (
    BY_PWC_SLUG,
    FeaturedOrganization,
    featured_for_hf_handle,
)
from backend.models.database import Organization, Paper, PaperOrganization
from backend.services.hf_organization_service import (
    HFOrganizationClient,
    HFOrganizationData,
)
from backend.services.paper_ingestion_service import (
    PaperIngestionError,
    PaperIngestionService,
)
from backend.utils.slug_utils import slugify

logger = logging.getLogger(__name__)
HF_ORG_PAPERS_SOURCE = "hf_org_papers"


@dataclass
class OrganizationSyncStats:
    organization: str
    fetched: int = 0
    existing: int = 0
    imported: int = 0
    linked: int = 0
    already_linked: int = 0
    failed: int = 0
    unknown_organizations_seen: int = 0
    upstream_local_delta: int = 0

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


def _upsert_metadata(
    db: Session,
    manifest: FeaturedOrganization,
    data: HFOrganizationData,
) -> Organization:
    organization = (
        db.query(Organization)
        .filter(
            (Organization.slug == manifest.slug)
            | (Organization.hf_slug == manifest.hf_slug)
        )
        .first()
    )
    if organization is None:
        organization = Organization(slug=manifest.slug, name=data.name)
        db.add(organization)
    organization.name = manifest.name_override or data.name.rstrip("_").strip()
    organization.slug = manifest.slug
    organization.hf_slug = manifest.hf_slug
    organization.hf_url = f"https://huggingface.co/{manifest.hf_slug}"
    organization.logo_url = data.logo_url
    if data.website_url:
        organization.website_url = data.website_url
    organization.is_featured = True
    organization.display_order = manifest.display_order
    organization.hf_paper_count = data.upstream_paper_count
    db.flush()
    return organization


class OrganizationSyncService:
    def __init__(
        self,
        db: Session,
        hf_client: HFOrganizationClient | None = None,
        ingestion_service: PaperIngestionService | None = None,
    ):
        self.db = db
        self.hf_client = hf_client or HFOrganizationClient()
        self._owns_hf_client = hf_client is None
        self.ingestion_service = ingestion_service or PaperIngestionService(db)

    def close(self) -> None:
        if self._owns_hf_client:
            self.hf_client.close()

    async def sync(
        self,
        slug: str,
        *,
        dry_run: bool = False,
        skip_missing_papers: bool = False,
    ) -> OrganizationSyncStats:
        manifest = BY_PWC_SLUG.get(slug)
        if manifest is None:
            raise ValueError(f"Organization {slug!r} is not in the featured manifest")
        data = self.hf_client.fetch(manifest.hf_slug)
        return await self._sync_manifest(
            manifest,
            data,
            dry_run=dry_run,
            skip_missing_papers=skip_missing_papers,
        )

    async def sync_hf_slug(
        self,
        hf_slug: str,
        *,
        slug: str | None = None,
        dry_run: bool = False,
        skip_missing_papers: bool = False,
    ) -> OrganizationSyncStats:
        """Synchronize an arbitrary HF organization through the admin API path."""
        normalized_hf_slug = hf_slug.strip()
        if not normalized_hf_slug:
            raise ValueError("Hugging Face organization handle must not be empty")
        requested_slug = slugify(slug or normalized_hf_slug)
        if not requested_slug:
            raise ValueError("Organization slug must not be empty")

        slug_match = (
            self.db.query(Organization)
            .filter(Organization.slug == requested_slug)
            .one_or_none()
        )
        hf_match = (
            self.db.query(Organization)
            .filter(func.lower(Organization.hf_slug) == normalized_hf_slug.lower())
            .one_or_none()
        )
        if (
            slug_match is not None
            and slug_match.hf_slug
            and slug_match.hf_slug.lower() != normalized_hf_slug.lower()
        ):
            raise ValueError(
                f"Organization slug {requested_slug!r} already belongs to Hugging "
                f"Face handle {slug_match.hf_slug!r}"
            )
        if (
            slug_match is not None
            and hf_match is not None
            and slug_match.id != hf_match.id
        ):
            raise ValueError(
                f"Organization slug {requested_slug!r} and Hugging Face handle "
                f"{normalized_hf_slug!r} identify different rows"
            )
        existing = hf_match or slug_match
        if existing is not None:
            requested_slug = existing.slug
            display_order = existing.display_order
        else:
            display_order = None
        if display_order is None:
            display_order = (
                self.db.query(func.max(Organization.display_order)).scalar() or 0
            ) + 1

        manifest = FeaturedOrganization(
            hf_slug=normalized_hf_slug,
            slug=requested_slug,
            display_order=display_order,
        )
        data = self.hf_client.fetch(normalized_hf_slug)
        return await self._sync_manifest(
            manifest,
            data,
            dry_run=dry_run,
            skip_missing_papers=skip_missing_papers,
        )

    async def _sync_manifest(
        self,
        manifest: FeaturedOrganization,
        data: HFOrganizationData,
        *,
        dry_run: bool,
        skip_missing_papers: bool,
    ) -> OrganizationSyncStats:
        stats = OrganizationSyncStats(
            organization=manifest.slug, fetched=len(data.papers)
        )

        arxiv_ids = [paper.arxiv_id for paper in data.papers]
        local_by_arxiv = {
            paper.arxiv_id: paper
            for paper in self.db.query(Paper)
            .filter(Paper.arxiv_id.in_(arxiv_ids), Paper.is_latest_version)
            .all()
        }
        stats.existing = len(local_by_arxiv)
        if dry_run:
            stats.imported = (
                0 if skip_missing_papers else len(arxiv_ids) - stats.existing
            )
            stats.upstream_local_delta = len(arxiv_ids) - stats.existing
            return stats

        try:
            organization = _upsert_metadata(self.db, manifest, data)
            if data.logo_url:
                try:
                    logo_data, logo_mime_type = self.hf_client.fetch_logo(data.logo_url)
                    organization.logo_sha256 = hashlib.sha256(logo_data).hexdigest()
                    if organization.logo_data != logo_data:
                        organization.logo_data = logo_data
                        organization.logo_mime_type = logo_mime_type
                except Exception as exc:
                    logger.warning(
                        "organization_logo_refresh_failed slug=%s error=%s",
                        manifest.slug,
                        exc,
                    )

            for hf_paper in data.papers:
                paper = local_by_arxiv.get(hf_paper.arxiv_id)
                if paper is None and not skip_missing_papers:
                    try:
                        (
                            paper,
                            created,
                        ) = await self.ingestion_service.get_or_import_arxiv_paper(
                            hf_paper.arxiv_id
                        )
                        if created:
                            stats.imported += 1
                    except PaperIngestionError as exc:
                        stats.failed += 1
                        logger.error(
                            "organization_paper_import_failed organization=%s "
                            "arxiv_id=%s error=%s",
                            manifest.slug,
                            hf_paper.arxiv_id,
                            exc,
                        )
                        continue
                if paper is None:
                    stats.failed += 1
                    continue
                link = (
                    self.db.query(PaperOrganization)
                    .filter(
                        PaperOrganization.paper_id == paper.id,
                        PaperOrganization.organization_id == organization.id,
                    )
                    .first()
                )
                if link is None:
                    self.db.add(
                        PaperOrganization(
                            paper_id=paper.id,
                            organization_id=organization.id,
                            source=HF_ORG_PAPERS_SOURCE,
                        )
                    )
                    stats.linked += 1
                else:
                    if link.source != HF_ORG_PAPERS_SOURCE:
                        link.source = HF_ORG_PAPERS_SOURCE
                    link.added_by_hf_subject = None
                    link.added_by_hf_username = None
                    stats.already_linked += 1

            if stats.failed == 0:
                organization.last_hf_synced_at = datetime.now(timezone.utc)
            self.db.commit()
            local_count = (
                self.db.query(PaperOrganization)
                .filter(
                    PaperOrganization.organization_id == organization.id,
                    PaperOrganization.source == HF_ORG_PAPERS_SOURCE,
                )
                .count()
            )
            stats.upstream_local_delta = data.upstream_paper_count - local_count
            return stats
        except Exception:
            self.db.rollback()
            raise


def _organization_payloads(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def link_daily_paper_organizations(
    db: Session, paper_id: int, organization_payload: Any
) -> dict[str, int]:
    """Link curated organizations from one HF daily-paper payload."""
    stats = {"linked": 0, "already_linked": 0, "unknown_organizations_seen": 0}
    for payload in _organization_payloads(organization_payload):
        raw_handle = payload.get("name")
        manifest = featured_for_hf_handle(raw_handle)
        if manifest is None:
            stats["unknown_organizations_seen"] += 1
            logger.warning("unknown_hf_organization handle=%s", raw_handle)
            continue
        organization = (
            db.query(Organization)
            .filter(
                (Organization.slug == manifest.slug)
                | (Organization.hf_slug == manifest.hf_slug)
            )
            .first()
        )
        if organization is None:
            organization = Organization(
                name=str(
                    payload.get("fullname") or raw_handle or manifest.slug
                ).strip(),
                slug=manifest.slug,
                hf_slug=manifest.hf_slug,
                hf_url=f"https://huggingface.co/{manifest.hf_slug}",
                logo_url=payload.get("avatar") or payload.get("avatarUrl"),
                is_featured=True,
                display_order=manifest.display_order,
            )
            db.add(organization)
            db.flush()
        link = (
            db.query(PaperOrganization)
            .filter(
                PaperOrganization.paper_id == paper_id,
                PaperOrganization.organization_id == organization.id,
            )
            .first()
        )
        if link is None:
            db.add(
                PaperOrganization(
                    paper_id=paper_id,
                    organization_id=organization.id,
                    source=HF_ORG_PAPERS_SOURCE,
                )
            )
            stats["linked"] += 1
        else:
            if link.source != HF_ORG_PAPERS_SOURCE:
                link.source = HF_ORG_PAPERS_SOURCE
            link.added_by_hf_subject = None
            link.added_by_hf_username = None
            stats["already_linked"] += 1
    db.commit()
    return stats
