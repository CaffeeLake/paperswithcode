"""
FastAPI router for organization endpoints.
"""

from typing import Optional

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import (
    Organization,
    OrganizationAreasWithTasks,
    OrganizationContributions,
    Organizations,
    Papers,
)
from backend.services.organization_service import OrganizationService
from backend.models.database import Organization as DBOrganization
from backend.utils.exceptions import DatabaseError, PaperNotFoundError
from backend.utils.organization_logos import organization_logo_extension

router = APIRouter(prefix="/organizations", tags=["organizations"])

VERSIONED_LOGO_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "CDN-Cache-Control": "public, max-age=31536000, immutable",
}
COMPAT_LOGO_CACHE_HEADERS = {
    "Cache-Control": "public, max-age=0, must-revalidate",
    "CDN-Cache-Control": "public, max-age=0, must-revalidate",
}


@router.get(
    "/",
    response_model=Organizations,
    summary="List all organizations",
)
def get_organizations(
    featured_only: bool = Query(
        False, description="Return only the curated featured organizations"
    ),
    db: Session = Depends(get_database_session),
):
    try:
        service = OrganizationService(db)
        return service.get_organizations(featured_only=featured_only)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}",
    response_model=Organization,
    summary="Get organization details",
)
def get_organization(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    try:
        service = OrganizationService(db)
        return service.get_organization(slug)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}/contributions",
    response_model=OrganizationContributions,
    summary="Get daily paper contributions for an organization",
)
def get_organization_contributions(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    try:
        return OrganizationService(db).get_organization_contributions(slug)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


def _organization_logo_response(
    request: Request,
    slug: str,
    db: Session,
    extension: str | None = None,
    digest: str | None = None,
):
    organization = (
        db.query(DBOrganization).filter(DBOrganization.slug == slug).one_or_none()
    )
    if (
        organization is None
        or organization.logo_mime_type is None
        or organization.logo_data is None
    ):
        raise HTTPException(
            status_code=404,
            detail="Logo not available",
            headers={"Cache-Control": "no-store"},
        )
    expected_extension = organization_logo_extension(organization.logo_mime_type)
    if extension is not None and extension != expected_extension:
        raise HTTPException(status_code=404, detail="Logo format not available")

    actual_digest = hashlib.sha256(organization.logo_data).hexdigest()
    if digest is not None and digest != actual_digest:
        raise HTTPException(status_code=404, detail="Logo version not available")

    etag = f'"{actual_digest}"'
    cache_headers = (
        VERSIONED_LOGO_CACHE_HEADERS if digest else COMPAT_LOGO_CACHE_HEADERS
    )
    headers = {**cache_headers, "ETag": etag}
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)
    return Response(
        content=organization.logo_data,
        media_type=organization.logo_mime_type,
        headers=headers,
    )


@router.get("/{slug}/logo", summary="Serve the cached organization logo")
def get_organization_logo(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    """Compatibility route for logo URLs emitted before extension caching."""
    return _organization_logo_response(request, slug, db)


@router.get(
    "/{slug}/logo/{digest}.{extension}",
    summary="Serve an immutable version of the cached organization logo",
)
def get_versioned_organization_logo(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    digest: str = Path(..., min_length=64, max_length=64),
    extension: str = Path(..., description="Cached logo file extension"),
    db: Session = Depends(get_database_session),
):
    return _organization_logo_response(
        request,
        slug,
        db,
        extension.lower(),
        digest.lower(),
    )


@router.get(
    "/{slug}/logo.{extension}",
    summary="Serve a compatibility organization logo URL",
)
def get_organization_logo_with_extension(
    request: Request,
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    extension: str = Path(..., description="Cached logo file extension"),
    db: Session = Depends(get_database_session),
):
    return _organization_logo_response(request, slug, db, extension.lower())


@router.get(
    "/{slug}/areas-with-tasks",
    response_model=OrganizationAreasWithTasks,
    summary="Get organization taxonomy grouped by area and task",
)
def get_organization_areas_with_tasks(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    db: Session = Depends(get_database_session),
):
    try:
        service = OrganizationService(db)
        return service.get_organization_areas_with_tasks(slug)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}/papers",
    response_model=Papers,
    summary="List papers for an organization, optionally filtered by task",
)
def get_organization_papers(
    slug: str = Path(..., description="Organization slug (e.g., nvidia)"),
    task: Optional[str] = Query(
        None, description="Optional task slug to filter papers"
    ),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Papers per page"),
    latest_only: bool = Query(True, description="Only include latest paper versions"),
    order_by: str = Query(
        "date_published",
        description="Sort field: date_published, title, citation_count, trending",
    ),
    order_dir: str = Query("desc", description="Sort direction: asc or desc"),
    include_resources: bool = Query(
        False, description="Include repositories and tasks on each paper"
    ),
    has_code: bool = Query(
        False, description="Only include papers with a linked GitHub repository"
    ),
    has_hf_artifacts: bool = Query(
        False, description="Only include papers with linked Hugging Face artifacts"
    ),
    db: Session = Depends(get_database_session),
):
    try:
        service = OrganizationService(db)
        return service.get_organization_papers(
            slug=slug,
            task_slug=task,
            page=page,
            page_size=page_size,
            latest_only=latest_only,
            order_by=order_by,
            order_dir=order_dir,
            include_resources=include_resources,
            has_code=has_code,
            has_hf_artifacts=has_hf_artifacts,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
