"""
Repository and Project Page service for business logic and data processing.

This service handles all repository and project page related operations, including:
- Fetching repositories with pagination and filtering
- Fetching project pages with pagination and filtering
- Converting database models to API models
- Managing repository metadata (stars, owner, etc.)
"""

from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc

from backend.models.database import (
    Repository as DBRepository,
    ProjectPage as DBProjectPage,
)
from backend.models.api import (
    Repository,
    Repositories,
    ProjectPage,
    ProjectPages,
)

from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings


class RepositoryService:
    """Service for repository and project page operations."""

    def __init__(self, db: Session):
        """Initialize the service with a database session."""
        self.db = db
        self.settings = get_settings()

    def get_repositories(
        self,
        page: int = 1,
        page_size: Optional[int] = None,
        owner: Optional[str] = None,
        official_only: bool = False,
        min_stars: Optional[int] = None,
        source: Optional[str] = None,
        order_by: str = "num_stars",
        order_dir: str = "desc",
    ) -> Repositories:
        """
        Get repositories with pagination and filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of repositories per page
            owner: Filter by repository owner
            official_only: Only include official repositories
            min_stars: Minimum number of stars
            source: Filter by data source (pwc_archive, ai_extraction, manual, etc.)
            order_by: Field to order by
            order_dir: Order direction (asc/desc)

        Returns:
            Repositories object with pagination info
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query
            query = self.db.query(DBRepository)

            # Apply filters
            if owner:
                query = query.filter(DBRepository.owner.ilike(f"%{owner}%"))

            if official_only:
                # Filter repositories that are official for at least one paper
                from backend.models.database import PaperRepository

                subquery = (
                    self.db.query(PaperRepository.repository_id)
                    .filter(PaperRepository.is_official)
                    .distinct()
                )
                query = query.filter(DBRepository.id.in_(subquery))

            if min_stars is not None:
                query = query.filter(DBRepository.num_stars >= min_stars)

            if source:
                query = query.filter(DBRepository.source == source)

            # Apply ordering
            order_field = getattr(DBRepository, order_by, DBRepository.num_stars)
            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            repositories = query.offset(offset).limit(page_size).all()

            # Convert to API models
            api_repositories = [
                self._db_repository_to_api(repo) for repo in repositories
            ]

            # Calculate pagination info
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Repositories(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_repositories,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to fetch repositories: {str(e)}")

    def get_repository_by_id(self, repository_id: str) -> Repository:
        """
        Get a specific repository by ID.

        Args:
            repository_id: Repository ID

        Returns:
            Repository object

        Raises:
            PaperNotFoundError: If repository not found
        """
        try:
            repository = (
                self.db.query(DBRepository)
                .filter(DBRepository.id == int(repository_id))
                .first()
            )

            if not repository:
                raise PaperNotFoundError(
                    f"Repository with ID {repository_id} not found"
                )

            return self._db_repository_to_api(repository)

        except ValueError:
            raise PaperNotFoundError(f"Invalid repository ID: {repository_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch repository: {str(e)}")

    def get_repositories_by_owner_and_name(
        self, owner: str, name: str
    ) -> List[Repository]:
        """
        Get repositories by owner and name.

        Args:
            owner: Repository owner
            name: Repository name

        Returns:
            List of Repository objects
        """
        try:
            repositories = (
                self.db.query(DBRepository)
                .filter(DBRepository.owner == owner)
                .filter(DBRepository.name == name)
                .all()
            )

            return [self._db_repository_to_api(repo) for repo in repositories]

        except Exception as e:
            raise DatabaseError(f"Failed to fetch repositories: {str(e)}")

    def get_repositories_for_paper(self, paper_id: str) -> List[Repository]:
        """
        Get all repositories associated with a paper.

        Args:
            paper_id: Paper ID

        Returns:
            List of Repository objects
        """
        try:
            from backend.models.database import PaperRepository

            # Query repositories with junction table data
            results = (
                self.db.query(DBRepository, PaperRepository.is_official)
                .join(PaperRepository, DBRepository.id == PaperRepository.repository_id)
                .filter(PaperRepository.paper_id == int(paper_id))
                .order_by(
                    desc(PaperRepository.is_official), desc(DBRepository.num_stars)
                )
                .all()
            )

            return [
                self._db_repository_to_api_with_junction(
                    repo, junction_is_official, paper_id
                )
                for repo, junction_is_official in results
            ]

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch repositories for paper: {str(e)}")

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
        Get project pages with pagination and filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of project pages per page
            official_only: Only include official project pages
            source: Filter by data source (pwc_archive, ai_extraction, manual, etc.)
            order_by: Field to order by
            order_dir: Order direction (asc/desc)

        Returns:
            ProjectPages object with pagination info
        """
        if page_size is None:
            page_size = self.settings.default_page_size

        # Ensure page_size doesn't exceed maximum
        page_size = min(page_size, self.settings.max_page_size)

        try:
            # Build base query
            query = self.db.query(DBProjectPage)

            # Apply filters
            if official_only:
                query = query.filter(DBProjectPage.is_official)

            if source:
                query = query.filter(DBProjectPage.source == source)

            # Apply ordering
            order_field = getattr(DBProjectPage, order_by, DBProjectPage.created_at)
            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_field))
            else:
                query = query.order_by(asc(order_field))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            project_pages = query.offset(offset).limit(page_size).all()

            # Convert to API models
            api_project_pages = [
                self._db_project_page_to_api(page) for page in project_pages
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
        Get all project pages associated with a paper.

        Args:
            paper_id: Paper ID

        Returns:
            List of ProjectPage objects
        """
        try:
            project_pages = (
                self.db.query(DBProjectPage)
                .filter(DBProjectPage.paper_id == int(paper_id))
                .order_by(
                    desc(DBProjectPage.is_official), desc(DBProjectPage.created_at)
                )
                .all()
            )

            return [self._db_project_page_to_api(page) for page in project_pages]

        except ValueError:
            raise PaperNotFoundError(f"Invalid paper ID: {paper_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to fetch project pages for paper: {str(e)}")

    def _db_repository_to_api(
        self, db_repository: DBRepository, paper_id: str = None
    ) -> Repository:
        """
        Convert database Repository model to API Repository model.

        Note: Since is_official is now in the junction table, this method
        defaults is_official to False. For paper-specific queries with correct
        is_official values, use _db_repository_to_api_with_junction instead.

        Args:
            db_repository: Database repository object
            paper_id: Paper ID (for backward compatibility with API)

        Returns:
            API Repository object
        """
        return Repository(
            id=str(db_repository.id),
            paper_id=paper_id or "",  # Use provided paper_id or empty string
            url=db_repository.url,
            owner=db_repository.owner,
            name=db_repository.name,
            num_stars=db_repository.num_stars,
            is_official=False,  # Default to False since is_official is now in junction table
            source=db_repository.source,
            created_at=db_repository.created_at.date()
            if db_repository.created_at
            else None,
            updated_at=db_repository.updated_at.date()
            if db_repository.updated_at
            else None,
        )

    def _db_repository_to_api_with_junction(
        self,
        db_repository: DBRepository,
        junction_is_official: bool,
        paper_id: str = None,
    ) -> Repository:
        """
        Convert database Repository model to API Repository model using junction table data.

        Args:
            db_repository: Database repository object
            junction_is_official: is_official value from paper_repositories junction table
            paper_id: Paper ID

        Returns:
            API Repository object with correct is_official value
        """
        return Repository(
            id=str(db_repository.id),
            paper_id=paper_id or "",
            url=db_repository.url,
            owner=db_repository.owner,
            name=db_repository.name,
            num_stars=db_repository.num_stars,
            is_official=junction_is_official,  # Use the correct value from junction table
            source=db_repository.source,
            created_at=db_repository.created_at.date()
            if db_repository.created_at
            else None,
            updated_at=db_repository.updated_at.date()
            if db_repository.updated_at
            else None,
        )

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
            paper_id=str(db_project_page.paper_id),
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
