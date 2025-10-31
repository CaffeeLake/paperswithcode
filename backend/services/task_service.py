"""
Task service for handling task-related business logic.

This service provides methods for retrieving and managing AI/ML task data,
including pagination, filtering, hierarchical relationships, and paper associations.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import Task as DBTask, Area as DBArea, PaperTask
from backend.models.api import Task, Tasks, TaskCreateRequest
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.slug_utils import slugify


class TaskService:
    """Service class for task-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_tasks(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        area_id: Optional[int] = None,
        parent_id: Optional[int] = None,
        level: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Tasks:
        """
        Get a paginated list of AI/ML tasks with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of tasks per page
            search: Search term for task name and description (full-text search)
            name: Filter by partial task name match
            area_id: Filter by research area ID
            parent_id: Filter by parent task ID
            level: Filter by hierarchy level (0=top-level, 1=subtask, etc.)
            order_by: Field to order by (name, created_at, level, paper_count)
            order_dir: Order direction (asc, desc)

        Returns:
            Tasks object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBTask)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in name and description
                query = query.filter(
                    or_(
                        DBTask.name.ilike(f"%{search}%"),
                        DBTask.description.ilike(f"%{search}%")
                        if DBTask.description
                        else False,
                    )
                )

            if name:
                query = query.filter(DBTask.name.ilike(f"%{name}%"))

            if area_id is not None:
                query = query.filter(DBTask.area_id == area_id)

            if parent_id is not None:
                query = query.filter(DBTask.parent_id == parent_id)

            if level is not None:
                query = query.filter(DBTask.level == level)

            # Apply ordering
            if order_by == "name":
                order_field = DBTask.name
            elif order_by == "created_at":
                order_field = DBTask.created_at
            elif order_by == "level":
                order_field = DBTask.level
            else:
                order_field = DBTask.name  # Default to name

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
            tasks = []
            for db_task in results:
                # Get paper count for this task
                paper_count = (
                    self.db.query(func.count(PaperTask.paper_id))
                    .filter(PaperTask.task_id == db_task.id)
                    .scalar()
                    or 0
                )

                task_dict = {
                    "id": str(db_task.id),
                    "name": db_task.name,
                    "description": db_task.description,
                    "slug": db_task.slug,
                    "keywords": db_task.keywords,
                    "parent_id": str(db_task.parent_id) if db_task.parent_id else None,
                    "area_id": str(db_task.area_id) if db_task.area_id else None,
                    "level": db_task.level,
                    "paper_count": paper_count,
                    "image_url": db_task.image_url,
                    "image_credit": db_task.image_credit,
                    "created_at": db_task.created_at,
                    "updated_at": db_task.updated_at,
                }
                tasks.append(Task(**task_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Tasks(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=tasks,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks: {str(e)}")

    def get_task_by_id(self, task_id: str) -> Task:
        """
        Get a specific AI/ML task by ID.

        Args:
            task_id: The task ID

        Returns:
            Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            db_task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()

            if not db_task:
                raise PaperNotFoundError(f"Task with ID {task_id} not found")

            # Get paper count for this task
            paper_count = (
                self.db.query(func.count(PaperTask.paper_id))
                .filter(PaperTask.task_id == db_task.id)
                .scalar()
                or 0
            )

            task_dict = {
                "id": str(db_task.id),
                "name": db_task.name,
                "description": db_task.description,
                "slug": db_task.slug,
                "keywords": db_task.keywords,
                "parent_id": str(db_task.parent_id) if db_task.parent_id else None,
                "area_id": str(db_task.area_id) if db_task.area_id else None,
                "level": db_task.level,
                "paper_count": paper_count,
                "image_url": db_task.image_url,
                "image_credit": db_task.image_credit,
                "created_at": db_task.created_at,
                "updated_at": db_task.updated_at,
            }

            return Task(**task_dict)

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve task: {str(e)}")

    def get_task_by_slug(self, slug: str) -> Task:
        """
        Get a specific AI/ML task by slug.

        Args:
            slug: The task slug

        Returns:
            Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            db_task = self.db.query(DBTask).filter(DBTask.slug == slug).first()

            if not db_task:
                raise PaperNotFoundError(f"Task with slug '{slug}' not found")

            return self.get_task_by_id(str(db_task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve task: {str(e)}")

    def get_task_children(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """
        Get child tasks (subtasks) of a specific task.

        Args:
            task_id: The parent task ID
            page: Page number (1-based)
            page_size: Number of tasks per page

        Returns:
            Tasks object with child tasks

        Raises:
            PaperNotFoundError: If parent task not found
            DatabaseError: If database query fails
        """
        try:
            # Verify parent task exists
            parent_task = (
                self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            )
            if not parent_task:
                raise PaperNotFoundError(f"Task with ID {task_id} not found")

            # Get children
            return self.get_tasks(
                page=page,
                page_size=page_size,
                parent_id=int(task_id),
                order_by="name",
                order_dir="asc",
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve child tasks: {str(e)}")

    def get_task_parents(self, task_id: str) -> List[Task]:
        """
        Get all parent tasks of a specific task (entire hierarchy up to root).

        Args:
            task_id: The task ID

        Returns:
            List of parent tasks from immediate parent to root

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            db_task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            if not db_task:
                raise PaperNotFoundError(f"Task with ID {task_id} not found")

            parents = []
            current = db_task

            # Traverse up the hierarchy
            while current.parent_id is not None:
                parent = (
                    self.db.query(DBTask).filter(DBTask.id == current.parent_id).first()
                )
                if not parent:
                    break

                # Get paper count for parent
                paper_count = (
                    self.db.query(func.count(PaperTask.paper_id))
                    .filter(PaperTask.task_id == parent.id)
                    .scalar()
                    or 0
                )

                parent_dict = {
                    "id": str(parent.id),
                    "name": parent.name,
                    "description": parent.description,
                    "slug": parent.slug,
                    "parent_id": str(parent.parent_id) if parent.parent_id else None,
                    "area_id": str(parent.area_id) if parent.area_id else None,
                    "level": parent.level,
                    "paper_count": paper_count,
                    "created_at": parent.created_at,
                    "updated_at": parent.updated_at,
                }
                parents.append(Task(**parent_dict))
                current = parent

            return parents

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve parent tasks: {str(e)}")

    def get_tasks_by_area(
        self,
        area_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """
        Get all tasks associated with a specific research area.

        Args:
            area_id: The research area ID
            page: Page number (1-based)
            page_size: Number of tasks per page

        Returns:
            Tasks object with tasks in the area

        Raises:
            PaperNotFoundError: If area not found
            DatabaseError: If database query fails
        """
        try:
            # Verify area exists
            area = self.db.query(DBArea).filter(DBArea.id == int(area_id)).first()
            if not area:
                raise PaperNotFoundError(f"Area with ID {area_id} not found")

            # Get tasks for this area
            return self.get_tasks(
                page=page,
                page_size=page_size,
                area_id=int(area_id),
                order_by="name",
                order_dir="asc",
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve tasks for area: {str(e)}")

    def search_tasks(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Tasks:
        """
        Search tasks by name and description with full-text search.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of tasks per page

        Returns:
            Tasks object with search results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_tasks(
            page=page,
            page_size=page_size,
            search=query,
            order_by="name",
            order_dir="asc",
        )

    def get_task_paper_count(self, task_id: int) -> int:
        """
        Get the number of papers associated with a task.

        Args:
            task_id: The task ID

        Returns:
            Paper count

        Raises:
            DatabaseError: If database query fails
        """
        try:
            return (
                self.db.query(func.count(PaperTask.paper_id))
                .filter(PaperTask.task_id == task_id)
                .scalar()
                or 0
            )
        except Exception as e:
            raise DatabaseError(f"Failed to get paper count for task: {str(e)}")

    def get_task_papers(
        self,
        task_id: str,
        page: int = 1,
        page_size: int = 20,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
        include_resources: bool = False,
    ):
        """
        Get papers associated with a specific task.

        Args:
            task_id: The task ID or slug
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by (date_published, title, citation_count)
            order_dir: Order direction (asc, desc)
            include_resources: Whether to include repositories and tasks

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database query fails
        """
        try:
            from backend.models.database import Paper as DBPaper
            from backend.models.api import Papers

            # Get task to verify it exists (try by ID or slug)
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self.db.query(DBTask).filter(DBTask.slug == task_id).first()

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Base query for papers with this task
            query = (
                self.db.query(DBPaper)
                .join(PaperTask, DBPaper.id == PaperTask.paper_id)
                .filter(PaperTask.task_id == task.id)
            )

            # Apply latest version filter
            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Apply ordering
            if order_by == "date_published":
                order_field = DBPaper.date_published
            elif order_by == "title":
                order_field = DBPaper.title
            elif order_by == "citation_count":
                order_field = DBPaper.citation_count
            else:
                order_field = DBPaper.date_published

            if order_dir == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            # Convert to API models
            from backend.services.paper_service import PaperService

            paper_service = PaperService(self.db)

            papers = []
            for db_paper in db_papers:
                paper = paper_service._convert_db_paper_to_api(
                    db_paper, include_resources=include_resources
                )
                papers.append(paper)

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next=next_page,
                previous=previous_page,
                results=papers,
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to get papers for task: {str(e)}")

    def add_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Add keywords to a task (appends to existing keywords).

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to add

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self.db.query(DBTask).filter(DBTask.slug == task_id).first()

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if task.keywords:
                existing_keywords = [kw.strip() for kw in task.keywords.split(",")]

            # Add new keywords (avoid duplicates)
            for keyword in keywords:
                keyword = keyword.strip()
                if keyword and keyword not in existing_keywords:
                    existing_keywords.append(keyword)

            # Update keywords
            task.keywords = ", ".join(existing_keywords)
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to add keywords to task: {str(e)}")

    def remove_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Remove specific keywords from a task.

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to remove

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self.db.query(DBTask).filter(DBTask.slug == task_id).first()

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Parse existing keywords
            existing_keywords = []
            if task.keywords:
                existing_keywords = [kw.strip() for kw in task.keywords.split(",")]

            # Remove specified keywords
            keywords_to_remove = [kw.strip().lower() for kw in keywords]
            existing_keywords = [
                kw for kw in existing_keywords if kw.lower() not in keywords_to_remove
            ]

            # Update keywords
            task.keywords = ", ".join(existing_keywords) if existing_keywords else None
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to remove keywords from task: {str(e)}")

    def replace_keywords(self, task_id: str, keywords: List[str]) -> Task:
        """
        Replace all keywords for a task.

        Args:
            task_id: The task ID or slug
            keywords: List of keywords to set (replaces all existing keywords)

        Returns:
            Updated Task object

        Raises:
            PaperNotFoundError: If task not found
            DatabaseError: If database operation fails
        """
        try:
            # Get task - try by ID or slug
            task = None
            if task_id.isdigit():
                task = self.db.query(DBTask).filter(DBTask.id == int(task_id)).first()
            else:
                task = self.db.query(DBTask).filter(DBTask.slug == task_id).first()

            if not task:
                raise PaperNotFoundError(f"Task with ID or slug '{task_id}' not found")

            # Set new keywords
            cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
            task.keywords = ", ".join(cleaned_keywords) if cleaned_keywords else None
            self.db.commit()
            self.db.refresh(task)

            # Return updated task
            return self.get_task_by_id(str(task.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to replace keywords for task: {str(e)}")

    def create_task(self, request: TaskCreateRequest) -> Task:
        """
        Create a new task.

        Args:
            request: TaskCreateRequest with task data

        Returns:
            Created Task object

        Raises:
            DatabaseError: If database operation fails
            ValueError: If area_id or parent_id don't exist, or slug already exists
        """
        try:
            # Validate area_id exists if provided
            if request.area_id is not None:
                area = (
                    self.db.query(DBArea).filter(DBArea.id == request.area_id).first()
                )
                if not area:
                    raise ValueError(f"Area with ID {request.area_id} not found")

            # Validate parent_id exists if provided and calculate level
            level = 0
            if request.parent_id is not None:
                parent = (
                    self.db.query(DBTask).filter(DBTask.id == request.parent_id).first()
                )
                if not parent:
                    raise ValueError(
                        f"Parent task with ID {request.parent_id} not found"
                    )
                level = parent.level + 1

            # Generate slug from name
            slug = slugify(request.name)

            # Check if slug already exists
            existing_task = self.db.query(DBTask).filter(DBTask.slug == slug).first()
            if existing_task:
                raise ValueError(f"Task with slug '{slug}' already exists")

            # Create the task
            db_task = DBTask(
                name=request.name,
                slug=slug,
                description=request.description,
                keywords=request.keywords,
                area_id=request.area_id,
                parent_id=request.parent_id,
                level=level,
                image_url=request.image_url,
                image_credit=request.image_credit,
            )

            self.db.add(db_task)
            self.db.commit()
            self.db.refresh(db_task)

            # Return the created task using the existing get_task_by_id method
            return self.get_task_by_id(str(db_task.id))

        except ValueError as e:
            self.db.rollback()
            raise e
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to create task: {str(e)}")
