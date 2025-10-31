"""
Datasets API router.

Provides endpoints for accessing benchmark dataset data, including filtering by task,
paper associations, and evaluation data.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import (
    Dataset,
    Datasets,
    DatasetCreateRequest,
    DatasetMetrics,
    DatasetMetricAddRequest,
    DatasetMetricSetRequest,
    DatasetMetricLink,
)
from backend.services.dataset_service import DatasetService
from backend.services.dataset_metric_service import DatasetMetricService
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


@router.post("/", response_model=Dataset, status_code=201)
async def create_dataset(
    request: DatasetCreateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Create a new dataset and link it to specified tasks.

    Creates a new benchmark dataset with the provided information and automatically
    links it to the specified tasks. The dataset slug is auto-generated from the name.

    **Request Body:**
    ```json
    {
        "name": "Video-MMLU",
        "full_name": "Video-MMLU: A Massive Multi-Discipline Lecture Understanding Benchmark",
        "description": "A comprehensive benchmark for evaluating Large Multimodal Models",
        "url": "https://enxinsong.com/Video-MMLU-web/",
        "hf_url": "https://huggingface.co/datasets/Enxin/Video-MMLU",
        "paper_url": "https://arxiv.org/abs/2504.14693",
        "task_ids": [9],
        "modalities": ["Videos", "Text"],
        "languages": ["English"],
        "license_name": "MIT",
        "introduced_date": "2025-01-01"
    }
    ```

    **Returns:**
    - Created dataset object with auto-generated slug and task associations
    - 201 status code on success

    **Errors:**
    - 400: Invalid request data or missing required fields
    - 404: One or more task IDs not found
    - 409: Dataset with the same slug already exists
    - 500: Internal server error
    """
    try:
        service = DatasetService(db)
        return service.create_dataset(request)

    except ValueError as e:
        if "Task IDs not found" in str(e):
            raise HTTPException(status_code=404, detail=str(e))
        elif "already exists" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# Dataset-Metric Management Endpoints


@router.get("/{dataset_id}/metrics", response_model=DatasetMetrics)
async def get_dataset_metrics(
    dataset_id: str,
    db: Session = Depends(get_database_session),
):
    """
    Get all allowed metrics for a dataset.

    Returns the list of metrics that are valid for evaluation submissions
    on this dataset. These metrics are enforced when creating or updating evaluations.

    **Example:**
    - `/api/v1/datasets/6/metrics` - Get allowed metrics for dataset 6

    **Returns:**
    ```json
    {
        "dataset_id": "6",
        "dataset_name": "COCO",
        "metrics": [
            {
                "dataset_id": "6",
                "metric_id": "1",
                "metric_name": "AP",
                "metric_direction": "higher_is_better",
                "created_at": "2025-10-24T12:00:00Z"
            },
            ...
        ]
    }
    ```
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        service = DatasetMetricService(db)
        return service.get_dataset_metrics(dataset_id_int)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/{dataset_id}/metrics", response_model=DatasetMetricLink, status_code=201)
async def add_metric_to_dataset(
    dataset_id: str,
    request: DatasetMetricAddRequest,
    db: Session = Depends(get_database_session),
):
    """
    Add a metric to a dataset's allowed metrics list.

    Links a metric to a dataset, allowing evaluations to use this metric
    when submitting results for this dataset.

    **Example:**
    ```
    POST /api/v1/datasets/6/metrics
    {
        "metric_name": "AP50"
    }
    ```

    **Returns:**
    - 201 status with the created link
    - 400 if dataset or metric not found
    - 409 if metric is already linked to dataset
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        service = DatasetMetricService(db)
        return service.add_metric_to_dataset(dataset_id_int, request.metric_name)

    except ValueError as e:
        if "already linked" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        else:
            raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put("/{dataset_id}/metrics", response_model=DatasetMetrics)
async def set_dataset_metrics(
    dataset_id: str,
    request: DatasetMetricSetRequest,
    db: Session = Depends(get_database_session),
):
    """
    Set all allowed metrics for a dataset (replaces existing).

    Replaces all existing metric links with the provided list. This is useful
    for bulk configuration of dataset metrics.

    **Example:**
    ```
    PUT /api/v1/datasets/6/metrics
    {
        "metric_names": ["AP", "AP50", "AP75", "APs", "APm", "APl"]
    }
    ```

    **Returns:**
    - Updated DatasetMetrics object
    - 404 if dataset or any metric not found
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        service = DatasetMetricService(db)
        return service.set_dataset_metrics(dataset_id_int, request.metric_names)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete("/{dataset_id}/metrics/{metric_name}", status_code=204)
async def remove_metric_from_dataset(
    dataset_id: str,
    metric_name: str,
    db: Session = Depends(get_database_session),
):
    """
    Remove a metric from a dataset's allowed metrics list.

    Unlinks a metric from a dataset. After removal, evaluations can no longer
    use this metric when submitting results for this dataset.

    **Example:**
    - `DELETE /api/v1/datasets/6/metrics/AP50` - Remove AP50 from dataset 6

    **Returns:**
    - 204 No Content on success
    - 404 if dataset, metric, or link not found
    """
    try:
        # Parse dataset_id
        try:
            dataset_id_int = int(dataset_id)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid dataset ID. Must be an integer."
            )

        service = DatasetMetricService(db)
        service.remove_metric_from_dataset(dataset_id_int, metric_name)
        return None

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
