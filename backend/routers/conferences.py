"""
FastAPI router for conference endpoints.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import (
    Conference,
    ConferenceAreasWithTasks,
    ConferenceDeadlines,
    Conferences,
    Papers,
)
from backend.services.conference_service import ConferenceService
from backend.utils.exceptions import DatabaseError, PaperNotFoundError

router = APIRouter(prefix="/conferences", tags=["conferences"])


@router.get(
    "/",
    response_model=Conferences,
    summary="List all conferences",
)
async def get_conferences(
    db: Session = Depends(get_database_session),
):
    try:
        service = ConferenceService(db)
        return service.get_conferences()
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/deadlines",
    response_model=ConferenceDeadlines,
    summary="List conferences with their submission deadlines",
)
async def get_conference_deadlines(
    db: Session = Depends(get_database_session),
):
    try:
        service = ConferenceService(db)
        return service.get_conference_deadlines()
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}",
    response_model=Conference,
    summary="Get conference details",
)
async def get_conference(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    db: Session = Depends(get_database_session),
):
    try:
        service = ConferenceService(db)
        return service.get_conference(slug)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}/areas-with-tasks",
    response_model=ConferenceAreasWithTasks,
    summary="Get conference taxonomy grouped by area and task",
)
async def get_conference_areas_with_tasks(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    db: Session = Depends(get_database_session),
):
    try:
        service = ConferenceService(db)
        return service.get_conference_areas_with_tasks(slug)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{slug}/papers",
    response_model=Papers,
    summary="List papers for a conference, optionally filtered by task",
)
async def get_conference_papers(
    slug: str = Path(..., description="Conference slug (e.g., cvpr-2026)"),
    task: Optional[str] = Query(
        None, description="Optional task slug to filter papers"
    ),
    presentation: Optional[str] = Query(
        None,
        description=(
            "Optional presentation tier filter: oral, spotlight, outstanding, "
            "or best_paper_finalist"
        ),
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
        service = ConferenceService(db)
        return service.get_conference_papers(
            slug=slug,
            task_slug=task,
            presentation=presentation,
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
