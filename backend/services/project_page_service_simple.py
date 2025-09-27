"""
Simple Project Page service that works with the normalized structure without complex relationships.

This service handles all project page related operations with direct SQL queries
to avoid SQLAlchemy relationship configuration issues.
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.models.api import (
    ProjectPage,
    ProjectPages,
    PaperProjectPage,
    ProjectPageWithPapers,
)

from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings


class ProjectPageServiceSimple:
    """Simple service for project page operations using direct queries."""

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
    ) -> ProjectPages:
        """
        Get project pages with pagination and filtering using direct SQL.
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query
            base_query = "SELECT * FROM project_pages"
            count_query = "SELECT COUNT(*) FROM project_pages"
            where_conditions = []
            params = {}

            # Apply filters
            if official_only:
                # For official_only, we need to check if there's at least one official relationship
                where_conditions.append("""
                    id IN (
                        SELECT project_page_id
                        FROM paper_project_pages
                        WHERE is_official = true
                    )
                """)

            if source:
                where_conditions.append("source = :source")
                params["source"] = source

            # Add WHERE clause if needed
            if where_conditions:
                where_clause = " WHERE " + " AND ".join(where_conditions)
                base_query += where_clause
                count_query += where_clause

            # Add ordering
            if order_by in ["created_at", "updated_at", "url", "source"]:
                order_clause = f" ORDER BY {order_by} {order_dir.upper()}"
                base_query += order_clause

            # Get total count
            count_result = self.db.execute(text(count_query), params).scalar()
            total_count = count_result or 0

            # Add pagination
            offset = (page - 1) * page_size
            base_query += " LIMIT :limit OFFSET :offset"
            params.update({"limit": page_size, "offset": offset})

            # Execute query
            results = self.db.execute(text(base_query), params).fetchall()

            # Convert to API models
            api_project_pages = []
            for row in results:
                api_project_pages.append(
                    ProjectPage(
                        id=str(row.id),
                        url=row.url,
                        is_official=row.is_official,
                        source=row.source,
                        created_at=row.created_at.date() if row.created_at else None,
                        updated_at=row.updated_at.date() if row.updated_at else None,
                    )
                )

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
        Get a specific project page by ID using direct SQL.
        """
        try:
            query = "SELECT * FROM project_pages WHERE id = :page_id"
            result = self.db.execute(text(query), {"page_id": int(page_id)}).fetchone()

            if not result:
                raise PaperNotFoundError(f"Project page with ID {page_id} not found")

            return ProjectPage(
                id=str(result.id),
                url=result.url,
                is_official=result.is_official,
                source=result.source,
                created_at=result.created_at.date() if result.created_at else None,
                updated_at=result.updated_at.date() if result.updated_at else None,
            )

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page: {str(e)}")

    def get_project_pages_for_paper(self, paper_id: str) -> List[ProjectPage]:
        """
        Get all project pages associated with a paper using direct SQL.
        """
        try:
            query = """
                SELECT pp.*
                FROM project_pages pp
                JOIN paper_project_pages ppp ON pp.id = ppp.project_page_id
                WHERE ppp.paper_id = :paper_id
                ORDER BY pp.is_official DESC, pp.created_at DESC
            """

            results = self.db.execute(
                text(query), {"paper_id": int(paper_id)}
            ).fetchall()

            api_project_pages = []
            for row in results:
                api_project_pages.append(
                    ProjectPage(
                        id=str(row.id),
                        url=row.url,
                        is_official=row.is_official,
                        source=row.source,
                        created_at=row.created_at.date() if row.created_at else None,
                        updated_at=row.updated_at.date() if row.updated_at else None,
                    )
                )

            return api_project_pages

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages for paper: {str(e)}")

    def get_project_page_with_papers(self, page_id: str) -> ProjectPageWithPapers:
        """
        Get a project page with all associated papers using direct SQL.
        """
        try:
            # Get the project page
            project_page = self.get_project_page_by_id(page_id)

            # Get associated papers and relationships
            query = """
                SELECT ppp.*, p.title
                FROM paper_project_pages ppp
                JOIN papers p ON ppp.paper_id = p.id
                WHERE ppp.project_page_id = :page_id
            """

            relationships_data = self.db.execute(
                text(query), {"page_id": int(page_id)}
            ).fetchall()

            paper_ids = [str(row.paper_id) for row in relationships_data]
            relationships = []

            for row in relationships_data:
                relationships.append(
                    PaperProjectPage(
                        paper_id=str(row.paper_id),
                        project_page_id=str(row.project_page_id),
                        is_official=row.is_official,
                        source=row.source,
                        created_at=row.created_at.date() if row.created_at else None,
                        updated_at=row.updated_at.date() if row.updated_at else None,
                    )
                )

            return ProjectPageWithPapers(
                project_page=project_page, papers=paper_ids, relationships=relationships
            )

        except ValueError:
            raise PaperNotFoundError(f"Invalid project page ID: {page_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project page with papers: {str(e)}")

    def get_paper_project_page_relationships(
        self, paper_id: Optional[str] = None, project_page_id: Optional[str] = None
    ) -> List[PaperProjectPage]:
        """
        Get paper-project page relationships using direct SQL.
        """
        try:
            query = "SELECT * FROM paper_project_pages"
            where_conditions = []
            params = {}

            if paper_id:
                where_conditions.append("paper_id = :paper_id")
                params["paper_id"] = int(paper_id)

            if project_page_id:
                where_conditions.append("project_page_id = :project_page_id")
                params["project_page_id"] = int(project_page_id)

            if where_conditions:
                query += " WHERE " + " AND ".join(where_conditions)

            results = self.db.execute(text(query), params).fetchall()

            relationships = []
            for row in results:
                relationships.append(
                    PaperProjectPage(
                        paper_id=str(row.paper_id),
                        project_page_id=str(row.project_page_id),
                    )
                )

            return relationships

        except ValueError as e:
            raise PaperNotFoundError(f"Invalid ID provided: {str(e)}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch relationships: {str(e)}")
