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
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
)
from backend.models.api import Evaluation, Evaluations
from backend.utils.exceptions import DatabaseError


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

            # Recalculate ranks for this leaderboard after creation
            self.recalculate_ranks(db_evaluation.task_id, db_evaluation.dataset_id)

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

            # Recalculate ranks for affected leaderboards
            # If task or dataset changed, recalculate both old and new leaderboards
            if (task_id is not None and task_id != old_task_id) or (
                dataset_id is not None and dataset_id != old_dataset_id
            ):
                # Recalculate old leaderboard (where evaluation was removed)
                self.recalculate_ranks(old_task_id, old_dataset_id)
                # Recalculate new leaderboard (where evaluation was added)
                self.recalculate_ranks(db_evaluation.task_id, db_evaluation.dataset_id)
            else:
                # Only recalculate current leaderboard if metrics or best_metric changed
                self.recalculate_ranks(db_evaluation.task_id, db_evaluation.dataset_id)

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

            # Store task_id and dataset_id before deletion for rank recalculation
            task_id = db_evaluation.task_id
            dataset_id = db_evaluation.dataset_id

            self.db.delete(db_evaluation)
            self.db.commit()

            # Recalculate ranks for this leaderboard after deletion
            self.recalculate_ranks(task_id, dataset_id)

            return True

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to delete evaluation: {str(e)}")

    def recalculate_ranks(
        self,
        task_id: int,
        dataset_id: int,
        uses_additional_data: Optional[bool] = None,
    ) -> int:
        """
        Recalculate ranks for all evaluations in a specific leaderboard.

        This method orders evaluations by their best_metric value (higher is better)
        and assigns ranks accordingly. Evaluations with the same metric value get the same rank.

        Args:
            task_id: Task ID to recalculate ranks for
            dataset_id: Dataset ID to recalculate ranks for
            uses_additional_data: If specified, only recalculate for evaluations with this value

        Returns:
            Number of evaluations updated

        Raises:
            DatabaseError: If database operation fails
        """
        try:
            # Build query for evaluations in this leaderboard
            query = self.db.query(DBEvaluation).filter(
                DBEvaluation.task_id == task_id,
                DBEvaluation.dataset_id == dataset_id,
            )

            # Optionally filter by uses_additional_data
            if uses_additional_data is not None:
                query = query.filter(
                    DBEvaluation.uses_additional_data == uses_additional_data
                )

            # Get all evaluations for this leaderboard
            evaluations = query.all()

            if not evaluations:
                return 0

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

            # Sort by metric value (descending - higher is better)
            # Place evaluations without valid metric values at the end
            eval_scores.sort(
                key=lambda x: (x[1] is None, -x[1] if x[1] is not None else 0)
            )

            # Assign ranks (same value = same rank)
            current_rank = 1
            previous_score = None
            updated_count = 0

            for idx, (eval_obj, score) in enumerate(eval_scores):
                # Skip evaluations without valid metric values
                if score is None:
                    eval_obj.best_rank = None
                    updated_count += 1
                    continue

                # If score is different from previous, update rank
                if previous_score is not None and score != previous_score:
                    current_rank = idx + 1

                eval_obj.best_rank = current_rank
                previous_score = score
                updated_count += 1

            # Commit all rank updates
            self.db.commit()

            return updated_count

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to recalculate ranks: {str(e)}")
