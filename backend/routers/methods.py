"""
Methods API router.

Provides endpoints for accessing AI/ML method data, including filtering by year,
collection, and paper associations.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import Method, Methods, Papers
from backend.services.method_service import MethodService
from backend.database.connection import get_database_session
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("/", response_model=Methods)
async def list_methods(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of methods per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for method name, full name, and description"
    ),
    name: Optional[str] = Query(
        None, description="Filter by partial method name match"
    ),
    full_name: Optional[str] = Query(
        None, description="Filter by partial full name match"
    ),
    introduced_year: Optional[int] = Query(
        None, description="Filter by year method was introduced"
    ),
    ordering: Optional[str] = Query(
        "name",
        description="Order by field: name, full_name, introduced_year, created_at (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of AI/ML methods.

    Methods represent techniques, algorithms, and approaches used in machine learning
    research (e.g., ResNet, Transformer, Adam, Dropout, etc.).

    **Example queries:**
    - `/api/v1/methods/` - Get all methods
    - `/api/v1/methods/?q=transform` - Search for methods containing "transform"
    - `/api/v1/methods/?introduced_year=2017` - Get methods from 2017
    - `/api/v1/methods/?name=resnet` - Find methods with "resnet" in the name
    - `/api/v1/methods/?ordering=-introduced_year` - Most recent methods first
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = ["name", "full_name", "introduced_year", "created_at"]
        if order_by not in valid_fields:
            order_by = "name"

        service = MethodService(db)

        # Use search if q parameter is provided
        if q:
            return service.search_methods(query=q, page=page, page_size=page_size)

        return service.get_methods(
            page=page,
            page_size=page_size,
            name=name,
            full_name=full_name,
            introduced_year=introduced_year,
            order_by=order_by,
            order_dir=order_dir,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{method_id}", response_model=Method)
async def get_method(
    method_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific AI/ML method by ID, slug, or name.

    Returns detailed information about a method including its description,
    source attribution, collection information, and paper count.

    **Examples:**
    - `/api/v1/methods/1` - Get method with ID 1
    - `/api/v1/methods/gpt-2` - Get method by slug (preferred)
    - `/api/v1/methods/vision-transformer` - Get method by slug
    - `/api/v1/methods/GPT-2` - Get method by name (legacy support)
    """
    try:
        service = MethodService(db)

        # Try as numeric ID first
        if method_id.isdigit():
            return service.get_method_by_id(method_id)

        # Otherwise, treat as name
        return service.get_method_by_name(method_id)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{method_id}/papers", response_model=Papers)
async def get_method_papers(
    method_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of papers per page (max 100)"
    ),
    order_by: Optional[str] = Query(
        "date_published",
        description="Field to order by: date_published, citation_count, title",
    ),
    order_dir: Optional[str] = Query(
        "desc", description="Order direction: asc or desc"
    ),
    latest_only: bool = Query(
        True, description="Only return latest versions of papers"
    ),
    include_resources: bool = Query(
        False, description="Include repositories and project pages"
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get all papers that use a specific method.

    Returns a paginated list of papers tagged with the given method.
    Accepts either method ID or method name.

    **Example queries:**
    - `/api/v1/methods/1/papers` - Get papers using method ID 1
    - `/api/v1/methods/GPT-2/papers` - Get papers using GPT-2
    - `/api/v1/methods/Transformer/papers?order_by=citation_count&order_dir=desc` - Most cited papers
    - `/api/v1/methods/BERT/papers?include_resources=true` - Include GitHub repos
    """
    try:
        service = MethodService(db)
        return service.get_method_papers(
            method_id=method_id,
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
