"""
Dataset service for handling dataset-related business logic.

This service provides methods for retrieving and managing benchmark dataset data,
including pagination, filtering, paper associations, and evaluation data.
"""

from typing import Optional, List
from sqlalchemy.orm import Session, aliased
from sqlalchemy import func, desc, asc, or_

from backend.models.database import (
    Dataset as DBDataset,
    Evaluation as DBEvaluation,
    PaperDataset,
    TaskDataset,
    Task as DBTask,
    Paper as DBPaper,
)
from backend.utils.task_hierarchy import collect_descendant_task_ids
from backend.models.api import (
    Dataset,
    Datasets,
    DatasetCreateRequest,
    DatasetUpdateRequest,
    IntroducingPaper,
)
from backend.utils.exceptions import DatabaseError
from backend.utils.slug_utils import slugify


class DatasetService:
    """Service class for dataset-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def _supports_harness(self, dataset_id: int, task_id: Optional[int] = None) -> bool:
        query = self.db.query(TaskDataset.supports_harness).filter(
            TaskDataset.dataset_id == dataset_id
        )
        if task_id is not None:
            query = query.filter(TaskDataset.task_id == task_id)
        return any(supports for (supports,) in query.all())

    def get_datasets(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        task_id: Optional[int] = None,
        include_descendants: bool = False,
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
            # Base query with paper count and task count.
            # `paper_count` here means leaderboard entry count: number of
            # evaluation rows on this dataset. This matches what the task page
            # labels as "ENTRIES" and the benchmark page renders in its
            # leaderboard table. Counting `paper_datasets` instead drifts to 0
            # for benchmarks that only exist as evaluation rows.
            task_dataset_filter = aliased(TaskDataset)
            query = (
                self.db.query(
                    DBDataset,
                    func.count(func.distinct(DBEvaluation.id)).label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
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
                # Filter datasets by task association via task_datasets so display
                # metadata stays independent from per-metric leaderboard triples.
                # When `include_descendants` is true, expand the filter to all
                # subtasks under `task_id` so a parent task page can roll up
                # benchmarks from its child tasks (subtasks).
                if include_descendants:
                    task_ids = collect_descendant_task_ids(self.db, task_id)
                else:
                    task_ids = [task_id]

                query = (
                    query.add_columns(
                        task_dataset_filter.featured_rank.label("featured_rank")
                    )
                    .join(
                        task_dataset_filter,
                        DBDataset.id == task_dataset_filter.dataset_id,
                    )
                    .filter(task_dataset_filter.task_id.in_(task_ids))
                    .group_by(task_dataset_filter.featured_rank)
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
            elif order_by == "paper_count":
                # Order by the aggregated leaderboard entry count.
                order_field = func.count(func.distinct(DBEvaluation.id))
            else:
                order_field = DBDataset.name

            order_clause = (
                desc(order_field) if order_dir == "desc" else asc(order_field)
            )
            if task_id is not None:
                query = query.order_by(
                    asc(task_dataset_filter.featured_rank).nulls_last(),
                    order_clause,
                    asc(DBDataset.name),
                )
            else:
                query = query.order_by(order_clause)

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            dataset_list = []
            for row in results:
                db_dataset, paper_count, task_count = row[:3]
                featured_rank = row[3] if task_id is not None else None
                # When rolling up descendants, harness support belongs to the
                # owning child task, not the requested parent. Drop the task
                # scoping so the dataset reflects whether *any* of its
                # leaderboards allow harness values.
                harness_task_id = None if include_descendants else task_id
                supports_harness = self._supports_harness(
                    db_dataset.id, harness_task_id
                )
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
                    # Hierarchy and variant fields
                    "parent_dataset_id": str(db_dataset.parent_dataset_id)
                    if db_dataset.parent_dataset_id
                    else None,
                    "variant_type": db_dataset.variant_type,
                    "split_name": db_dataset.split_name,
                    # Images
                    "image_url": db_dataset.image_url,
                    "thumbnail_url": db_dataset.thumbnail_url,
                    "verified_image_url": db_dataset.verified_image_url,
                    # Paper reference
                    "introducing_paper_id": str(db_dataset.introducing_paper_id)
                    if db_dataset.introducing_paper_id
                    else None,
                    "introducing_paper_title": db_dataset.introducing_paper_title,
                    "paper_url": db_dataset.paper_url,
                    # Licensing
                    "license_name": db_dataset.license_name,
                    "license_url": db_dataset.license_url,
                    # Dates
                    "introduced_year": db_dataset.introduced_year,
                    "introduced_date": db_dataset.introduced_date,
                    # Metadata
                    "modalities": db_dataset.modalities,
                    "languages": db_dataset.languages,
                    "variants": db_dataset.variants,
                    "num_papers": db_dataset.num_papers,
                    "warning": db_dataset.warning,
                    "pwc_url": db_dataset.pwc_url,
                    # Legacy counts
                    "paper_count": paper_count,
                    "task_count": task_count,
                    "featured_rank": featured_rank,
                    "supports_harness": supports_harness,
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

    def _fetch_introducing_paper(
        self, paper_id: Optional[int]
    ) -> Optional[IntroducingPaper]:
        """Fetch the minimal introducing-paper projection in one tiny query.

        Returns None when `paper_id` is missing or the row no longer exists.
        Used by `get_dataset` / `get_dataset_by_slug` when callers pass
        `include_paper=True` so the benchmark page can avoid a follow-up
        request for the introducing paper.
        """
        if paper_id is None:
            return None
        row = (
            self.db.query(
                DBPaper.id, DBPaper.arxiv_id, DBPaper.title, DBPaper.date_published
            )
            .filter(DBPaper.id == paper_id)
            .first()
        )
        if not row:
            return None
        pid, arxiv_id, title, published = row
        return IntroducingPaper(
            id=str(pid),
            arxiv_id=arxiv_id,
            title=title,
            published=published,
        )

    def get_dataset(
        self, dataset_id: int, include_paper: bool = False
    ) -> Optional[Dataset]:
        """
        Get a specific dataset by ID.

        Args:
            dataset_id: Dataset ID
            include_paper: When True, embed a lightweight `introducing_paper`
                projection (arxiv_id, title, published) in the response.

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts. `paper_count` is the number of
            # evaluation rows on the dataset (leaderboard entries) so it stays
            # in sync with the benchmark page leaderboard table.
            result = (
                self.db.query(
                    DBDataset,
                    func.count(func.distinct(DBEvaluation.id)).label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(DBDataset.id == dataset_id)
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result
            supports_harness = self._supports_harness(db_dataset.id)

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
                # Hierarchy and variant fields
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "variant_type": db_dataset.variant_type,
                "split_name": db_dataset.split_name,
                # Images
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                # Paper reference
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "paper_url": db_dataset.paper_url,
                # Licensing
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                # Dates
                "introduced_year": db_dataset.introduced_year,
                "introduced_date": db_dataset.introduced_date,
                # Metadata
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
                "featured_rank": None,
                "supports_harness": supports_harness,
            }

            if include_paper:
                dataset_dict["introducing_paper"] = self._fetch_introducing_paper(
                    db_dataset.introducing_paper_id
                )

            return Dataset(**dataset_dict)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve dataset: {str(e)}")

    def get_dataset_by_slug(
        self, slug: str, include_paper: bool = False
    ) -> Optional[Dataset]:
        """
        Get a specific dataset by slug.

        Args:
            slug: Dataset slug
            include_paper: When True, embed a lightweight `introducing_paper`
                projection (arxiv_id, title, published) in the response.

        Returns:
            Dataset object or None if not found

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query dataset with counts. `paper_count` mirrors the benchmark
            # leaderboard size (evaluation rows) instead of `paper_datasets`.
            result = (
                self.db.query(
                    DBDataset,
                    func.count(func.distinct(DBEvaluation.id)).label("paper_count"),
                    func.count(func.distinct(TaskDataset.task_id)).label("task_count"),
                )
                .outerjoin(DBEvaluation, DBDataset.id == DBEvaluation.dataset_id)
                .outerjoin(TaskDataset, DBDataset.id == TaskDataset.dataset_id)
                .filter(DBDataset.slug == slug)
                .group_by(DBDataset.id)
                .first()
            )

            if not result:
                return None

            db_dataset, paper_count, task_count = result
            supports_harness = self._supports_harness(db_dataset.id)

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
                # Hierarchy and variant fields
                "parent_dataset_id": str(db_dataset.parent_dataset_id)
                if db_dataset.parent_dataset_id
                else None,
                "variant_type": db_dataset.variant_type,
                "split_name": db_dataset.split_name,
                # Images
                "image_url": db_dataset.image_url,
                "thumbnail_url": db_dataset.thumbnail_url,
                "verified_image_url": db_dataset.verified_image_url,
                # Paper reference
                "introducing_paper_id": str(db_dataset.introducing_paper_id)
                if db_dataset.introducing_paper_id
                else None,
                "introducing_paper_title": db_dataset.introducing_paper_title,
                "paper_url": db_dataset.paper_url,
                # Licensing
                "license_name": db_dataset.license_name,
                "license_url": db_dataset.license_url,
                # Dates
                "introduced_year": db_dataset.introduced_year,
                "introduced_date": db_dataset.introduced_date,
                # Metadata
                "modalities": db_dataset.modalities,
                "languages": db_dataset.languages,
                "variants": db_dataset.variants,
                "num_papers": db_dataset.num_papers,
                "warning": db_dataset.warning,
                "pwc_url": db_dataset.pwc_url,
                # Legacy counts
                "paper_count": paper_count,
                "task_count": task_count,
                "featured_rank": None,
                "supports_harness": supports_harness,
            }

            if include_paper:
                dataset_dict["introducing_paper"] = self._fetch_introducing_paper(
                    db_dataset.introducing_paper_id
                )

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
        Get tasks associated with a specific dataset via task_dataset_metrics.

        Args:
            dataset_id: Dataset ID

        Returns:
            List of unique task IDs

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Get distinct task IDs from task_datasets
            task_ids = (
                self.db.query(TaskDataset.task_id)
                .filter(TaskDataset.dataset_id == dataset_id)
                .distinct()
                .all()
            )

            return [tid[0] for tid in task_ids]

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks for dataset: {str(e)}")

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

    def create_dataset(self, request: DatasetCreateRequest) -> Dataset:
        """
        Create a new dataset and link it to specified tasks.

        Args:
            request: DatasetCreateRequest with dataset data and task IDs

        Returns:
            Created Dataset object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If task IDs don't exist or slug already exists
        """
        try:
            # Generate slug from name
            slug = slugify(request.name)

            # Check if slug already exists
            existing_dataset = (
                self.db.query(DBDataset).filter(DBDataset.slug == slug).first()
            )
            if existing_dataset:
                raise ValueError(f"Dataset with slug '{slug}' already exists")

            # Validate that all task IDs exist
            existing_task_ids = set(
                self.db.query(DBTask.id).filter(DBTask.id.in_(request.task_ids)).all()
            )
            existing_task_ids = {task_id[0] for task_id in existing_task_ids}

            missing_task_ids = set(request.task_ids) - existing_task_ids
            if missing_task_ids:
                raise ValueError(f"Task IDs not found: {sorted(missing_task_ids)}")

            # Create the dataset
            db_dataset = DBDataset(
                name=request.name,
                slug=slug,
                full_name=request.full_name,
                description=request.description,
                url=request.url,
                hf_url=request.hf_url,
                paper_url=request.paper_url,
                # Additional PWC fields
                short_description=request.short_description,
                homepage=request.homepage,
                image_url=request.image_url,
                thumbnail_url=request.thumbnail_url,
                verified_image_url=request.verified_image_url,
                license_name=request.license_name,
                license_url=request.license_url,
                introduced_date=request.introduced_date,
                modalities=request.modalities,
                languages=request.languages,
                variants=request.variants,
                num_papers=request.num_papers,
                warning=request.warning,
                pwc_url=request.pwc_url,
            )

            self.db.add(db_dataset)
            self.db.commit()

            # Note: Task-dataset relationships are now defined via TASK_DATASET_METRICS.
            # If task_ids were provided in the request, use the leaderboard metrics API
            # (/api/v1/datasets/{dataset_id}/tasks/{task_id}/metrics) to define metrics
            # for each task-dataset pair.

            # Return the created dataset using the existing get_dataset method
            return self.get_dataset(db_dataset.id)

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create dataset: {str(e)}")

    def update_dataset(self, dataset_id: int, request: DatasetUpdateRequest) -> Dataset:
        """
        Update an existing dataset.

        Args:
            dataset_id: Dataset ID to update
            request: DatasetUpdateRequest with fields to update

        Returns:
            Updated Dataset object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If dataset not found
        """
        try:
            # Get the existing dataset
            db_dataset = (
                self.db.query(DBDataset).filter(DBDataset.id == dataset_id).first()
            )
            if not db_dataset:
                raise ValueError(f"Dataset with ID {dataset_id} not found")

            # Update only provided fields
            if request.name is not None:
                db_dataset.name = request.name
                # Regenerate slug if name changes
                db_dataset.slug = slugify(request.name)

            if request.full_name is not None:
                db_dataset.full_name = request.full_name

            if request.description is not None:
                db_dataset.description = request.description

            if request.url is not None:
                db_dataset.url = request.url

            if request.hf_url is not None:
                db_dataset.hf_url = request.hf_url

            if request.paper_url is not None:
                db_dataset.paper_url = request.paper_url

            # Additional PWC fields
            if request.short_description is not None:
                db_dataset.short_description = request.short_description

            if request.homepage is not None:
                db_dataset.homepage = request.homepage

            if request.image_url is not None:
                db_dataset.image_url = request.image_url

            if request.thumbnail_url is not None:
                db_dataset.thumbnail_url = request.thumbnail_url

            if request.verified_image_url is not None:
                db_dataset.verified_image_url = request.verified_image_url

            if request.license_name is not None:
                db_dataset.license_name = request.license_name

            if request.license_url is not None:
                db_dataset.license_url = request.license_url

            if request.introduced_date is not None:
                db_dataset.introduced_date = request.introduced_date

            if request.modalities is not None:
                db_dataset.modalities = request.modalities

            if request.languages is not None:
                db_dataset.languages = request.languages

            if request.variants is not None:
                db_dataset.variants = request.variants

            if request.num_papers is not None:
                db_dataset.num_papers = request.num_papers

            if request.warning is not None:
                db_dataset.warning = request.warning

            if request.pwc_url is not None:
                db_dataset.pwc_url = request.pwc_url

            self.db.commit()

            # Return the updated dataset using the existing get_dataset method
            return self.get_dataset(db_dataset.id)

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to update dataset: {str(e)}")
