"""
Author service for handling author-related business logic.

This service provides methods for retrieving and managing author data,
including pagination, filtering, and paper relationships.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import Author as DBAuthor, Paper as DBPaper, PaperAuthor
from backend.models.api import Author, Authors, Papers
from backend.utils.exceptions import PaperNotFoundError, DatabaseError


class AuthorService:
    """Service class for author-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_authors(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        hf_users_only: bool = False,
        order_by: str = "paper_count",
        order_dir: str = "desc",
    ) -> Authors:
        """
        Get a paginated list of authors with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of authors per page
            search: Search term for author name
            hf_users_only: Filter to only Hugging Face users
            order_by: Field to order by (name, paper_count, created_at)
            order_dir: Order direction (asc, desc)

        Returns:
            Authors object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with paper count
            query = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .group_by(DBAuthor.id)
            )

            # Apply filters
            if search:
                query = query.filter(DBAuthor.name.ilike(f"%{search}%"))

            if hf_users_only:
                query = query.filter(DBAuthor.hf_username.isnot(None))

            # Apply ordering
            if order_by == "paper_count":
                order_field = func.count(PaperAuthor.paper_id)
            elif order_by == "name":
                order_field = DBAuthor.name
            elif order_by == "created_at":
                order_field = DBAuthor.created_at
            else:
                order_field = func.count(PaperAuthor.paper_id)  # Default to paper_count

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
            authors = []
            for db_author, paper_count in results:
                author_dict = {
                    "id": str(db_author.id),
                    "full_name": db_author.name,  # API model uses 'full_name', DB uses 'name'
                    "hf_username": db_author.hf_username,
                    "hf_id": db_author.hf_id,
                    "hf_avatar_url": db_author.hf_avatar_url,
                    "hf_status": db_author.hf_status,
                    "hf_is_pro": db_author.hf_is_pro or False,
                    "paper_count": paper_count or 0,
                }
                authors.append(Author(**author_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Authors(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=authors,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve authors: {str(e)}")

    def get_author_by_id(self, author_id: str) -> Author:
        """
        Get a specific author by ID.

        Args:
            author_id: The author ID

        Returns:
            Author object

        Raises:
            PaperNotFoundError: If author not found
            DatabaseError: If database query fails
        """
        try:
            # Query with paper count
            result = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .filter(DBAuthor.id == int(author_id))
                .group_by(DBAuthor.id)
                .first()
            )

            if not result:
                raise PaperNotFoundError(f"Author with ID {author_id} not found")

            db_author, paper_count = result

            author_dict = {
                "id": str(db_author.id),
                "full_name": db_author.name,
                "hf_username": db_author.hf_username,
                "hf_id": db_author.hf_id,
                "hf_avatar_url": db_author.hf_avatar_url,
                "hf_status": db_author.hf_status,
                "hf_is_pro": db_author.hf_is_pro or False,
                "paper_count": paper_count or 0,
            }

            return Author(**author_dict)

        except ValueError:
            raise PaperNotFoundError(f"Invalid author ID: {author_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve author: {str(e)}")

    def get_author_papers(
        self,
        author_id: str,
        page: int = 1,
        page_size: int = 50,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
    ) -> Papers:
        """
        Get papers by a specific author.

        Args:
            author_id: The author ID
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by
            order_dir: Order direction (asc, desc)

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If author not found
            DatabaseError: If database query fails
        """
        try:
            # Verify author exists
            author_exists = (
                self.db.query(DBAuthor).filter(DBAuthor.id == int(author_id)).first()
            )

            if not author_exists:
                raise PaperNotFoundError(f"Author with ID {author_id} not found")

            # Base query for papers by author
            query = (
                self.db.query(DBPaper)
                .join(PaperAuthor, DBPaper.id == PaperAuthor.paper_id)
                .filter(PaperAuthor.author_id == int(author_id))
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
                paper = paper_service._convert_db_paper_to_api(db_paper)
                papers.append(paper)

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=papers,
            )

        except ValueError:
            raise PaperNotFoundError(f"Invalid author ID: {author_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve author papers: {str(e)}")

    def search_authors(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        hf_users_only: bool = False,
    ) -> Authors:
        """
        Search authors by name with full-text search capabilities.

        Args:
            query: Search query
            page: Page number (1-based)
            page_size: Number of authors per page
            hf_users_only: Filter to only Hugging Face users

        Returns:
            Authors object with search results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Use ILIKE for case-insensitive search
            search_query = (
                self.db.query(
                    DBAuthor, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .outerjoin(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .filter(
                    or_(
                        DBAuthor.name.ilike(f"%{query}%"),
                        DBAuthor.hf_username.ilike(f"%{query}%"),
                    )
                )
                .group_by(DBAuthor.id)
            )

            if hf_users_only:
                search_query = search_query.filter(DBAuthor.hf_username.isnot(None))

            # Order by relevance (exact matches first, then by paper count)
            search_query = search_query.order_by(desc(func.count(PaperAuthor.paper_id)))

            # Get total count
            total_count = search_query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = search_query.offset(offset).limit(page_size).all()

            # Convert to API models
            authors = []
            for db_author, paper_count in results:
                author_dict = {
                    "id": str(db_author.id),
                    "full_name": db_author.name,  # API model uses 'full_name', DB uses 'name'
                    "hf_username": db_author.hf_username,
                    "hf_id": db_author.hf_id,
                    "hf_avatar_url": db_author.hf_avatar_url,
                    "hf_status": db_author.hf_status,
                    "hf_is_pro": db_author.hf_is_pro or False,
                    "paper_count": paper_count or 0,
                }
                authors.append(Author(**author_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Authors(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=authors,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to search authors: {str(e)}")

    def get_authors_for_paper(self, paper_id: int) -> List[dict]:
        """
        Get authors for a specific paper with their ordering.

        Args:
            paper_id: The paper ID

        Returns:
            List of author dictionaries with ordering information

        Raises:
            DatabaseError: If database query fails
        """
        try:
            results = (
                self.db.query(DBAuthor, PaperAuthor.author_order)
                .join(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .filter(PaperAuthor.paper_id == paper_id)
                .order_by(PaperAuthor.author_order)
                .all()
            )

            authors = []
            for db_author, author_order in results:
                author_dict = {
                    "id": str(db_author.id),
                    "full_name": db_author.name,
                    "hf_username": db_author.hf_username,
                    "hf_id": db_author.hf_id,
                    "hf_avatar_url": db_author.hf_avatar_url,
                    "hf_status": db_author.hf_status,
                    "hf_is_pro": db_author.hf_is_pro or False,
                    "author_order": author_order,
                }
                authors.append(author_dict)

            return authors

        except Exception as e:
            raise DatabaseError(f"Failed to get authors for paper: {str(e)}")

    def add_author(self, author_data: dict) -> Optional[int]:
        """
        Add a new author to the database.

        Args:
            author_data: Dictionary containing author information with keys:
                - name: Author full name (required)
                - hf_username: Hugging Face username (optional)
                - hf_id: Hugging Face ID (optional)
                - hf_avatar_url: Hugging Face avatar URL (optional)
                - hf_status: Hugging Face status (optional)
                - hf_is_pro: Whether user has HF Pro (optional)

        Returns:
            Author ID if successful, None if author already exists or on error
        """
        try:
            # Check if author already exists by name
            existing = (
                self.db.query(DBAuthor)
                .filter(DBAuthor.name == author_data["name"])
                .first()
            )

            if existing:
                return None  # Author already exists

            # Create new author
            db_author = DBAuthor(
                name=author_data["name"],
                hf_username=author_data.get("hf_username"),
                hf_id=author_data.get("hf_id"),
                hf_avatar_url=author_data.get("hf_avatar_url"),
                hf_status=author_data.get("hf_status"),
                hf_is_pro=author_data.get("hf_is_pro", False),
            )

            self.db.add(db_author)
            self.db.commit()
            self.db.refresh(db_author)

            return db_author.id

        except Exception as e:
            self.db.rollback()
            print(f"Error adding author {author_data.get('name', 'unknown')}: {e}")
            return None

    def update_author_hf_data(self, author_id: int, hf_data: dict) -> bool:
        """
        Update author's Hugging Face integration data.

        Args:
            author_id: Database author ID
            hf_data: Dictionary of HF fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            db_author = self.db.query(DBAuthor).filter(DBAuthor.id == author_id).first()
            if not db_author:
                return False

            # Update allowed HF fields
            allowed_fields = {
                "hf_username",
                "hf_id",
                "hf_avatar_url",
                "hf_status",
                "hf_is_pro",
            }

            for field, value in hf_data.items():
                if field in allowed_fields and hasattr(db_author, field):
                    setattr(db_author, field, value)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            print(f"Error updating author HF data {author_id}: {e}")
            return False

    def get_author_stats(self) -> dict:
        """
        Get statistics about authors in the database.

        Returns:
            Dictionary with author statistics
        """
        try:
            total_authors = self.db.query(DBAuthor).count()
            hf_authors = (
                self.db.query(DBAuthor).filter(DBAuthor.hf_username.isnot(None)).count()
            )
            hf_pro_authors = self.db.query(DBAuthor).filter(DBAuthor.hf_is_pro).count()

            # Get top authors by paper count
            top_authors = (
                self.db.query(
                    DBAuthor.name, func.count(PaperAuthor.paper_id).label("paper_count")
                )
                .join(PaperAuthor, DBAuthor.id == PaperAuthor.author_id)
                .group_by(DBAuthor.id, DBAuthor.name)
                .order_by(desc(func.count(PaperAuthor.paper_id)))
                .limit(10)
                .all()
            )

            return {
                "total_authors": total_authors,
                "hf_integrated_authors": hf_authors,
                "hf_pro_authors": hf_pro_authors,
                "hf_integration_rate": round((hf_authors / total_authors) * 100, 2)
                if total_authors > 0
                else 0,
                "top_authors": [
                    {"name": name, "paper_count": count} for name, count in top_authors
                ],
            }

        except Exception as e:
            raise DatabaseError(f"Error fetching author statistics: {str(e)}")
