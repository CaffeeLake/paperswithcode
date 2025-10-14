"""
Evaluation service for handling evaluation-related business logic.

This service provides methods for retrieving and managing benchmark evaluation data,
including pagination, filtering by paper, task, and dataset.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_

from backend.models.database import (
    Evaluation as DBEvaluation,
)
from backend.models.api import Evaluation, Evaluations
from backend.utils.exceptions import DatabaseError


class EvaluationService:
    """Service class for evaluation-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_evaluations(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        paper_id: Optional[int] = None,
        task_id: Optional[int] = None,
        dataset_id: Optional[int] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
    ) -> Evaluations:
        """
        Get a paginated list of benchmark evaluations with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of evaluations per page
            search: Search term for model name or methodology
            paper_id: Filter by paper ID
            task_id: Filter by task ID
            dataset_id: Filter by dataset ID
            order_by: Field to order by (created_at, best_rank, evaluated_on)
            order_dir: Order direction (asc, desc)

        Returns:
            Evaluations object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBEvaluation)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in model name and methodology
                query = query.filter(
                    or_(
                        DBEvaluation.model_name.ilike(f"%{search}%")
                        if DBEvaluation.model_name
                        else False,
                        DBEvaluation.methodology.ilike(f"%{search}%")
                        if DBEvaluation.methodology
                        else False,
                    )
                )

            if paper_id is not None:
                query = query.filter(DBEvaluation.paper_id == paper_id)

            if task_id is not None:
                query = query.filter(DBEvaluation.task_id == task_id)

            if dataset_id is not None:
                query = query.filter(DBEvaluation.dataset_id == dataset_id)

            # Get total count before pagination
            total_count = query.count()

            # Apply ordering
            if order_by == "created_at":
                order_field = DBEvaluation.created_at
            elif order_by == "best_rank":
                order_field = DBEvaluation.best_rank
            elif order_by == "evaluated_on":
                order_field = DBEvaluation.evaluated_on
            else:
                order_field = DBEvaluation.created_at

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            evaluation_list = []
            for db_evaluation in results:
                evaluation_dict = {
                    "id": str(db_evaluation.id),
                    "paper_id": str(db_evaluation.paper_id),
                    "task_id": str(db_evaluation.task_id),
                    "dataset_id": str(db_evaluation.dataset_id),
                    "model_name": db_evaluation.model_name,
                    "methodology": db_evaluation.methodology,
                    "metrics": db_evaluation.metrics,
                    "uses_additional_data": db_evaluation.uses_additional_data,
                    "best_rank": db_evaluation.best_rank,
                    "best_metric": db_evaluation.best_metric,
                    "evaluated_on": db_evaluation.evaluated_on,
                    "external_source_url": db_evaluation.external_source_url,
                    "created_at": db_evaluation.created_at,
                    "updated_at": db_evaluation.updated_at,
                }
                evaluation_list.append(Evaluation(**evaluation_dict))

            # Calculate pagination
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Evaluations(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=evaluation_list,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve evaluations: {str(e)}")

    def get_evaluation(self, evaluation_id: int) -> Optional[Evaluation]:
        """
        Get a specific evaluation by ID.

        Args:
            evaluation_id: Evaluation ID

        Returns:
            Evaluation object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                return None

            evaluation_dict = {
                "id": str(db_evaluation.id),
                "paper_id": str(db_evaluation.paper_id),
                "task_id": str(db_evaluation.task_id),
                "dataset_id": str(db_evaluation.dataset_id),
                "model_name": db_evaluation.model_name,
                "methodology": db_evaluation.methodology,
                "metrics": db_evaluation.metrics,
                "uses_additional_data": db_evaluation.uses_additional_data,
                "best_rank": db_evaluation.best_rank,
                "best_metric": db_evaluation.best_metric,
                "evaluated_on": db_evaluation.evaluated_on,
                "external_source_url": db_evaluation.external_source_url,
                "created_at": db_evaluation.created_at,
                "updated_at": db_evaluation.updated_at,
            }

            return Evaluation(**evaluation_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve evaluation: {str(e)}")

    def search_evaluations(
        self, query: str, page: int = 1, page_size: int = 50
    ) -> Evaluations:
        """
        Search evaluations by model name or methodology.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of evaluations per page

        Returns:
            Evaluations object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_evaluations(
            page=page,
            page_size=page_size,
            search=query,
            order_by="created_at",
            order_dir="desc",
        )

    def create_evaluation(
        self,
        paper_id: int,
        task_id: int,
        dataset_id: int,
        metrics: dict,
        model_name: Optional[str] = None,
        methodology: Optional[str] = None,
        uses_additional_data: bool = False,
        best_rank: Optional[int] = None,
        best_metric: Optional[str] = None,
        evaluated_on: Optional[str] = None,
        external_source_url: Optional[str] = None,
    ) -> Evaluation:
        """
        Create a new evaluation.

        Args:
            paper_id: Paper ID
            task_id: Task ID
            dataset_id: Dataset ID
            metrics: Dictionary of metric names and values
            model_name: Model name
            methodology: Methodology description
            uses_additional_data: Whether additional data was used
            best_rank: Best rank achieved
            best_metric: Name of best metric
            evaluated_on: Evaluation date
            external_source_url: External source URL

        Returns:
            Created Evaluation object

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            db_evaluation = DBEvaluation(
                paper_id=paper_id,
                task_id=task_id,
                dataset_id=dataset_id,
                model_name=model_name,
                methodology=methodology,
                metrics=metrics,
                uses_additional_data=uses_additional_data,
                best_rank=best_rank,
                best_metric=best_metric,
                evaluated_on=evaluated_on,
                external_source_url=external_source_url,
            )

            self.db.add(db_evaluation)
            self.db.commit()
            self.db.refresh(db_evaluation)

            evaluation_dict = {
                "id": str(db_evaluation.id),
                "paper_id": str(db_evaluation.paper_id),
                "task_id": str(db_evaluation.task_id),
                "dataset_id": str(db_evaluation.dataset_id),
                "model_name": db_evaluation.model_name,
                "methodology": db_evaluation.methodology,
                "metrics": db_evaluation.metrics,
                "uses_additional_data": db_evaluation.uses_additional_data,
                "best_rank": db_evaluation.best_rank,
                "best_metric": db_evaluation.best_metric,
                "evaluated_on": db_evaluation.evaluated_on,
                "external_source_url": db_evaluation.external_source_url,
                "created_at": db_evaluation.created_at,
                "updated_at": db_evaluation.updated_at,
            }

            return Evaluation(**evaluation_dict)

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create evaluation: {str(e)}")
