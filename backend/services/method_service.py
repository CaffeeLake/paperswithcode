"""
Method service for handling method-related business logic.

This service provides methods for retrieving and managing AI/ML method data,
including pagination, filtering, and paper associations.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, func, desc, asc, or_, case, literal

from backend.models.database import (
    Method as DBMethod,
    Paper as DBPaper,
    PaperMethod,
)
from backend.models.api import Method, Methods
from backend.utils.entity_images import entity_image_url
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.utils.urls import get_method_source_url


class MethodService:
    """Service class for method-related operations."""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _convert_db_method_to_api(
        db_method: DBMethod,
        paper_count: Optional[int] = None,
        recent_paper_count: Optional[int] = None,
        baseline_paper_count: Optional[int] = None,
        *,
        recent_days: int = 90,
        baseline_days: int = 180,
    ) -> Method:
        recent = int(recent_paper_count) if recent_paper_count is not None else None
        baseline = (
            int(baseline_paper_count) if baseline_paper_count is not None else None
        )
        recent_velocity = recent * 30.0 / recent_days if recent is not None else None
        baseline_velocity = (
            baseline * 30.0 / baseline_days if baseline is not None else None
        )
        return Method(
            id=str(db_method.id),
            name=db_method.name,
            slug=db_method.slug,
            full_name=db_method.full_name,
            description=db_method.description,
            keywords=db_method.keywords,
            area_id=str(db_method.area_id) if db_method.area_id else None,
            introduced_year=db_method.introduced_year,
            source_paper_id=str(db_method.source_paper_id)
            if db_method.source_paper_id is not None
            else None,
            source_url=get_method_source_url(
                db_method.source_url, db_method.source_paper
            ),
            source_title=db_method.source_title,
            code_snippet_url=db_method.code_snippet_url,
            image_url=entity_image_url(
                "methods",
                db_method.slug,
                db_method.image_mime_type is not None,
                db_method.image_url,
                db_method.updated_at,
            ),
            image_credit=db_method.image_credit,
            collection_name=db_method.collection_name,
            collection_description=db_method.collection_description,
            collection_parent=db_method.collection_parent,
            paper_count=paper_count,
            recent_paper_count=recent,
            baseline_paper_count=baseline,
            trend_score=(
                round(recent_velocity, 4) if recent_velocity is not None else None
            ),
            rate_change=(
                round(recent_velocity / baseline_velocity, 4)
                if recent_velocity is not None and baseline_velocity
                else None
            ),
            created_at=db_method.created_at,
            updated_at=db_method.updated_at,
        )

    def get_methods(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        name: Optional[str] = None,
        full_name: Optional[str] = None,
        introduced_year: Optional[int] = None,
        area_id: Optional[int] = None,
        exclude_id: Optional[int] = None,
        order_by: str = "name",
        order_dir: str = "asc",
        include_trends: bool = False,
        recent_days: int = 90,
        baseline_days: int = 180,
        today: Optional[date] = None,
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
            order_by: Field to order by
                (name, full_name, introduced_year, created_at, paper_count,
                trend_score)
            order_dir: Order direction (asc, desc)
            include_trends: Include recent and baseline paper-usage activity
            recent_days: Length of the recent method-usage window
            baseline_days: Length of the preceding comparison window
            today: Optional reproducible endpoint for the usage windows

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        try:
            include_trends = include_trends or order_by == "trend_score"
            generated_on = today or datetime.now(UTC).date()
            recent_start = generated_on - timedelta(days=recent_days)
            baseline_start = recent_start - timedelta(days=baseline_days)
            paper_count_subq = (
                self.db.query(
                    PaperMethod.method_id.label("method_id"),
                    func.count(PaperMethod.paper_id).label("paper_count"),
                )
                .group_by(PaperMethod.method_id)
                .subquery()
            )
            paper_count_col = func.coalesce(paper_count_subq.c.paper_count, 0).label(
                "paper_count"
            )
            activity_subq = None
            if include_trends:
                in_recent = and_(
                    DBPaper.date_published > recent_start,
                    DBPaper.date_published <= generated_on,
                )
                in_baseline = and_(
                    DBPaper.date_published > baseline_start,
                    DBPaper.date_published <= recent_start,
                )
                recent_count = func.count(case((in_recent, DBPaper.id), else_=None))
                baseline_count = func.count(case((in_baseline, DBPaper.id), else_=None))
                activity_subq = (
                    self.db.query(
                        PaperMethod.method_id.label("method_id"),
                        recent_count.label("recent_paper_count"),
                        baseline_count.label("baseline_paper_count"),
                    )
                    .join(
                        DBPaper,
                        and_(
                            DBPaper.id == PaperMethod.paper_id,
                            DBPaper.is_latest_version,
                        ),
                    )
                    .filter(
                        DBPaper.date_published > baseline_start,
                        DBPaper.date_published <= generated_on,
                    )
                    .group_by(PaperMethod.method_id)
                    .subquery()
                )
                recent_count_col = func.coalesce(
                    activity_subq.c.recent_paper_count, 0
                ).label("recent_paper_count")
                baseline_count_col = func.coalesce(
                    activity_subq.c.baseline_paper_count, 0
                ).label("baseline_paper_count")
            else:
                recent_count_col = literal(None).label("recent_paper_count")
                baseline_count_col = literal(None).label("baseline_paper_count")
            query = (
                self.db.query(
                    DBMethod,
                    paper_count_col,
                    recent_count_col,
                    baseline_count_col,
                )
                .options(joinedload(DBMethod.source_paper))
                .outerjoin(
                    paper_count_subq, DBMethod.id == paper_count_subq.c.method_id
                )
            )
            if activity_subq is not None:
                query = query.outerjoin(
                    activity_subq, DBMethod.id == activity_subq.c.method_id
                )

            if search:
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

            if area_id is not None:
                query = query.filter(DBMethod.area_id == area_id)

            if exclude_id is not None:
                query = query.filter(DBMethod.id != exclude_id)

            # When a search query is active, rank title matches above
            # description-only matches so e.g. searching "image" surfaces
            # methods named "Image ..." before ones that only mention the
            # term in their description.
            if search:
                search_rank = case(
                    (DBMethod.name.ilike(f"{search}%"), 0),
                    (DBMethod.name.ilike(f"%{search}%"), 1),
                    (DBMethod.full_name.ilike(f"{search}%"), 2),
                    (DBMethod.full_name.ilike(f"%{search}%"), 3),
                    else_=4,
                ).label("search_rank")
                query = query.order_by(asc(search_rank), asc(DBMethod.name))
            else:
                if order_by == "name":
                    order_field = DBMethod.name
                elif order_by == "full_name":
                    order_field = DBMethod.full_name
                elif order_by == "introduced_year":
                    order_field = DBMethod.introduced_year
                elif order_by == "created_at":
                    order_field = DBMethod.created_at
                elif order_by == "paper_count":
                    order_field = paper_count_col
                elif order_by == "trend_score":
                    order_field = recent_count_col
                else:
                    order_field = DBMethod.name

                if order_dir == "desc":
                    query = query.order_by(desc(order_field))
                else:
                    query = query.order_by(asc(order_field))

            total_count = query.count()

            offset = (page - 1) * page_size
            rows = query.offset(offset).limit(page_size).all()

            methods = [
                self._convert_db_method_to_api(
                    db_method,
                    paper_count or 0,
                    recent_papers,
                    baseline_papers,
                    recent_days=recent_days,
                    baseline_days=baseline_days,
                )
                for db_method, paper_count, recent_papers, baseline_papers in rows
            ]

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
                self.db.query(DBMethod)
                .options(joinedload(DBMethod.source_paper))
                .filter(DBMethod.id == method_id_int)
                .first()
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

            return self._convert_db_method_to_api(db_method, paper_count)

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
                .options(joinedload(DBMethod.source_paper))
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

            return self._convert_db_method_to_api(db_method, paper_count)

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
                .options(joinedload(DBMethod.source_paper))
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

                methods.append(self._convert_db_method_to_api(db_method, paper_count))

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

    def search_methods(
        self,
        query: str,
        page: int = 1,
        page_size: int = 50,
        include_trends: bool = False,
    ) -> Methods:
        """
        Full-text search for methods by name, full_name, or description.

        Args:
            query: Search query string
            page: Page number (1-based)
            page_size: Number of methods per page
            include_trends: Include recent and baseline paper-usage activity

        Returns:
            Methods object with pagination info and results

        Raises:
            DatabaseError: If database query fails
        """
        return self.get_methods(
            page=page,
            page_size=page_size,
            search=query,
            include_trends=include_trends,
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
            order_by: Field to order by (date_published, title, citation_count, trending)
            order_dir: Order direction (asc, desc); ignored for trending which is always desc
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
            if order_by == "trending":
                # Match the home feed: rank by the active trending metric
                # (paper-level composite score or official-repo velocity per
                # PWC_TRENDING_RANKING_MODE). Unscored papers stay in the list
                # but sort after scored papers.
                from backend.services.paper_service import PaperService

                query = PaperService(self.db).apply_scoped_trending_order(query)
            else:
                if order_by == "date_published":
                    order_field = DBPaper.date_published
                elif order_by == "title":
                    order_field = DBPaper.title
                elif order_by == "citation_count":
                    order_field = DBPaper.citation_count
                else:
                    order_field = DBPaper.date_published

                if order_dir == "desc":
                    query = query.order_by(desc(order_field), desc(DBPaper.id))
                else:
                    query = query.order_by(asc(order_field), asc(DBPaper.id))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            # Convert to API models
            from backend.services.paper_service import PaperService

            paper_service = PaperService(self.db)
            relation_data = paper_service._get_paper_relation_data(
                [paper.id for paper in db_papers],
                include_resources=include_resources,
                card_view=True,
            )

            papers = []
            for db_paper in db_papers:
                paper = paper_service._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
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

    def add_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Add keywords to a method (appends to existing keywords).

        Args:
            method_id: The method ID or name
            keywords: List of keywords to add

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

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

            # Parse existing keywords
            existing_keywords = []
            if method.keywords:
                existing_keywords = [kw.strip() for kw in method.keywords.split(",")]

            # Add new keywords (avoid duplicates)
            for keyword in keywords:
                keyword = keyword.strip()
                if keyword and keyword not in existing_keywords:
                    existing_keywords.append(keyword)

            # Update keywords
            method.keywords = ", ".join(existing_keywords)
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to add keywords to method: {str(e)}")

    def remove_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Remove specific keywords from a method.

        Args:
            method_id: The method ID or name
            keywords: List of keywords to remove

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

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

            # Parse existing keywords
            existing_keywords = []
            if method.keywords:
                existing_keywords = [kw.strip() for kw in method.keywords.split(",")]

            # Remove specified keywords
            keywords_to_remove = [kw.strip().lower() for kw in keywords]
            existing_keywords = [
                kw for kw in existing_keywords if kw.lower() not in keywords_to_remove
            ]

            # Update keywords
            method.keywords = (
                ", ".join(existing_keywords) if existing_keywords else None
            )
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to remove keywords from method: {str(e)}")

    def replace_keywords(self, method_id: str, keywords: List[str]) -> Method:
        """
        Replace all keywords for a method.

        Args:
            method_id: The method ID or name
            keywords: List of keywords to set (replaces all existing keywords)

        Returns:
            Updated Method object

        Raises:
            PaperNotFoundError: If method not found
            DatabaseError: If database operation fails
        """
        try:
            # Get method - try by ID first, then by name/slug
            method = None
            if method_id.isdigit():
                method = (
                    self.db.query(DBMethod)
                    .filter(DBMethod.id == int(method_id))
                    .first()
                )

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

            # Set new keywords
            cleaned_keywords = [kw.strip() for kw in keywords if kw.strip()]
            method.keywords = ", ".join(cleaned_keywords) if cleaned_keywords else None
            self.db.commit()
            self.db.refresh(method)

            # Return updated method
            return self.get_method_by_id(str(method.id))

        except PaperNotFoundError:
            raise
        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Failed to replace keywords for method: {str(e)}")
