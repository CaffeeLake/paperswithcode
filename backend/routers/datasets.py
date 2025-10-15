"""
Datasets API router.

Provides endpoints for accessing benchmark dataset data, including filtering by task,
paper associations, and evaluation data.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import Dataset, Datasets
from backend.services.dataset_service import DatasetService
from backend.database.connection import get_database_session
from backend.utils.exceptions import DatabaseError

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("/", response_model=Datasets)
async def list_datasets(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of datasets per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for dataset name, full name, and description"
    ),
    name: Optional[str] = Query(
        None, description="Filter by partial dataset name match"
    ),
    full_name: Optional[str] = Query(
        None, description="Filter by partial full name match"
    ),
    task: Optional[str] = Query(None, description="Filter by task ID or task slug"),
    ordering: Optional[str] = Query(
        "name",
        description="Order by field: name, full_name, created_at (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get a paginated list of benchmark datasets.

    Datasets can be filtered by name, task, or searched across name and description.
    Supports ordering and pagination.

    **Example queries:**
    - `/api/v1/datasets/` - Get all datasets
    - `/api/v1/datasets/?task=123` - Get datasets for task ID 123
    - `/api/v1/datasets/?q=imagenet` - Search for datasets containing "imagenet"
    - `/api/v1/datasets/?name=COCO` - Filter datasets by name containing "COCO"
    - `/api/v1/datasets/?ordering=-name` - Order by name descending
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = ["name", "full_name", "created_at"]
        if order_by not in valid_fields:
            order_by = "name"

        service = DatasetService(db)

        # Parse task parameter (could be ID or slug)
        task_id = None
        if task:
            try:
                task_id = int(task)
            except ValueError:
                # If not an integer, treat as slug and look up task ID
                from backend.models.database import Task as DBTask

                task_obj = db.query(DBTask).filter(DBTask.slug == task).first()
                if task_obj:
                    task_id = task_obj.id

        # Use search if q parameter is provided
        if q:
            return service.search_datasets(query=q, page=page, page_size=page_size)

        return service.get_datasets(
            page=page,
            page_size=page_size,
            name=name,
            full_name=full_name,
            task_id=task_id,
            order_by=order_by,
            order_dir=order_dir,
        )

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_id}", response_model=Dataset)
async def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get a specific dataset by its ID or slug.

    Returns detailed information about the dataset including name, description,
    URLs, and metadata about associated papers and tasks.

    **Example:**
    - `/api/v1/datasets/123` - Get dataset with ID 123
    - `/api/v1/datasets/coco` - Get dataset with slug "coco"
    """
    try:
        service = DatasetService(db)

        # Try to parse as integer ID first
        try:
            dataset_id_int = int(dataset_id)
            dataset = service.get_dataset(dataset_id_int)
        except ValueError:
            # Not an integer, treat as slug
            dataset = service.get_dataset_by_slug(dataset_id)

        if not dataset:
            raise HTTPException(
                status_code=404,
                detail=f"Dataset with ID or slug '{dataset_id}' not found",
            )

        return dataset

    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{dataset_id}/evaluations/", response_model=dict)
async def get_dataset_evaluations(
    dataset_id: str,
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of evaluations per page (max 100)"
    ),
    ordering: Optional[str] = Query(
        "-best_rank",
        description="Order by field: created_at, best_rank, evaluated_on (prefix with '-' for descending)",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Get evaluation results for a specific dataset.

    Returns paginated list of benchmark evaluation results for papers evaluated on this dataset.
    This endpoint matches the legacy PapersWithCode API pattern.

    **Example:**
    - `/api/v1/datasets/123/evaluations/` - Get evaluations for dataset 123
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        dataset_service = DatasetService(db)

        # Check if dataset exists
        dataset = dataset_service.get_dataset(dataset_id_int)
        if not dataset:
            raise HTTPException(
                status_code=404, detail=f"Dataset with ID {dataset_id} not found"
            )

        # Parse ordering
        order_dir = "asc"
        order_by = "created_at"
        if ordering:
            if ordering.startswith("-"):
                order_dir = "desc"
                order_by = ordering[1:]
            else:
                order_dir = "asc"
                order_by = ordering

        # Use EvaluationService to fetch actual evaluation data
        from backend.services.evaluation_service import EvaluationService

        evaluation_service = EvaluationService(db)
        evaluations_response = evaluation_service.get_evaluations(
            page=page,
            page_size=page_size,
            dataset_id=dataset_id_int,
            order_by=order_by,
            order_dir=order_dir,
        )

        # Return in the expected format
        return {
            "count": evaluations_response.count,
            "next_page": evaluations_response.next_page,
            "previous_page": evaluations_response.previous_page,
            "results": [eval.model_dump() for eval in evaluations_response.results],
        }

    except HTTPException:
        raise
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
