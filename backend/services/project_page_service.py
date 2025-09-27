"""
Project Page service for business logic and data processing with normalized structure.

This service handles all project page related operations with the new many-to-many
relationship structure, including:
- Fetching project pages with pagination and filtering
- Managing paper-project page relationships via junction table
- Converting database models to API models
- Handling relationship metadata (is_official, source)
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func

from backend.models.database import (
    ProjectPage as DBProjectPage,
    PaperProjectPage as DBPaperProjectPage,
)
from backend.models.api import (
    ProjectPage,
    ProjectPages,
    PaperProjectPage,
    ProjectPageWithPapers,
)

from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings


class ProjectPageService:
    """Service for project page operations with normalized many-to-many support."""

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db
        self.settings = get_settings()

    def get_project_pages(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        official_only: bool = False,
        source: Optional[str] = None,
        order_by: str = "created_at",
        order_dir: str = "desc",
        include_paper_count: bool = True,
    ) -> ProjectPages:
        """
        Get project pages with pagination and filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of project pages per page
            official_only: Only include project pages that are official for at least one paper
            source: Filter by data source (pwc_archive, ai_extraction, manual, etc.)
            order_by: Field to order by (supports 'paper_count' for number of associated papers)
            order_dir: Order direction (asc/desc)
            include_paper_count: Whether to include paper count in results

        Returns:
            ProjectPages object with pagination info
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query
            if include_paper_count or order_by == "paper_count":
                # Query with paper count
                query = (
                    self.db.query(
                        DBProjectPage,
                        func.count(DBPaperProjectPage.paper_id).label("paper_count"),
                    )
                    .outerjoin(
                        DBPaperProjectPage,
                        DBProjectPage.id == DBPaperProjectPage.project_page_id,
                    )
                    .group_by(DBProjectPage.id)
                )
            else:
                # Simple query without paper count
                query = self.db.query(DBProjectPage)

            # Apply filters
            if official_only:
                if include_paper_count or order_by == "paper_count":
                    # For queries with joins, filter on junction table
                    query = query.having(
                        func.sum(
                            func.cast(DBPaperProjectPage.is_official, func.INTEGER())
                        )
                        > 0
                    )
                else:
                    # For simple queries, use exists subquery
                    query = query.filter(
                        self.db.query(DBPaperProjectPage)
                        .filter(
                            DBPaperProjectPage.project_page_id == DBProjectPage.id,
                            DBPaperProjectPage.is_official,
                        )
                        .exists()
                    )

            if source:
                query = query.filter(DBProjectPage.source == source)

            # Apply ordering
            if order_by == "paper_count" and (
                include_paper_count or order_by == "paper_count"
            ):
                order_field = func.count(DBPaperProjectPage.paper_id)
            else:
                order_field = getattr(DBProjectPage, order_by, DBProjectPage.created_at)

            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            if include_paper_count or order_by == "paper_count":
                total_count = query.count()
            else:
                total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            if include_paper_count or order_by == "paper_count":
                api_project_pages = [
                    self._db_project_page_to_api(result[0]) for result in results
                ]
            else:
                api_project_pages = [
                    self._db_project_page_to_api(page) for page in results
                ]

            # Calculate pagination info
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return ProjectPages(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_project_pages,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages: {str(e)}")

    def get_project_page_by_id(self, page_id: str) -> ProjectPage:
        """
        Get a specific project page by ID.

        Args:
            page_id: Project page ID

        Returns:
            ProjectPage object

        Raises:
            PaperNotFoundError: If project page not found
        """
        try:
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            return self._db_project_page_to_api(project_page)

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page: {str(e)}")

    def get_project_pages_for_paper(self, paper_id: str) -> List[ProjectPage]:
        """
        Get all project pages associated with a paper via the junction table.

        Args:
            paper_id: Paper ID

        Returns:
            List of ProjectPage objects
        """
        try:
            # Query using the junction table
            project_pages = (
                self.db.query(DBProjectPage)
                .join(
                    DBPaperProjectPage,
                    DBProjectPage.id == DBPaperProjectPage.project_page_id,
                )
                .filter(DBPaperProjectPage.paper_id == int(paper_id))
                .order_by(
                    desc(DBPaperProjectPage.is_official), desc(DBProjectPage.created_at)
                )
                .all()
            )

            return [self._db_project_page_to_api(page) for page in project_pages]

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages for paper: {str(e)}")

    def get_project_page_with_papers(self, page_id: str) -> ProjectPageWithPapers:
        """
        Get a project page with all associated papers.

        Args:
            page_id: Project page ID

        Returns:
            ProjectPageWithPapers object with project page and associated papers
        """
        try:
            # Get the project page
            project_page = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.id == int(page_id))
                .first()
            )

            if not project_page:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            # Get associated papers
            paper_relationships = (
                self.db.query(DBPaperProjectPage)
                .filter(DBPaperProjectPage.project_page_id == int(page_id))
                .all()
            )

            paper_ids = [str(rel.paper_id) for rel in paper_relationships]
            relationships = [
                self._db_paper_project_page_to_api(rel) for rel in paper_relationships
            ]

            return ProjectPageWithPapers(
                project_page=self._db_project_page_to_api(project_page),
                papers=paper_ids,
                relationships=relationships,
            )

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page with papers: {str(e)}")

    def get_paper_project_page_relationships(
        self, paper_id: Optional[str] = None, project_page_id: Optional[str] = None
    ) -> List[PaperProjectPage]:
        """
        Get paper-project page relationships with optional filtering.

        Args:
            paper_id: Optional paper ID to filter by
            project_page_id: Optional project page ID to filter by

        Returns:
            List of PaperProjectPage relationship objects
        """
        try:
            query = self.db.query(DBPaperProjectPage)

            if paper_id:
                query = query.filter(DBPaperProjectPage.paper_id == int(paper_id))

            if project_page_id:
                query = query.filter(
                    DBPaperProjectPage.project_page_id == int(project_page_id)
                )

            relationships = query.all()
            return [self._db_paper_project_page_to_api(rel) for rel in relationships]

        except ValueError as e:
            raise PaperNotFoundError(f"Invalid ID provided: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch relationships: {str(e)}")

    def _db_project_page_to_api(self, db_project_page: DBProjectPage) -> ProjectPage:
        """
        Convert database ProjectPage model to API ProjectPage model.

        Args:
            db_project_page: Database project page object

        Returns:
            API ProjectPage object
        """
        return ProjectPage(
            id=str(db_project_page.id),
            url=db_project_page.url,
            is_official=db_project_page.is_official,
            source=db_project_page.source,
            created_at=db_project_page.created_at.date()
            if db_project_page.created_at
            else None,
            updated_at=db_project_page.updated_at.date()
            if db_project_page.updated_at
            else None,
        )

    def _db_paper_project_page_to_api(
        self, db_relationship: DBPaperProjectPage
    ) -> PaperProjectPage:
        """
        Convert database PaperProjectPage model to API PaperProjectPage model.

        Args:
            db_relationship: Database paper-project page relationship object

        Returns:
            API PaperProjectPage object
        """
        return PaperProjectPage(
            paper_id=str(db_relationship.paper_id),
            project_page_id=str(db_relationship.project_page_id),
            is_official=db_relationship.is_official,
            source=db_relationship.source,
            created_at=db_relationship.created_at.date()
            if db_relationship.created_at
            else None,
            updated_at=db_relationship.updated_at.date()
            if db_relationship.updated_at
            else None,
        )
