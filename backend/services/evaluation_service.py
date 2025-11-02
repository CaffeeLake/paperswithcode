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
    Paper as DBPaper,
    Task as DBTask,
    Dataset as DBDataset,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    TaskDataset,
    Metric as DBMetric,
)
from backend.models.api import Evaluation, Evaluations
from backend.utils.exceptions import DatabaseError
from backend.services.leaderboard_metric_service import LeaderboardMetricService


class EvaluationService:
    """Service class for evaluation-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def _get_paper_info(
        self, paper_id: int
    ) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
        """
        Get paper title, ArXiv ID, code URL, and publication date for a given paper ID.

        Returns:
            Tuple of (paper_title, paper_arxiv_id, code_url, paper_published_date)
        """
        try:
            # Get paper title, ArXiv ID, and publication date
            paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            paper_title = paper.title if paper else None
            paper_arxiv_id = paper.arxiv_id if paper else None
            paper_published_date = (
                str(paper.date_published) if paper and paper.date_published else None
            )

            # Get code URL (first repository for the paper)
            code_url = None
            repo_link = (
                self.db.query(DBRepository)
                .join(
                    DBPaperRepository,
                    DBRepository.id == DBPaperRepository.repository_id,
                )
                .filter(DBPaperRepository.paper_id == paper_id)
                .order_by(DBPaperRepository.is_official.desc())  # Prefer official repos
                .first()
            )
            if repo_link:
                code_url = repo_link.url

            return paper_title, paper_arxiv_id, code_url, paper_published_date
        except Exception:
            return None, None, None, None

    def _get_task_name(self, task_id: int) -> Optional[str]:
        """
        Get task name for a given task ID.

        Returns:
            Task name or None if not found
        """
        try:
            task = self.db.query(DBTask).filter(DBTask.id == task_id).first()
            return task.name if task else None
        except Exception:
            return None

    def _get_dataset_name(self, dataset_id: int) -> Optional[str]:
        """
        Get dataset name for a given dataset ID.

        Returns:
            Dataset name or None if not found
        """
        try:
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            return dataset.name if dataset else None
        except Exception:
            return None

    def _get_dataset_slug(self, dataset_id: int) -> Optional[str]:
        """
        Get dataset slug for a given dataset ID.

        Returns:
            Dataset slug or None if not found
        """
        try:
            dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            return dataset.slug if dataset else None
        except Exception:
            return None

    def _link_dataset_to_task(self, task_id: int, dataset_id: int) -> bool:
        """
        Link a dataset to a task via the task_datasets junction table.

        This ensures the dataset appears in the task's leaderboards section.
        If the link already exists, this method does nothing.

        Args:
            task_id: Task ID
            dataset_id: Dataset ID

        Returns:
            True if the link was created or already exists
        """
        try:
            # Check if link already exists
            existing_link = (
                self.db.query(TaskDataset)
                .filter(
                    TaskDataset.task_id == task_id,
                    TaskDataset.dataset_id == dataset_id,
                )
                .first()
            )

            if existing_link:
                return True

            # Create the link
            task_dataset = TaskDataset(task_id=task_id, dataset_id=dataset_id)

            self.db.add(task_dataset)
            self.db.flush()  # Flush to DB without committing (will commit with evaluation)

            return True
        except Exception as e:
            # Log the error for debugging purposes
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to link dataset {dataset_id} to task {task_id}: {str(e)}"
            )
            # If linking fails, we still want the evaluation to succeed
            # The dataset can be linked manually later if needed
            return False

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
                # Get paper info (title, ArXiv ID, code URL, and publication date)
                paper_title, paper_arxiv_id, code_url, paper_published_date = (
                    self._get_paper_info(db_evaluation.paper_id)
                )

                # Get task and dataset names
                task_name = self._get_task_name(db_evaluation.task_id)
                dataset_name = self._get_dataset_name(db_evaluation.dataset_id)
                dataset_slug = self._get_dataset_slug(db_evaluation.dataset_id)

                # Use external_source_url if available, otherwise use paper ArXiv URL as fallback
                result_url = db_evaluation.external_source_url
                if not result_url and paper_arxiv_id:
                    result_url = f"https://arxiv.org/abs/{paper_arxiv_id}"

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
                    "paper_title": paper_title,
                    "paper_arxiv_id": paper_arxiv_id,
                    "code_url": code_url,
                    "paper_published_date": paper_published_date,
                    "result_url": result_url,
                    "task_name": task_name,
                    "dataset_name": dataset_name,
                    "dataset_slug": dataset_slug,
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

            # Get paper info (title, ArXiv ID, code URL, and publication date)
            paper_title, paper_arxiv_id, code_url, paper_published_date = (
                self._get_paper_info(db_evaluation.paper_id)
            )

            # Get task and dataset names
            task_name = self._get_task_name(db_evaluation.task_id)
            dataset_name = self._get_dataset_name(db_evaluation.dataset_id)
            dataset_slug = self._get_dataset_slug(db_evaluation.dataset_id)

            # Use external_source_url if available, otherwise use paper ArXiv URL as fallback
            result_url = db_evaluation.external_source_url
            if not result_url and paper_arxiv_id:
                result_url = f"https://arxiv.org/abs/{paper_arxiv_id}"

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
                "paper_title": paper_title,
                "paper_arxiv_id": paper_arxiv_id,
                "code_url": code_url,
                "paper_published_date": paper_published_date,
                "result_url": result_url,
                "task_name": task_name,
                "dataset_name": dataset_name,
                "dataset_slug": dataset_slug,
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
            ValueError: If metrics are not valid for this dataset
            DatabaseError: If database operation fails
        """
        try:
            # Validate metrics against leaderboard's allowed metrics
            metric_service = LeaderboardMetricService(self.db)
            metric_keys = list(metrics.keys())
            is_valid, error_message = metric_service.validate_metrics_for_leaderboard(
                task_id, dataset_id, metric_keys, best_metric
            )

            if not is_valid:
                raise ValueError(error_message)

            # Link the dataset to the task if not already linked
            # This ensures the dataset appears in the task's leaderboards section
            self._link_dataset_to_task(task_id, dataset_id)

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

            # Recalculate ranks for this leaderboard after creation
            # Recalculate only for the specific metric if best_metric is set
            self.recalculate_ranks(
                db_evaluation.task_id,
                db_evaluation.dataset_id,
                metric_name=db_evaluation.best_metric,
            )

            # Refresh to get updated rank
            self.db.refresh(db_evaluation)

            # Get paper info (title, ArXiv ID, and code URL)
            paper_title, paper_arxiv_id, code_url, paper_published_date = (
                self._get_paper_info(db_evaluation.paper_id)
            )

            # Use external_source_url if available, otherwise use paper ArXiv URL as fallback
            result_url = db_evaluation.external_source_url
            if not result_url and paper_arxiv_id:
                result_url = f"https://arxiv.org/abs/{paper_arxiv_id}"

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
                "paper_title": paper_title,
                "paper_arxiv_id": paper_arxiv_id,
                "code_url": code_url,
                "paper_published_date": paper_published_date,
                "result_url": result_url,
            }

            return Evaluation(**evaluation_dict)

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create evaluation: {str(e)}")

    def update_evaluation(
        self,
        evaluation_id: int,
        task_id: Optional[int] = None,
        dataset_id: Optional[int] = None,
        model_name: Optional[str] = None,
        methodology: Optional[str] = None,
        metrics: Optional[dict] = None,
        uses_additional_data: Optional[bool] = None,
        best_rank: Optional[int] = None,
        best_metric: Optional[str] = None,
        evaluated_on: Optional[str] = None,
        external_source_url: Optional[str] = None,
    ) -> Evaluation:
        """
        Update an existing evaluation.

        Args:
            evaluation_id: Evaluation ID to update
            task_id: Task ID (changing this moves evaluation to different leaderboard)
            dataset_id: Dataset ID (changing this moves evaluation to different leaderboard)
            model_name: Model name
            methodology: Methodology description
            metrics: Dictionary of metric names and values
            uses_additional_data: Whether additional data was used
            best_rank: Best rank achieved
            best_metric: Name of best metric
            evaluated_on: Evaluation date
            external_source_url: External source URL

        Returns:
            Updated Evaluation object

        Raises:
            ValueError: If metrics are not valid for this dataset
            DatabaseError: If database operation fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                raise DatabaseError(f"Evaluation {evaluation_id} not found")

            # Store old task_id and dataset_id for rank recalculation
            old_task_id = db_evaluation.task_id
            old_dataset_id = db_evaluation.dataset_id

            # Determine which dataset to validate against
            target_dataset_id = dataset_id if dataset_id is not None else old_dataset_id

            # Determine which metrics and best_metric to validate
            target_metrics = metrics if metrics is not None else db_evaluation.metrics
            target_best_metric = (
                best_metric if best_metric is not None else db_evaluation.best_metric
            )

            # Determine which task to validate against
            target_task_id = task_id if task_id is not None else old_task_id

            # Validate metrics if they are being changed or task/dataset is changing
            if (
                metrics is not None
                or dataset_id is not None
                or task_id is not None
                or best_metric is not None
            ):
                metric_service = LeaderboardMetricService(self.db)
                metric_keys = list(target_metrics.keys())
                is_valid, error_message = (
                    metric_service.validate_metrics_for_leaderboard(
                        target_task_id,
                        target_dataset_id,
                        metric_keys,
                        target_best_metric,
                    )
                )

                if not is_valid:
                    raise ValueError(error_message)

            # Update only provided fields
            if task_id is not None:
                db_evaluation.task_id = task_id
            if dataset_id is not None:
                db_evaluation.dataset_id = dataset_id
            if model_name is not None:
                db_evaluation.model_name = model_name
            if methodology is not None:
                db_evaluation.methodology = methodology
            if metrics is not None:
                db_evaluation.metrics = metrics
            if uses_additional_data is not None:
                db_evaluation.uses_additional_data = uses_additional_data
            if best_rank is not None:
                db_evaluation.best_rank = best_rank
            if best_metric is not None:
                db_evaluation.best_metric = best_metric
            if evaluated_on is not None:
                db_evaluation.evaluated_on = evaluated_on
            if external_source_url is not None:
                db_evaluation.external_source_url = external_source_url

            self.db.commit()
            self.db.refresh(db_evaluation)

            # Store old best_metric for rank recalculation
            old_best_metric = (
                self.db.query(DBEvaluation.best_metric)
                .filter(DBEvaluation.id == evaluation_id)
                .scalar()
            )

            # Recalculate ranks for affected leaderboards
            # If task or dataset changed, recalculate both old and new leaderboards
            if (task_id is not None and task_id != old_task_id) or (
                dataset_id is not None and dataset_id != old_dataset_id
            ):
                # Recalculate old leaderboard (where evaluation was removed)
                self.recalculate_ranks(
                    old_task_id, old_dataset_id, metric_name=old_best_metric
                )
                # Recalculate new leaderboard (where evaluation was added)
                self.recalculate_ranks(
                    db_evaluation.task_id,
                    db_evaluation.dataset_id,
                    metric_name=db_evaluation.best_metric,
                )
            elif best_metric is not None and best_metric != old_best_metric:
                # If best_metric changed, recalculate both old and new metric leaderboards
                self.recalculate_ranks(
                    db_evaluation.task_id,
                    db_evaluation.dataset_id,
                    metric_name=old_best_metric,
                )
                self.recalculate_ranks(
                    db_evaluation.task_id,
                    db_evaluation.dataset_id,
                    metric_name=db_evaluation.best_metric,
                )
            else:
                # Only recalculate current leaderboard for current metric
                self.recalculate_ranks(
                    db_evaluation.task_id,
                    db_evaluation.dataset_id,
                    metric_name=db_evaluation.best_metric,
                )

            # Refresh to get updated rank
            self.db.refresh(db_evaluation)

            # Get paper info (title, ArXiv ID, and code URL)
            paper_title, paper_arxiv_id, code_url, paper_published_date = (
                self._get_paper_info(db_evaluation.paper_id)
            )

            # Use external_source_url if available, otherwise use paper ArXiv URL as fallback
            result_url = db_evaluation.external_source_url
            if not result_url and paper_arxiv_id:
                result_url = f"https://arxiv.org/abs/{paper_arxiv_id}"

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
                "paper_title": paper_title,
                "paper_arxiv_id": paper_arxiv_id,
                "code_url": code_url,
                "paper_published_date": paper_published_date,
                "result_url": result_url,
            }

            return Evaluation(**evaluation_dict)

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to update evaluation: {str(e)}")

    def delete_evaluation(self, evaluation_id: int) -> bool:
        """
        Delete an evaluation.

        Args:
            evaluation_id: Evaluation ID to delete

        Returns:
            True if deletion was successful

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            db_evaluation = (
                self.db.query(DBEvaluation)
                .filter(DBEvaluation.id == evaluation_id)
                .first()
            )

            if not db_evaluation:
                raise DatabaseError(f"Evaluation {evaluation_id} not found")

            # Store task_id, dataset_id, and best_metric before deletion for rank recalculation
            task_id = db_evaluation.task_id
            dataset_id = db_evaluation.dataset_id
            best_metric = db_evaluation.best_metric

            self.db.delete(db_evaluation)
            self.db.commit()

            # Recalculate ranks for this leaderboard after deletion
            self.recalculate_ranks(task_id, dataset_id, metric_name=best_metric)

            return True

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to delete evaluation: {str(e)}")

    def recalculate_ranks(
        self,
        task_id: int,
        dataset_id: int,
        metric_name: Optional[str] = None,
        uses_additional_data: Optional[bool] = None,
    ) -> int:
        """
        Recalculate ranks for evaluations in a specific leaderboard.

        This method orders evaluations by their best_metric value and assigns ranks accordingly.
        The ranking direction (higher is better vs lower is better) is determined by the
        metrics table. Evaluations with the same metric value get the same rank.

        Leaderboards are now defined by (task, dataset, metric) triples. If metric_name is
        provided, only recalculates ranks for that specific metric. If None, recalculates
        for all metrics present in evaluations for this task-dataset pair.

        Args:
            task_id: Task ID to recalculate ranks for
            dataset_id: Dataset ID to recalculate ranks for
            metric_name: Optional metric name to recalculate ranks for. If None, recalculates all.
            uses_additional_data: If specified, only recalculate for evaluations with this value

        Returns:
            Number of evaluations updated

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # If metric_name is provided, recalculate only for that metric
            # Otherwise, recalculate for all unique metrics in this task-dataset pair
            if metric_name:
                metrics_to_process = [metric_name]
            else:
                # Get all unique best_metric values for this task-dataset pair
                unique_metrics = (
                    self.db.query(DBEvaluation.best_metric)
                    .filter(
                        DBEvaluation.task_id == task_id,
                        DBEvaluation.dataset_id == dataset_id,
                        DBEvaluation.best_metric.isnot(None),
                    )
                    .distinct()
                    .all()
                )
                metrics_to_process = [m[0] for m in unique_metrics]

            if not metrics_to_process:
                return 0

            total_updated = 0

            # Process each metric separately
            for current_metric in metrics_to_process:
                # Build query for evaluations in this specific leaderboard (task, dataset, metric)
                query = self.db.query(DBEvaluation).filter(
                    DBEvaluation.task_id == task_id,
                    DBEvaluation.dataset_id == dataset_id,
                    DBEvaluation.best_metric == current_metric,
                )

                # Optionally filter by uses_additional_data
                if uses_additional_data is not None:
                    query = query.filter(
                        DBEvaluation.uses_additional_data == uses_additional_data
                    )

                # Get all evaluations for this leaderboard
                evaluations = query.all()

                if not evaluations:
                    continue

                # Determine the ranking direction from the metrics table
                metric_direction = "higher_is_better"  # Default

                # Query metrics table for ranking direction
                metric_def = (
                    self.db.query(DBMetric)
                    .filter(DBMetric.name == current_metric)
                    .first()
                )

                if metric_def:
                    metric_direction = metric_def.direction
                else:
                    # Log warning if metric not found in database
                    import logging

                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Metric '{current_metric}' not found in metrics table. "
                        f"Defaulting to 'higher_is_better' for ranking."
                    )

                # Extract metric values for sorting - rank ALL evaluations together
                # (uses_additional_data is displayed as a tag but doesn't affect ranking)
                eval_scores = []
                for eval_obj in evaluations:
                    # Get the value of the best_metric from metrics dict
                    metric_value = None
                    if eval_obj.best_metric and eval_obj.metrics:
                        # Handle both string and numeric metric values
                        raw_value = eval_obj.metrics.get(eval_obj.best_metric)
                        if raw_value is not None:
                            try:
                                # Convert to float for comparison
                                metric_value = float(raw_value)
                            except (ValueError, TypeError):
                                # If conversion fails, skip this evaluation
                                pass

                    eval_scores.append((eval_obj, metric_value))

                # Sort by metric value based on direction
                # Place evaluations without valid metric values at the end
                if metric_direction == "lower_is_better":
                    # For "lower is better" metrics (WER, error rates, perplexity)
                    # Lower values should get rank 1
                    eval_scores.sort(
                        key=lambda x: (
                            x[1] is None,
                            x[1] if x[1] is not None else float("inf"),
                        )
                    )
                else:
                    # For "higher is better" metrics (AP, accuracy, F1)
                    # Higher values should get rank 1 (default behavior)
                    eval_scores.sort(
                        key=lambda x: (x[1] is None, -x[1] if x[1] is not None else 0)
                    )

                # Assign ranks (same value = same rank)
                current_rank = 1
                previous_score = None

                for idx, (eval_obj, score) in enumerate(eval_scores):
                    # Skip evaluations without valid metric values
                    if score is None:
                        eval_obj.best_rank = None
                        total_updated += 1
                        continue

                    # If score is different from previous, update rank
                    if previous_score is not None and score != previous_score:
                        current_rank = idx + 1

                    eval_obj.best_rank = current_rank
                    previous_score = score
                    total_updated += 1

            # Commit all rank updates
            self.db.commit()

            return total_updated

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to recalculate ranks: {str(e)}")
