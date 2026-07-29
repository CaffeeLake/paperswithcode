"""
Methods API router.

Provides endpoints for accessing AI/ML method data, including filtering by year,
collection, and paper associations.
"""

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import KeywordUpdate, Method, Methods, MethodTrend, Papers
from backend.models.database import Method as DBMethod
from backend.services.method_service import MethodService
from backend.services.method_trend_service import MethodTrendService
from backend.database.connection import get_database_session
from backend.utils.auth import require_admin
from backend.utils.entity_images import (
    IMAGE_CACHE_HEADERS,
    IMAGE_MISSING_HEADERS,
    load_entity_image,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError

router = APIRouter(prefix="/methods", tags=["methods"])


@router.get("/", response_model=Methods)
def list_methods(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=500, description="Number of methods per page (max 500)"
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
    area_id: Optional[int] = Query(
        None, description="Filter methods belonging to this research area"
    ),
    exclude_id: Optional[int] = Query(
        None, description="Exclude a specific method ID from results"
    ),
    ordering: Optional[str] = Query(
        "name",
        description=(
            "Order by field: name, full_name, introduced_year, created_at, "
            "paper_count, trend_score (prefix with '-' for descending)"
        ),
    ),
    include_trends: bool = Query(
        False,
        description="Include 90-day method usage scores and baseline rate changes",
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

        valid_fields = [
            "name",
            "full_name",
            "introduced_year",
            "created_at",
            "paper_count",
            "trend_score",
        ]
        if order_by not in valid_fields:
            order_by = "name"

        service = MethodService(db)

        # Use search if q parameter is provided
        if q:
            return service.search_methods(
                query=q,
                page=page,
                page_size=page_size,
                include_trends=include_trends,
            )

        return service.get_methods(
            page=page,
            page_size=page_size,
            name=name,
            full_name=full_name,
            introduced_year=introduced_year,
            area_id=area_id,
            exclude_id=exclude_id,
            order_by=order_by,
            order_dir=order_dir,
            include_trends=include_trends,
        )
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{method_id}", response_model=Method)
def get_method(
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


@router.get("/{method_id}/trend", response_model=MethodTrend)
def get_method_trend(
    method_id: str,
    recent_days: int = Query(90, ge=1, le=365),
    baseline_days: int = Query(180, ge=1, le=730),
    history_months: int | None = Query(
        None,
        ge=1,
        le=600,
        description="Optional trailing-month override; omitted returns full history",
    ),
    db: Session = Depends(get_database_session),
):
    """Return complete monthly mention history and reference coverage."""
    try:
        return MethodTrendService(db).get_method_trend(
            method_id,
            recent_days=recent_days,
            baseline_days=baseline_days,
            history_months=history_months,
        )
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{method_id}/image")
def get_method_image(
    method_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Serve the DB-backed figure for a method by ID or slug.

    Returns the raw image bytes stored in `methods.image_data`. 404s when the
    method does not exist or has no stored image.
    """
    result = load_entity_image(db, DBMethod, method_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail="Image not available",
            headers=IMAGE_MISSING_HEADERS,
        )
    data, mime = result
    return Response(content=data, media_type=mime, headers=IMAGE_CACHE_HEADERS)


@router.get("/{method_id}/papers", response_model=Papers)
def get_method_papers(
    method_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of papers per page (max 100)"
    ),
    order_by: Optional[str] = Query(
        "date_published",
        description="Field to order by: date_published, citation_count, title, trending",
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
    - `/api/v1/methods/Transformer/papers?order_by=trending` - Papers ranked by official repo trending score
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


@router.post(
    "/{method_id}/keywords",
    response_model=Method,
    dependencies=[Depends(require_admin)],
)
def add_method_keywords(
    method_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Add keywords to a method (appends to existing keywords).

    Adds the specified keywords to the method's keyword list without removing
    existing keywords. Duplicates are automatically prevented.

    **Examples:**
    - `/api/v1/methods/function-calling/keywords` - Add keywords to "function calling" method
    - `/api/v1/methods/1/keywords` - Add keywords by method ID

    **Request body:**
    ```json
    {
        "keywords": ["function-calling", "tool-use"]
    }
    ```
    """
    try:
        service = MethodService(db)
        return service.add_keywords(method_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/{method_id}/keywords",
    response_model=Method,
    dependencies=[Depends(require_admin)],
)
def remove_method_keywords(
    method_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Remove specific keywords from a method.

    Removes the specified keywords from the method's keyword list.
    Keywords not present in the list are silently ignored.

    **Examples:**
    - `/api/v1/methods/function-calling/keywords` - Remove keywords from "function calling" method
    - `/api/v1/methods/1/keywords` - Remove keywords by method ID

    **Request body:**
    ```json
    {
        "keywords": ["old-keyword"]
    }
    ```
    """
    try:
        service = MethodService(db)
        return service.remove_keywords(method_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put(
    "/{method_id}/keywords",
    response_model=Method,
    dependencies=[Depends(require_admin)],
)
def replace_method_keywords(
    method_id: str,
    keyword_update: KeywordUpdate,
    db: Session = Depends(get_database_session),
):
    """
    Replace all keywords for a method.

    Replaces the entire keyword list with the provided keywords.
    All existing keywords are removed and replaced with the new list.

    **Examples:**
    - `/api/v1/methods/function-calling/keywords` - Replace all keywords for "function calling" method
    - `/api/v1/methods/1/keywords` - Replace keywords by method ID

    **Request body:**
    ```json
    {
        "keywords": ["function-calling", "tool-calling", "function-call"]
    }
    ```
    """
    try:
        service = MethodService(db)
        return service.replace_keywords(method_id, keyword_update.keywords)
    except PaperNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
