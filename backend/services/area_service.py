"""
Area service for handling area-related business logic.

This service provides methods for retrieving and managing research area data,
including pagination, filtering, and task relationships.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import Area as DBArea, Task as DBTask, PaperTask
from backend.models.api import (
    Area,
    Areas,
    AreaWithTasks,
    AreasWithTasks,
    Task,
)
from backend.utils.entity_images import entity_image_url
from backend.utils.exceptions import PaperNotFoundError, DatabaseError


class AreaService:
    """Service class for area-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_areas(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Areas:
        """
        Get a paginated list of research areas with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of areas per page
            search: Search term for area name (full-text search)
            name: Filter by partial area name match
            order_by: Field to order by (name, created_at, task_count)
            order_dir: Order direction (asc, desc)

        Returns:
            Areas object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBArea)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search
                query = query.filter(DBArea.name.ilike(f"%{search}%"))

            if name:
                query = query.filter(DBArea.name.ilike(f"%{name}%"))

            # Apply ordering
            if order_by == "name":
                order_field = DBArea.name
            elif order_by == "created_at":
                order_field = DBArea.created_at
            else:
                order_field = DBArea.name  # Default to name

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            areas = []
            for db_area in results:
                area_dict = {
                    "id": str(db_area.id),
                    "name": db_area.name,
                    "description": db_area.description,
                    "created_at": db_area.created_at,
                    "updated_at": db_area.updated_at,
                }
                areas.append(Area(**area_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Areas(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=areas,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve areas: {str(e)}")

    def get_area_by_id(self, area_id: str) -> Area:
        """
        Get a specific research area by ID.

        Args:
            area_id: The area ID

        Returns:
            Area object

        Raises:
            PaperNotFoundError: If area not found
            DatabaseError: If database query fails
        """
        try:
            db_area = self.db.query(DBArea).filter(DBArea.id == int(area_id)).first()

            if not db_area:
                raise PaperNotFoundError(f"Area with ID {area_id} not found")

            area_dict = {
                "id": str(db_area.id),
                "name": db_area.name,
                "description": db_area.description,
                "created_at": db_area.created_at,
                "updated_at": db_area.updated_at,
            }

            return Area(**area_dict)

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve area: {str(e)}")

    def search_areas(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Areas:
        """
        Search areas by name with full-text search.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of areas per page

        Returns:
            Areas object with search results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Use case-insensitive search
            db_query = self.db.query(DBArea).filter(
                or_(
                    DBArea.name.ilike(f"%{query}%"),
                    DBArea.description.ilike(f"%{query}%")
                    if DBArea.description
                    else False,
                )
            )

            # Order by name
            db_query = db_query.order_by(DBArea.name)

            # Get total count
            total_count = db_query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = db_query.offset(offset).limit(page_size).all()

            # Convert to API models
            areas = []
            for db_area in results:
                area_dict = {
                    "id": str(db_area.id),
                    "name": db_area.name,
                    "description": db_area.description,
                    "created_at": db_area.created_at,
                    "updated_at": db_area.updated_at,
                }
                areas.append(Area(**area_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Areas(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=areas,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to search areas: {str(e)}")

    def get_areas_with_tasks(self) -> AreasWithTasks:
        """
        Return every area together with its tasks (and per-task paper counts)
        in a single response.

        Uses two queries:
          1. All areas, ordered by name.
          2. All visible tasks LEFT JOIN paper_tasks GROUP BY task.id,
             fetching paper_count in one aggregate pass instead of one count
             per task. Tasks with `is_visible = false` are filtered out so the
             public `/tasks` taxonomy mirrors the `is_visible` denylist.

        This collapses what used to be `1 + N_areas` HTTP requests from the
        frontend (one for `/areas/`, then one `/areas/{id}/tasks` per area) into
        a single backend round-trip.
        """
        try:
            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

            paper_count_col = func.count(PaperTask.paper_id).label("paper_count")
            task_rows = (
                self.db.query(DBTask, paper_count_col)
                .outerjoin(PaperTask, DBTask.id == PaperTask.task_id)
                .filter(DBTask.is_visible)
                .group_by(DBTask.id)
                .order_by(DBTask.name)
                .all()
            )

            tasks_by_area: dict[Optional[int], list[Task]] = {}
            for db_task, paper_count in task_rows:
                api_task = Task(
                    id=str(db_task.id),
                    name=db_task.name,
                    description=db_task.description,
                    slug=db_task.slug,
                    keywords=db_task.keywords,
                    parent_id=str(db_task.parent_id) if db_task.parent_id else None,
                    area_id=str(db_task.area_id) if db_task.area_id else None,
                    level=db_task.level,
                    paper_count=paper_count or 0,
                    image_url=entity_image_url(
                        "tasks",
                        db_task.slug,
                        db_task.image_mime_type is not None,
                        db_task.image_url,
                    ),
                    image_credit=db_task.image_credit,
                    is_visible=db_task.is_visible,
                    created_at=db_task.created_at,
                    updated_at=db_task.updated_at,
                )
                tasks_by_area.setdefault(db_task.area_id, []).append(api_task)

            results = [
                AreaWithTasks(
                    id=str(area.id),
                    name=area.name,
                    description=area.description,
                    tasks=tasks_by_area.get(area.id, []),
                )
                for area in area_rows
            ]

            return AreasWithTasks(results=results)

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve areas with tasks: {str(e)}")

    def get_area_task_count(self, area_id: int) -> int:
        """
        Get the number of tasks associated with an area.

        Args:
            area_id: The area ID

        Returns:
            Task count

        Raises:
            DatabaseError: If database query fails
        """
        try:
            return (
                self.db.query(func.count(DBTask.id))
                .filter(DBTask.area_id == area_id)
                .scalar()
                or 0
            )
        except Exception as e:
            raise DatabaseError(f"Failed to get task count for area: {str(e)}")
