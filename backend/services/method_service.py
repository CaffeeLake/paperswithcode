"""
Method service for handling method-related business logic.

This service provides methods for retrieving and managing AI/ML method data,
including pagination, filtering, and paper associations.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, asc, or_

from backend.models.database import Method as DBMethod, PaperMethod
from backend.models.api import Method, Methods
from backend.utils.exceptions import PaperNotFoundError, DatabaseError


class MethodService:
    """Service class for method-related operations."""

    def __init__(self, db: Session):
        self.db = db

    def get_methods(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        introduced_year: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
    ) -> Methods:
        """
        Get a paginated list of AI/ML methods with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of methods per page
            search: Search term for method name and description (full-text search)
            name: Filter by partial method name match
            full_name: Filter by partial full name match
            introduced_year: Filter by year introduced
            order_by: Field to order by (name, full_name, introduced_year, paper_count)
            order_dir: Order direction (asc, desc)

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBMethod)

            # Apply filters
            if search:
                # Use ilike for case-insensitive search in name, full_name, and description
                query = query.filter(
                    or_(
                        DBMethod.name.ilike(f"%{search}%"),
                        DBMethod.full_name.ilike(f"%{search}%")
                        if DBMethod.full_name
                        else False,
                        DBMethod.description.ilike(f"%{search}%")
                        if DBMethod.description
                        else False,
                    )
                )

            if name:
                query = query.filter(DBMethod.name.ilike(f"%{name}%"))

            if full_name:
                query = query.filter(DBMethod.full_name.ilike(f"%{full_name}%"))

            if introduced_year is not None:
                query = query.filter(DBMethod.introduced_year == introduced_year)

            # Apply ordering
            if order_by == "name":
                order_field = DBMethod.name
            elif order_by == "full_name":
                order_field = DBMethod.full_name
            elif order_by == "introduced_year":
                order_field = DBMethod.introduced_year
            elif order_by == "created_at":
                order_field = DBMethod.created_at
            else:
                order_field = DBMethod.name  # Default to name

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
            methods = []
            for db_method in results:
                # Get paper count for this method
                paper_count = (
                    self.db.query(func.count(PaperMethod.paper_id))
                    .filter(PaperMethod.method_id == db_method.id)
                    .scalar()
                    or 0
                )

                method_dict = {
                    "id": str(db_method.id),
                    "name": db_method.name,
                    "slug": db_method.slug,
                    "full_name": db_method.full_name,
                    "description": db_method.description,
                    "area_id": str(db_method.area_id) if db_method.area_id else None,
                    "introduced_year": db_method.introduced_year,
                    "source_url": db_method.source_url,
                    "source_title": db_method.source_title,
                    "code_snippet_url": db_method.code_snippet_url,
                    "image_url": db_method.image_url,
                    "image_credit": db_method.image_credit,
                    "collection_name": db_method.collection_name,
                    "collection_description": db_method.collection_description,
                    "collection_parent": db_method.collection_parent,
                    "collection_area": db_method.collection_area,
                    "paper_count": paper_count,
                    "created_at": db_method.created_at,
                    "updated_at": db_method.updated_at,
                }
                methods.append(Method(**method_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Methods(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=methods,
            )

        except Exception as e:
            raise DatabaseError(f"Failed to retrieve methods: {str(e)}")

    def get_method_by_id(self, method_id: str) -> Method:
        """
        Get a specific AI/ML method by ID.

        Args:
            method_id: The method ID

        Returns:
            Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            # Convert string ID to integer
            method_id_int = int(method_id)

            # Query the database
            db_method = (
                self.db.query(DBMethod).filter(DBMethod.id == method_id_int).first()
            )

            if not db_method:
                raise PaperNotFoundError(f"Method with ID {method_id} not found")

            # Get paper count for this method
            paper_count = (
                self.db.query(func.count(PaperMethod.paper_id))
                .filter(PaperMethod.method_id == db_method.id)
                .scalar()
                or 0
            )

            # Convert to API model
            method_dict = {
                "id": str(db_method.id),
                "name": db_method.name,
                "slug": db_method.slug,
                "full_name": db_method.full_name,
                "description": db_method.description,
                "area_id": str(db_method.area_id) if db_method.area_id else None,
                "introduced_year": db_method.introduced_year,
                "source_url": db_method.source_url,
                "source_title": db_method.source_title,
                "code_snippet_url": db_method.code_snippet_url,
                "image_url": db_method.image_url,
                "image_credit": db_method.image_credit,
                "collection_name": db_method.collection_name,
                "collection_description": db_method.collection_description,
                "collection_parent": db_method.collection_parent,
                "collection_area": db_method.collection_area,
                "paper_count": paper_count,
                "created_at": db_method.created_at,
                "updated_at": db_method.updated_at,
            }

            return Method(**method_dict)

        except ValueError:
            raise PaperNotFoundError(f"Invalid method ID: {method_id}")
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve method: {str(e)}")

    def get_method_by_name(self, method_name: str) -> Method:
        """
        Get a specific AI/ML method by name or slug.

        Args:
            method_name: The method name or slug (case-insensitive exact match)

        Returns:
            Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            # Try to find by slug first (preferred), then fall back to name
            db_method = (
                self.db.query(DBMethod)
                .filter(
                    or_(
                        DBMethod.slug == method_name.lower(),
                        DBMethod.name.ilike(method_name),
                    )
                )
                .first()
            )

            if not db_method:
                raise PaperNotFoundError(f"Method '{method_name}' not found")

            # Get paper count for this method
            paper_count = (
                self.db.query(func.count(PaperMethod.paper_id))
                .filter(PaperMethod.method_id == db_method.id)
                .scalar()
                or 0
            )

            # Convert to API model
            method_dict = {
                "id": str(db_method.id),
                "name": db_method.name,
                "slug": db_method.slug,
                "full_name": db_method.full_name,
                "description": db_method.description,
                "area_id": str(db_method.area_id) if db_method.area_id else None,
                "introduced_year": db_method.introduced_year,
                "source_url": db_method.source_url,
                "source_title": db_method.source_title,
                "code_snippet_url": db_method.code_snippet_url,
                "image_url": db_method.image_url,
                "image_credit": db_method.image_credit,
                "collection_name": db_method.collection_name,
                "collection_description": db_method.collection_description,
                "collection_parent": db_method.collection_parent,
                "collection_area": db_method.collection_area,
                "paper_count": paper_count,
                "created_at": db_method.created_at,
                "updated_at": db_method.updated_at,
            }

            return Method(**method_dict)

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve method: {str(e)}")

    def get_methods_for_paper(
        self,
        paper_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Methods:
        """
        Get all methods associated with a specific paper.

        Args:
            paper_id: The paper ID
            page: Page number (1-based)
            page_size: Number of methods per page

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query with join to paper_methods
            query = (
                self.db.query(DBMethod)
                .join(PaperMethod, PaperMethod.method_id == DBMethod.id)
                .filter(PaperMethod.paper_id == paper_id)
                .order_by(DBMethod.name)
            )

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            methods = []
            for db_method in results:
                # Get paper count for this method
                paper_count = (
                    self.db.query(func.count(PaperMethod.paper_id))
                    .filter(PaperMethod.method_id == db_method.id)
                    .scalar()
                    or 0
                )

                method_dict = {
                    "id": str(db_method.id),
                    "name": db_method.name,
                    "slug": db_method.slug,
                    "full_name": db_method.full_name,
                    "description": db_method.description,
                    "area_id": str(db_method.area_id) if db_method.area_id else None,
                    "introduced_year": db_method.introduced_year,
                    "source_url": db_method.source_url,
                    "source_title": db_method.source_title,
                    "code_snippet_url": db_method.code_snippet_url,
                    "image_url": db_method.image_url,
                    "image_credit": db_method.image_credit,
                    "collection_name": db_method.collection_name,
                    "collection_description": db_method.collection_description,
                    "collection_parent": db_method.collection_parent,
                    "collection_area": db_method.collection_area,
                    "paper_count": paper_count,
                    "created_at": db_method.created_at,
                    "updated_at": db_method.updated_at,
                }
                methods.append(Method(**method_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Methods(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=methods,
            )

        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve methods for paper {paper_id}: {str(e)}"
            )

    def get_papers_for_method(
        self,
        method_id: int,
        page: int = 1,
        page_size: int = 50,
    ) -> List[int]:
        """
        Get all paper IDs that use a specific method.

        Args:
            method_id: The method ID
            page: Page number (1-based)
            page_size: Number of paper IDs per page

        Returns:
            List of paper IDs

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Query paper IDs from paper_methods junction table
            query = (
                self.db.query(PaperMethod.paper_id)
                .filter(PaperMethod.method_id == method_id)
                .order_by(PaperMethod.paper_id)
            )

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Extract paper IDs from results
            paper_ids = [result[0] for result in results]

            return paper_ids

        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve papers for method {method_id}: {str(e)}"
            )

    def search_methods(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Methods:
        """
        Full-text search for methods by name, full_name, or description.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of methods per page

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_methods(
            page=page,
            page_size=page_size,
            search=query,
        )

    def get_method_count(self) -> int:
        """
        Get the total count of methods in the database.

        Returns:
            Total number of methods

        Raises:
            DatabaseError: If database query fails
        """
        try:
            return self.db.query(func.count(DBMethod.id)).scalar() or 0
        except Exception as e:
            raise DatabaseError(f"Failed to get method count: {str(e)}")

    def get_methods_by_collection(
        self,
        collection_name: str,
        page: int = 1,
        page_size: int = 50,
    ) -> Methods:
        """
        Get all methods in a specific collection.

        Args:
            collection_name: Name of the method collection
            page: Page number (1-based)
            page_size: Number of methods per page

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            # Base query
            query = self.db.query(DBMethod).filter(
                DBMethod.collection_name == collection_name
            )

            # Order by name
            query = query.order_by(DBMethod.name)

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            results = query.offset(offset).limit(page_size).all()

            # Convert to API models
            methods = []
            for db_method in results:
                # Get paper count for this method
                paper_count = (
                    self.db.query(func.count(PaperMethod.paper_id))
                    .filter(PaperMethod.method_id == db_method.id)
                    .scalar()
                    or 0
                )

                method_dict = {
                    "id": str(db_method.id),
                    "name": db_method.name,
                    "slug": db_method.slug,
                    "full_name": db_method.full_name,
                    "description": db_method.description,
                    "area_id": str(db_method.area_id) if db_method.area_id else None,
                    "introduced_year": db_method.introduced_year,
                    "source_url": db_method.source_url,
                    "source_title": db_method.source_title,
                    "code_snippet_url": db_method.code_snippet_url,
                    "image_url": db_method.image_url,
                    "image_credit": db_method.image_credit,
                    "collection_name": db_method.collection_name,
                    "collection_description": db_method.collection_description,
                    "collection_parent": db_method.collection_parent,
                    "collection_area": db_method.collection_area,
                    "paper_count": paper_count,
                    "created_at": db_method.created_at,
                    "updated_at": db_method.updated_at,
                }
                methods.append(Method(**method_dict))

            # Calculate pagination
            next_page = page + 1 if offset + page_size < total_count else None
            previous_page = page - 1 if page > 1 else None

            return Methods(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=methods,
            )

        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve methods for collection {collection_name}: {str(e)}"
            )

    def get_methods_by_year(
        self,
        year: int,
        page: int = 1,
        page_size: int = 50,
    ) -> Methods:
        """
        Get all methods introduced in a specific year.

        Args:
            year: Year when the method was introduced
            page: Page number (1-based)
            page_size: Number of methods per page

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_methods(
            page=page,
            page_size=page_size,
            introduced_year=year,
        )

    def get_method_papers(
        self,
        method_id: str,
        page: int = 1,
        page_size: int = 20,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
        include_resources: bool = False,
    ):
        """
        Get papers associated with a specific method.

        Args:
            method_id: The method ID or name
            page: Page number (1-based)
            page_size: Number of papers per page
            latest_only: Whether to only include latest versions
            order_by: Field to order by (date_published, title, citation_count)
            order_dir: Order direction (asc, desc)
            include_resources: Whether to include repositories and methods

        Returns:
            Papers object with pagination info and results

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database query fails
        """
        try:
            from backend.models.database import Paper as DBPaper
            from backend.models.api import Papers
            from sqlalchemy import desc, asc

            # Get method to verify it exists - try by ID first, then by slug/name
            method = None
            if method_id.isdigit():
                method_id_int = int(method_id)
                method = (
                    self.db.query(DBMethod).filter(DBMethod.id == method_id_int).first()
                )

            # If not found by ID or not numeric, try by slug first, then name
            if not method:
                method = (
                    self.db.query(DBMethod)
                    .filter(
                        or_(
                            DBMethod.slug == method_id.lower(),
                            DBMethod.name.ilike(method_id),
                        )
                    )
                    .first()
                )

            if not method:
                raise PaperNotFoundError(f"Method '{method_id}' not found")

            # Base query for papers with this method
            query = (
                self.db.query(DBPaper)
                .join(PaperMethod, DBPaper.id == PaperMethod.paper_id)
                .filter(PaperMethod.method_id == method.id)
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
                next_page=next_page,
                previous_page=previous_page,
                results=papers,
            )

        except PaperNotFoundError:
            raise
        except ValueError:
            raise PaperNotFoundError(f"Invalid method ID: {method_id}")
        except Exception as e:
            raise DatabaseError(f"Failed to get papers for method: {str(e)}")
