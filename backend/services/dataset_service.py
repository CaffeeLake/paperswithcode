"""
Dataset service for handling dataset-related business logic.

This service provides methods for retrieving and managing benchmark dataset data,
including pagination, filtering, paper associations, and evaluation data.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import (
    Dataset as DBDataset,
    PaperDataset,
    TaskDataset,
    Evaluation as DBEvaluation,
)
from backend.models.api import Dataset, Datasets
from backend.utils.exceptions import DatabaseError


class DatasetService:
    """Service class for dataset-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_datasets(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        task_id: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Datasets:
        """
        Get a paginated list of benchmark datasets with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of datasets per page
            search: Search term for dataset name and description (full-text search)
            name: Filter by partial dataset name match
            full_name: Filter by partial full name match
            task_id: Filter by associated task ID (e.g., datasets for "Image Classification")
            order_by: Field to order by (name, full_name, created_at)
            order_dir: Order direction (asc, desc)

        Returns:
            Datasets object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with paper count
            query = (
                self.db.query(
                    DBDataset,
                    func.count(PaperDataset.paper_id).label("paper_count"),
                    func.count(TaskDataset.task_id).label("task_count"),
                )
                .outerjoin(PaperDataset, DBDataset.id == PaperDataset.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .group_by(DBDataset.id)
            )

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in name and description
                query = query.filter(
                    or_(
                        DBDataset.name.ilike(f"%{search}%"),
                        DBDataset.full_name.ilike(f"%{search}%")
                        if DBDataset.full_name
                        else False,
                        DBDataset.description.ilike(f"%{search}%")
                        if DBDataset.description
                        else False,
                    )
                )

            if name:
                query = query.filter(DBDataset.name.ilike(f"%{name}%"))

            if full_name:
                query = query.filter(DBDataset.full_name.ilike(f"%{full_name}%"))

            if task_id is not None:
                # Filter datasets by task association
                query = query.filter(
                    DBDataset.id.in_(
                        self.db.query(TaskDataset.dataset_id).filter(
                            TaskDataset.task_id == task_id
                        )
                    )
                )

            # Get total count before pagination
            total_count = query.count()

            # Apply ordering
            if order_by == "name":
                order_field = DBDataset.name
            elif order_by == "full_name":
                order_field = DBDataset.full_name
            elif order_by == "created_at":
                order_field = DBDataset.created_at
            else:
                order_field = DBDataset.name

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            dataset_list = []
            for db_dataset, paper_count, task_count in results:
                dataset_dict = {
                    "id": str(db_dataset.id),
                    "name": db_dataset.name,
                    "slug": db_dataset.slug,
                    "full_name": db_dataset.full_name,
                    "description": db_dataset.description,
                    "url": db_dataset.url,
                    "hf_url": db_dataset.hf_url,
                    # PWC enriched fields
                    "short_description": db_dataset.short_description,
                    "homepage": db_dataset.homepage,
                    "parent_dataset_id": str(db_dataset.parent_dataset_id)
                    if db_dataset.parent_dataset_id
                    else None,
                    "image_url": db_dataset.image_url,
                    "thumbnail_url": db_dataset.thumbnail_url,
                    "verified_image_url": db_dataset.verified_image_url,
                    "introducing_paper_id": str(db_dataset.introducing_paper_id)
                    if db_dataset.introducing_paper_id
                    else None,
                    "introducing_paper_title": db_dataset.introducing_paper_title,
                    "license_name": db_dataset.license_name,
                    "license_url": db_dataset.license_url,
                    "introduced_date": db_dataset.introduced_date,
                    "modalities": db_dataset.modalities,
                    "languages": db_dataset.languages,
                    "variants": db_dataset.variants,
                    "num_papers": db_dataset.num_papers,
                    "warning": db_dataset.warning,
                    "pwc_url": db_dataset.pwc_url,
                    # Legacy counts
                    "paper_count": paper_count,
                    "task_count": task_count,
                }
                dataset_list.append(Dataset(**dataset_dict))

            # Calculate pagination
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Datasets(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=dataset_list,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve datasets: {str(e)}")

    def get_dataset(self, dataset_id: int) -> Optional[Dataset]:
        """
        Get a specific dataset by ID.

        Args:
            dataset_id: Dataset ID

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts
            result = (
                self.db.query(
                    DBDataset,
                    func.count(PaperDataset.paper_id).label("paper_count"),
                    func.count(TaskDataset.task_id).label("task_count"),
                )
                .outerjoin(PaperDataset, DBDataset.id == PaperDataset.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(DBDataset.id == dataset_id)
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result

            dataset_dict = {
                "id": str(db_dataset.id),
                "name": db_dataset.name,
                "slug": db_dataset.slug,
                "full_name": db_dataset.full_name,
                "description": db_dataset.description,
                "url": db_dataset.url,
                "hf_url": db_dataset.hf_url,
                # PWC enriched fields
                "short_description": db_dataset.short_description,
                "homepage": db_dataset.homepage,
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                "introduced_date": db_dataset.introduced_date,
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
            }

            return Dataset(**dataset_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset: {str(e)}")

    def get_dataset_by_slug(self, slug: str) -> Optional[Dataset]:
        """
        Get a specific dataset by slug.

        Args:
            slug: Dataset slug

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts
            result = (
                self.db.query(
                    DBDataset,
                    func.count(PaperDataset.paper_id).label("paper_count"),
                    func.count(TaskDataset.task_id).label("task_count"),
                )
                .outerjoin(PaperDataset, DBDataset.id == PaperDataset.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(DBDataset.slug == slug)
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result

            dataset_dict = {
                "id": str(db_dataset.id),
                "name": db_dataset.name,
                "slug": db_dataset.slug,
                "full_name": db_dataset.full_name,
                "description": db_dataset.description,
                "url": db_dataset.url,
                "hf_url": db_dataset.hf_url,
                # PWC enriched fields
                "short_description": db_dataset.short_description,
                "homepage": db_dataset.homepage,
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                "introduced_date": db_dataset.introduced_date,
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
            }

            return Dataset(**dataset_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset by slug: {str(e)}")

    def get_dataset_papers(
        self, dataset_id: int, page: int = 1, page_size: int = 50
    ) -> List[int]:
        """
        Get papers that use a specific dataset.

        Args:
            dataset_id: Dataset ID
            page: Page number (1-based)
            page_size: Number of papers per page

        Returns:
            List of paper IDs

        Raises:
            DatabaseError: If database query fails
        """
        try:
            offset = (page - 1) * page_size

            paper_ids = (
                self.db.query(PaperDataset.paper_id)
                .filter(PaperDataset.dataset_id == dataset_id)
                .offset(offset)
                .limit(page_size)
                .all()
            )

            return [pid[0] for pid in paper_ids]

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve papers for dataset: {str(e)}")

    def get_dataset_tasks(self, dataset_id: int) -> List[int]:
        """
        Get tasks associated with a specific dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            List of task IDs

        Raises:
            DatabaseError: If database query fails
        """
        try:
            task_ids = (
                self.db.query(TaskDataset.task_id)
                .filter(TaskDataset.dataset_id == dataset_id)
                .all()
            )

            return [tid[0] for tid in task_ids]

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks for dataset: {str(e)}")

    def get_dataset_evaluations_count(self, dataset_id: int) -> int:
        """
        Get count of evaluations for a specific dataset.

        Args:
            dataset_id: Dataset ID

        Returns:
            Number of evaluations

        Raises:
            DatabaseError: If database query fails
        """
        try:
            count = (
                self.db.query(func.count(DBEvaluation.id))
                .filter(DBEvaluation.dataset_id == dataset_id)
                .scalar()
            )

            return count or 0

        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve evaluation count for dataset: {str(e)}"
            )

    def search_datasets(
        self, query: str, page: int = 1, page_size: int = 50
    ) -> Datasets:
        """
        Search datasets by name, full_name, or description.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of datasets per page

        Returns:
            Datasets object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_datasets(
            page=page,
            page_size=page_size,
            search=query,
            order_by="name",
            order_dir="asc",
        )
