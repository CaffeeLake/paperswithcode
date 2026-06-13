"""
FastAPI router for organization endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import (
    Organization,
    OrganizationAreasWithTasks,
    Organizations,
    Papers,
)
from backend.services.organization_service import OrganizationService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get(
    "/",
    response_model=Organizations,
    summary="List all organizations",
)
def get_organizations(
    db: Session = Depends(get_database_session),
):
    try:
        service = OrganizationService(db)
        return service.get_organizations()
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
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
