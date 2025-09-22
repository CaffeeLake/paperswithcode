"""
FastAPI router for repository and project page endpoints.

This module provides all repository and project page related API endpoints
that support the enhanced PapersWithCode functionality.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import Repository, Repositories, ProjectPage, ProjectPages
from backend.services.repository_service import RepositoryService
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

router = APIRouter()


@router.get(
    "/repositories/",
    response_model=Repositories,
    summary="Get repositories with pagination and filtering",
)
async def get_repositories(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of repositories per page"
    ),
    owner: Optional[str] = Query(None, description="Filter by repository owner"),
    official_only: bool = Query(
        False, description="Only include official repositories by paper authors"
    ),
    min_stars: Optional[int] = Query(
        None, ge=0, description="Minimum number of GitHub stars"
    ),
    order_by: str = Query("num_stars", description="Field to order by"),
    order_dir: str = Query("desc", regex="^(asc|desc)$", description="Order direction"),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of repositories with optional filtering.

    This endpoint provides comprehensive repository listing functionality with:
    - Pagination support
    - Filtering by owner, official status, and star count
    - Sorting options
    """
    try:
        service = RepositoryService(db)
        return service.get_repositories(
            page=page,
            page_size=page_size,
            owner=owner,
            official_only=official_only,
            min_stars=min_stars,
            order_by=order_by,
            order_dir=order_dir,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/repositories/{repository_id}",
    response_model=Repository,
    summary="Get repository by ID",
)
async def get_repository_by_id(
    repository_id: str = Path(..., description="Repository ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific repository by its database ID.
    """
    try:
        service = RepositoryService(db)
        return service.get_repository_by_id(repository_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/repositories/{owner}",
    response_model=List[Repository],
    summary="Get repositories by owner",
)
async def get_repositories_by_owner(
    owner: str = Path(
        ..., description="Repository owner (GitHub username/organization)"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get all repositories by a specific owner.
    """
    try:
        service = RepositoryService(db)
        return service.get_repositories(
            page=1,
            page_size=1000,  # Large limit to get all repos by owner
            owner=owner,
        ).results
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/repositories/{owner}/{name}",
    response_model=List[Repository],
    summary="Get repositories by owner and name",
)
async def get_repositories_by_owner_and_name(
    owner: str = Path(..., description="Repository owner"),
    name: str = Path(..., description="Repository name"),
    db: Session = Depends(get_database_session),
):
    """
    Get repositories by owner and name.
    """
    try:
        service = RepositoryService(db)
        return service.get_repositories_by_owner_and_name(owner, name)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/project-pages/",
    response_model=ProjectPages,
    summary="Get project pages with pagination and filtering",
)
async def get_project_pages(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of project pages per page"
    ),
    official_only: bool = Query(
        False, description="Only include official project pages by paper authors"
    ),
    order_by: str = Query("created_at", description="Field to order by"),
    order_dir: str = Query("desc", regex="^(asc|desc)$", description="Order direction"),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of project pages with optional filtering.

    This endpoint provides comprehensive project page listing functionality with:
    - Pagination support
    - Filtering by official status
    - Sorting options
    """
    try:
        service = RepositoryService(db)
        return service.get_project_pages(
            page=page,
            page_size=page_size,
            official_only=official_only,
            order_by=order_by,
            order_dir=order_dir,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/project-pages/{page_id}",
    response_model=ProjectPage,
    summary="Get project page by ID",
)
async def get_project_page_by_id(
    page_id: str = Path(..., description="Project page ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific project page by its database ID.
    """
    try:
        service = RepositoryService(db)
        return service.get_project_page_by_id(page_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# Paper-specific endpoints


@router.get(
    "/papers/{paper_id}/repositories",
    response_model=List[Repository],
    summary="Get repositories for a paper",
)
async def get_repositories_for_paper(
    paper_id: str = Path(..., description="Paper ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all repositories associated with a specific paper.
    """
    try:
        service = RepositoryService(db)
        return service.get_repositories_for_paper(paper_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/{paper_id}/project-pages",
    response_model=List[ProjectPage],
    summary="Get project pages for a paper",
)
async def get_project_pages_for_paper(
    paper_id: str = Path(..., description="Paper ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all project pages associated with a specific paper.
    """
    try:
        service = RepositoryService(db)
        return service.get_project_pages_for_paper(paper_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
