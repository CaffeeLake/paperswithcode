"""
Area service for handling area-related business logic.

This service provides methods for retrieving and managing research area data,
including pagination, filtering, and task relationships.
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import Area as DBArea, Task as DBTask
from backend.models.api import Area, Areas
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
