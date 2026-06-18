"""
Evaluations API router.

Provides endpoints for accessing benchmark evaluation data, including filtering by paper,
task, and dataset.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from backend.models.api import (
    Evaluation,
    Evaluations,
    EvaluationCreateRequest,
    EvaluationUpdateRequest,
)
from backend.services.evaluation_service import EvaluationService
from backend.database.connection import get_database_session
from backend.utils.auth import require_admin
from backend.utils.exceptions import DatabaseError

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


@router.get("/", response_model=Evaluations)
def list_evaluations(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(
        50, ge=1, le=100, description="Number of evaluations per page (max 100)"
    ),
    q: Optional[str] = Query(
        None, description="Search query for model name and methodology"
    ),
    paper_id: Optional[int] = Query(None, description="Filter by paper ID"),
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    include_descendants: bool = Query(
        False,
        description=(
            "When `task_id` is set, also include evaluations whose task is a "
            "descendant of `task_id`. Useful for parent task pages that want "
            "to roll up evaluations from their subtasks."
        ),
    ),
    dataset_id: Optional[int] = Query(None, description="Filter by dataset ID"),
    best_metric: Optional[str] = Query(
        None, description="Filter by best metric (e.g., 'AbsRel', 'delta1')"
    ),
    is_open: Optional[bool] = Query(
        None,
        description=(
            "Filter by open-source status of the evaluated model. "
            "Pass `true` to return only open-source rows (hides closed-source)."
        ),
    ),
    external: Optional[bool] = Query(
        None,
        description="Filter by external source attribution status.",
    ),
    ordering: Optional[str] = Query(
        "-created_at",
        description=(
            "Order by field: created_at, best_rank, evaluated_on, "
            "benchmark_popularity (prefix with '-' for descending). "
            "benchmark_popularity sorts each row by the total number of "
            "evaluations on its dataset across all papers, which keeps rows "
            "for the most popular benchmarks together at the top."
        ),
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
    - `/api/v1/evaluations/?paper_id=123&ordering=-benchmark_popularity` -
      Paper page rows grouped by most popular benchmark first
    """
    try:
        # Parse ordering
        order_dir = "asc"
        order_by = ordering
        if ordering and ordering.startswith("-"):
            order_dir = "desc"
            order_by = ordering[1:]

        # Validate order_by field
        valid_fields = [
            "created_at",
            "best_rank",
            "evaluated_on",
            "benchmark_popularity",
        ]
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
            include_descendants=include_descendants,
            dataset_id=dataset_id,
            best_metric=best_metric,
            is_open=is_open,
            external=external,
            order_by=order_by,
            order_dir=order_dir,
        )

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/{evaluation_id}", response_model=Evaluation)
def get_evaluation(
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


@router.post(
    "/",
    response_model=Evaluation,
    status_code=201,
    dependencies=[Depends(require_admin)],
)
def create_evaluation(
    request: EvaluationCreateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Create a new evaluation.

    Creates a new benchmark evaluation result for a paper on a specific task and dataset.

    **Metric Validation:**
    - All metrics in the `metrics` dictionary must be allowed for the specified leaderboard (task + dataset)
    - The `best_metric` must also be in the allowed metrics list
    - Use `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics` to see allowed metrics for a leaderboard
    - Leaderboards are defined by (task, dataset, metric) triples in the `task_dataset_metrics` table

    **Request Body:**
    ```json
    {
        "paper_id": 123,
        "task_id": 1,
        "dataset_id": 5,
        "model_name": "DETR",
        "metrics": {"AP": "44.9", "AP50": "64.7"},
        "best_rank": 1,
        "best_metric": "AP"
    }
    ```

    **Returns:**
    - 201: Created evaluation object with ID
    - 400: Invalid metrics for the dataset (see error message for allowed metrics)
    - 500: Internal server error
    """
    try:
        service = EvaluationService(db)
        return service.create_evaluation(
            paper_id=request.paper_id,
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            model_name=request.model_name,
            harness=request.harness,
            methodology=request.methodology,
            metrics=request.metrics,
            uses_additional_data=request.uses_additional_data,
            is_open=request.is_open,
            best_rank=request.best_rank,
            best_metric=request.best_metric,
            evaluated_on=request.evaluated_on,
            external_source_url=request.external_source_url,
            source_url=request.source_url,
            num_parameters=request.num_parameters,
            hf_model_url=request.hf_model_url,
        )

    except ValueError as e:
        # Validation error (invalid metrics for dataset)
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.put(
    "/{evaluation_id}",
    response_model=Evaluation,
    dependencies=[Depends(require_admin)],
)
def update_evaluation(
    evaluation_id: int,
    request: EvaluationUpdateRequest,
    db: Session = Depends(get_database_session),
):
    """
    Update an existing evaluation.

    Updates the fields of an existing evaluation. Only provided fields will be updated.

    **Metric Validation:**
    - If updating `metrics`, `task_id`, or `dataset_id`, all metrics must be allowed for the leaderboard
    - If updating `best_metric`, it must be in the allowed metrics list
    - Use `GET /api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics` to see allowed metrics for a leaderboard

    **Example:**
    ```
    PUT /api/v1/evaluations/123
    {
        "model_name": "DETR-R50",
        "metrics": {"AP": "45.2", "AP50": "65.1"},
        "best_rank": 2
    }
    ```

    **Returns:**
    - 200: Updated evaluation object
    - 400: Invalid metrics for the dataset
    - 404: Evaluation not found
    - 500: Internal server error
    """
    try:
        service = EvaluationService(db)
        return service.update_evaluation(
            evaluation_id=evaluation_id,
            task_id=request.task_id,
            dataset_id=request.dataset_id,
            model_name=request.model_name,
            harness=request.harness,
            methodology=request.methodology,
            metrics=request.metrics,
            uses_additional_data=request.uses_additional_data,
            is_open=request.is_open,
            best_rank=request.best_rank,
            best_metric=request.best_metric,
            evaluated_on=request.evaluated_on,
            external_source_url=request.external_source_url,
            source_url=request.source_url,
            num_parameters=request.num_parameters,
            hf_model_url=request.hf_model_url,
            harness_set="harness" in request.model_fields_set,
            source_url_set="source_url" in request.model_fields_set,
            num_parameters_set="num_parameters" in request.model_fields_set,
            hf_model_url_set="hf_model_url" in request.model_fields_set,
        )

    except ValueError as e:
        # Validation error (invalid metrics for dataset)
        raise HTTPException(status_code=400, detail=str(e))
    except DatabaseError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.delete(
    "/{evaluation_id}",
    status_code=204,
    dependencies=[Depends(require_admin)],
)
def delete_evaluation(
    evaluation_id: int,
    db: Session = Depends(get_database_session),
):
    """
    Delete an evaluation.

    Permanently deletes an evaluation by ID.

    **Example:**
    - `/api/v1/evaluations/123` - Delete evaluation with ID 123

    **Returns:**
    - 204 No Content on success
    """
    try:
        service = EvaluationService(db)
        service.delete_evaluation(evaluation_id)
        return None

    except DatabaseError as e:
        if "not found" in str(e).lower():
            raise HTTPException(status_code=404, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post(
    "/recalculate-ranks",
    status_code=200,
    dependencies=[Depends(require_admin)],
)
def recalculate_ranks(
    task_id: int = Query(..., description="Task ID for the leaderboard"),
    dataset_id: int = Query(..., description="Dataset ID for the leaderboard"),
    uses_additional_data: Optional[bool] = Query(
        None,
        description="If specified, only recalculate for evaluations with this value",
    ),
    db: Session = Depends(get_database_session),
):
    """
    Recalculate ranks for all evaluations in a specific leaderboard.

    This endpoint recalculates the best_rank field for all evaluations matching the
    specified task_id and dataset_id. Rankings are based on the best_metric value,
    with higher values receiving better (lower) ranks.

    **Example:**
    - `POST /api/v1/evaluations/recalculate-ranks?task_id=2&dataset_id=5` - Recalculate ranks for task 2 on dataset 5

    **Returns:**
    - JSON object with the number of evaluations updated
    """
    try:
        service = EvaluationService(db)
        updated_count = service.recalculate_ranks(
            task_id=task_id,
            dataset_id=dataset_id,
            uses_additional_data=uses_additional_data,
        )
        return {
            "message": f"Successfully recalculated ranks for {updated_count} evaluations",
            "task_id": task_id,
            "dataset_id": dataset_id,
            "updated_count": updated_count,
        }

    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
