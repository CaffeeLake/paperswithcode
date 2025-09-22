"""
FastAPI router for paper endpoints.

This module provides all paper-related API endpoints that match the
original PapersWithCode API specification.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import (
    Paper,
    Papers,
    PaperSummary,
    PaperVersions,
    VersionComparison,
)
from backend.services.paper_service import PaperService
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.urls import validate_arxiv_id, validate_version

router = APIRouter()


@router.get(
    "/papers/",
    response_model=Papers,
    summary="Get papers with pagination and filtering",
)
async def get_papers(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: Optional[int] = Query(
        None, ge=1, le=500, description="Number of papers per page"
    ),
    search: Optional[str] = Query(None, description="Search term for title/abstract"),
    published_after: Optional[str] = Query(
        None, description="Filter papers published after this date (YYYY-MM-DD)"
    ),
    published_before: Optional[str] = Query(
        None, description="Filter papers published before this date (YYYY-MM-DD)"
    ),
    conference: Optional[str] = Query(None, description="Filter by conference"),
    latest_only: bool = Query(
        True, description="Whether to only include latest versions of papers"
    ),
    order_by: str = Query("date_published", description="Field to order by"),
    order_dir: str = Query("desc", regex="^(asc|desc)$", description="Order direction"),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of papers with optional filtering and searching.

    This endpoint provides comprehensive paper listing functionality with:
    - Pagination support
    - Full-text search in titles and abstracts
    - Date range filtering
    - Conference filtering
    - Sorting options
    - Latest version filtering
    """
    try:
        service = PaperService(db)
        return service.get_papers(
            page=page,
            page_size=page_size,
            search=search,
            published_after=published_after,
            published_before=published_before,
            conference=conference,
            latest_only=latest_only,
            order_by=order_by,
            order_dir=order_dir,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/search",
    response_model=List[PaperSummary],
    summary="Search papers with citation-based ranking",
)
async def search_papers(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=100, description="Maximum number of results"),
    db: Session = Depends(get_database_session),
):
    """
    Full-text search for papers in titles and abstracts with citation-based ranking.

    Uses PostgreSQL's full-text search capabilities combined with citation counts
    to rank papers by both relevance and importance. Also queries Semantic Scholar
    API for highly cited papers to provide enhanced search results.

    Returns paper summaries ordered by:
    1. Exact title matches (sorted by citation count)
    2. Title contains query (sorted by citation count)
    3. Full-text matches (sorted by relevance + citation importance)
    """
    try:
        service = PaperService(db)
        return service.search_papers(q, limit)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/recent", response_model=List[PaperSummary], summary="Get recent papers"
)
async def get_recent_papers(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of papers"),
    db: Session = Depends(get_database_session),
):
    """
    Get recently published papers.

    Returns the most recently published papers (latest versions only)
    ordered by publication date.
    """
    try:
        service = PaperService(db)
        return service.get_recent_papers(limit)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/papers/stats", summary="Get paper statistics")
async def get_paper_stats(db: Session = Depends(get_database_session)):
    """
    Get statistics about the papers in the database.

    Returns information about:
    - Total number of papers
    - Papers by publication year
    - Latest paper date
    - Version distribution
    """
    try:
        service = PaperService(db)
        return service.get_paper_stats()
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/{paper_id}", response_model=Paper, summary="Get paper by database ID"
)
async def get_paper_by_id(
    paper_id: int = Path(..., description="Database paper ID"),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific paper by its database ID.

    Returns complete paper information including:
    - Full metadata
    - Author list
    - ArXiv URLs (abstract and PDF)
    - Conference information
    - Version information
    """
    try:
        service = PaperService(db)
        return service.get_paper_by_id(paper_id, include_resources=include_resources)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/arxiv/{arxiv_id}", response_model=Paper, summary="Get paper by ArXiv ID"
)
async def get_paper_by_arxiv_id(
    arxiv_id: str = Path(..., description="ArXiv ID (e.g., '1805.10616')"),
    version: Optional[str] = Query(
        None,
        description="Specific version (e.g., 'v2'). If not provided, returns latest version",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a specific paper by its ArXiv ID and optional version.

    If no version is specified, returns the latest version of the paper.
    If a specific version is requested, returns that exact version.

    The ArXiv ID should be in the format:
    - Modern: 1805.10616
    - Legacy: cs.DS/0610046
    """
    # Validate ArXiv ID format
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    # Validate version format if provided
    if version and not validate_version(version):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid version format: {version}. Expected format: v1, v2, etc.",
        )

    try:
        service = PaperService(db)
        return service.get_paper_by_arxiv_id(arxiv_id, version)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/arxiv/{arxiv_id}/versions",
    response_model=PaperVersions,
    summary="Get all versions of a paper",
)
async def get_paper_versions(
    arxiv_id: str = Path(..., description="ArXiv ID"),
    db: Session = Depends(get_database_session),
):
    """
    Get all versions of a paper by ArXiv ID.

    Returns information about all available versions including:
    - Version identifiers
    - Publication dates
    - Title changes across versions
    - Abstract previews
    - Direct links to each version
    """
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    try:
        service = PaperService(db)
        return service.get_paper_versions(arxiv_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/papers/arxiv/{arxiv_id}/versions/{from_version}/compare/{to_version}",
    response_model=VersionComparison,
    summary="Compare two versions of a paper",
)
async def compare_paper_versions(
    arxiv_id: str = Path(..., description="ArXiv ID"),
    from_version: str = Path(..., description="Source version (e.g., 'v1')"),
    to_version: str = Path(..., description="Target version (e.g., 'v2')"),
    db: Session = Depends(get_database_session),
):
    """
    Compare two versions of a paper to see what changed.

    Returns comparison information including:
    - Whether the title changed
    - Whether the abstract changed
    - Whether the publication date changed
    - Time elapsed between versions
    """
    if not validate_arxiv_id(arxiv_id):
        raise HTTPException(
            status_code=400, detail=f"Invalid ArXiv ID format: {arxiv_id}"
        )

    if not validate_version(from_version):
        raise HTTPException(
            status_code=400, detail=f"Invalid source version format: {from_version}"
        )

    if not validate_version(to_version):
        raise HTTPException(
            status_code=400, detail=f"Invalid target version format: {to_version}"
        )

    try:
        service = PaperService(db)
        return service.compare_paper_versions(arxiv_id, from_version, to_version)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/papers/update-citations", summary="Update citation counts from Semantic Scholar"
)
async def update_citation_counts(
    limit: int = Query(
        100, ge=1, le=1000, description="Maximum number of papers to update"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Update citation counts for papers using the Semantic Scholar API.

    This endpoint fetches citation counts from Semantic Scholar and updates
    the database. It prioritizes papers that haven't been updated recently
    or don't have citation data yet.

    Returns statistics about the update process.
    """
    try:
        service = PaperService(db)
        result = await service.update_citation_counts(limit)
        return result
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


# Legacy compatibility endpoints (matching original PapersWithCode API)


@router.get(
    "/papers",
    response_model=Papers,
    summary="Legacy: Get papers (compatibility endpoint)",
)
async def get_papers_legacy(
    page: int = Query(1, ge=1), db: Session = Depends(get_database_session)
):
    """
    Legacy compatibility endpoint matching the original PapersWithCode API.

    This endpoint provides basic pagination without advanced filtering options
    to maintain compatibility with existing clients.
    """
    try:
        service = PaperService(db)
        return service.get_papers(page=page, latest_only=True)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
