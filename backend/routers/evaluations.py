"""
Evaluations API router.

Provides endpoints for accessing benchmark evaluation data, including filtering by paper,
task, and dataset.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import Evaluation, Evaluations
from backend.services.evaluation_service import EvaluationService
from backend.database.connection import get_database_session
from backend.utils.exceptions import DatabaseError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/", response_model=Evaluations)
async def list_evaluations(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of evaluations per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for model name and methodology"
    ),
    paper_id: Optional[int] = Query(None, description="Filter by paper ID"),
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    dataset_id: Optional[int] = Query(None, description="Filter by dataset ID"),
    ordering: Optional[str] = Query(
        "-created_at",
        description="Order by field: created_at, best_rank, evaluated_on (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of benchmark evaluations.

    Evaluations can be filtered by paper, task, dataset, or searched across model name and methodology.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/evaluations/` - Get all evaluations
    - `/api/v1/evaluations/?paper_id=123` - Get evaluations for paper ID 123
    - `/api/v1/evaluations/?task_id=2&dataset_id=1` - Get evaluations for task 2 on dataset 1
    - `/api/v1/evaluations/?q=DETR` - Search for evaluations containing "DETR"
    - `/api/v1/evaluations/?ordering=-best_rank` - Order by best rank descending
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = ["created_at", "best_rank", "evaluated_on"]
        if order_by not in valid_fields:
            order_by = "created_at"

        service = EvaluationService(db)

        # Use search if q parameter is provided
        if q:
            return service.search_evaluations(query=q, page=page, page_size=page_size)

        return service.get_evaluations(
            page=page,
            page_size=page_size,
            paper_id=paper_id,
            task_id=task_id,
            dataset_id=dataset_id,
            order_by=order_by,
            order_dir=order_dir,
        )

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{evaluation_id}", response_model=Evaluation)
async def get_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific evaluation by ID.

    **Example:**
    - `/api/v1/evaluations/1` - Get evaluation with ID 1
    """
    try:
        service = EvaluationService(db)
        evaluation = service.get_evaluation(evaluation_id)

        if not evaluation:
            raise HTTPException(
                status_code=404, detail=f"Evaluation {evaluation_id} not found"
            )

        return evaluation

    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
