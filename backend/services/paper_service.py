"""
Paper service for business logic and data processing.

This service handles all paper-related operations, including:
- Fetching papers with proper URL construction
- Converting database models to API models
- Handling pagination
- Managing paper versions
"""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, func, case

try:
    from ..models.database import Paper as DBPaper, Author as DBAuthor, PaperAuthor
    from ..models.api import (
        Paper,
        Papers,
        PaperSummary,
        PaperVersion,
        PaperVersions,
        VersionComparison,
    )
    from ..utils.urls import (
        get_arxiv_abs_url,
        get_arxiv_pdf_url,
        get_paper_url,
    )
except ImportError:
    # Handle case when running as script
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(backend_dir))
    from models.database import Paper as DBPaper, Author as DBAuthor, PaperAuthor
    from models.api import (
        Paper,
        Papers,
        PaperSummary,
        PaperVersion,
        PaperVersions,
        VersionComparison,
    )
    from utils.urls import get_arxiv_abs_url, get_arxiv_pdf_url, get_paper_url
try:
    from ..utils.exceptions import PaperNotFoundError, DatabaseError
    from ..config import get_settings
    from .semantic_scholar_service import SemanticScholarService
except ImportError:
    # Handle case when running as script
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).parent.parent
    sys.path.insert(0, str(backend_dir))
    from utils.exceptions import PaperNotFoundError, DatabaseError
    from config import get_settings
    from services.semantic_scholar_service import SemanticScholarService


class PaperService:
    """
    Service class for paper-related operations.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _convert_db_paper_to_api(
        self, db_paper: DBPaper, include_full_data: bool = True
    ) -> Paper:
        """
        Convert database paper model to API paper model.

        Args:
            db_paper: Database paper instance
            include_full_data: Whether to include full paper data or just summary

        Returns:
            API Paper model
        """
        # Get authors for this paper - handle case where authors table doesn't exist yet
        authors = []
        try:
            authors_query = (
                self.db.query(DBAuthor)
                .join(PaperAuthor)
                .filter(PaperAuthor.paper_id == db_paper.id)
            )
            authors = [author.name for author in authors_query.all()]
        except Exception:
            # Authors table doesn't exist yet, use empty list
            authors = []

        # Construct URLs
        url_abs = get_arxiv_abs_url(db_paper.arxiv_id, db_paper.version)
        url_pdf = get_arxiv_pdf_url(db_paper.arxiv_id, db_paper.version)

        # Create the API model
        paper_data = {
            "id": str(db_paper.id),
            "arxiv_id": db_paper.arxiv_id,
            "url_abs": url_abs,
            "url_pdf": url_pdf,
            "title": db_paper.title,
            "abstract": db_paper.abstract or "",
            "authors": authors,
            "published": db_paper.date_published,
            "conference": db_paper.conference,
            "conference_url_abs": db_paper.conference_url_abs,
            "conference_url_pdf": db_paper.conference_url_pdf,
            "proceeding": db_paper.proceeding,
            "version": db_paper.version,
            "is_latest_version": db_paper.is_latest_version,
            "citation_count": db_paper.citation_count,
            "semantic_scholar_id": db_paper.semantic_scholar_id,
        }

        return Paper(**paper_data)

    def _convert_db_paper_to_summary(self, db_paper: DBPaper) -> PaperSummary:
        """
        Convert database paper model to API paper summary model.

        Args:
            db_paper: Database paper instance

        Returns:
            API PaperSummary model
        """
        # Get authors for this paper - handle case where authors table doesn't exist yet
        authors = []
        try:
            authors_query = (
                self.db.query(DBAuthor)
                .join(PaperAuthor)
                .filter(PaperAuthor.paper_id == db_paper.id)
            )
            authors = [author.name for author in authors_query.all()]
        except Exception:
            # Authors table doesn't exist yet, use empty list
            authors = []

        # Construct URLs
        url_abs = get_arxiv_abs_url(db_paper.arxiv_id, db_paper.version)

        return PaperSummary(
            id=str(db_paper.id),
            title=db_paper.title,
            arxiv_id=db_paper.arxiv_id,
            authors=authors,
            published=db_paper.date_published,
            url_abs=url_abs,
            citation_count=db_paper.citation_count,
        )

    def get_paper_by_id(self, paper_id: int) -> Paper:
        """
        Get a paper by its database ID.

        Args:
            paper_id: Database paper ID

        Returns:
            API Paper model

        Raises:
            PaperNotFoundError: If paper is not found
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()

            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            return self._convert_db_paper_to_api(db_paper)

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {paper_id}: {str(e)}")

    def get_paper_by_arxiv_id(
        self, arxiv_id: str, version: Optional[str] = None
    ) -> Paper:
        """
        Get a paper by ArXiv ID and optional version.

        Args:
            arxiv_id: ArXiv ID
            version: Specific version (if None, gets latest version)

        Returns:
            API Paper model

        Raises:
            PaperNotFoundError: If paper is not found
        """
        try:
            query = self.db.query(DBPaper).filter(DBPaper.arxiv_id == arxiv_id)

            if version:
                query = query.filter(DBPaper.version == version)
            else:
                # Get latest version
                query = query.filter(DBPaper.is_latest_version)

            db_paper = query.first()

            if not db_paper:
                version_text = f" version {version}" if version else " (latest version)"
                raise PaperNotFoundError(
                    f"Paper with ArXiv ID {arxiv_id}{version_text} not found"
                )

            return self._convert_db_paper_to_api(db_paper)

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {arxiv_id}: {str(e)}")

    def get_papers(
        self,
        page: int = 1,
        page_size: int = None,
        search: Optional[str] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        conference: Optional[str] = None,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
    ) -> Papers:
        """
        Get paginated list of papers with optional filtering.

        Args:
            page: Page number (1-based)
            page_size: Number of papers per page
            search: Search term for title/abstract
            published_after: Filter papers published after this date (YYYY-MM-DD)
            published_before: Filter papers published before this date (YYYY-MM-DD)
            conference: Filter by conference
            latest_only: Whether to only include latest versions of papers
            order_by: Field to order by (date_published, title)
            order_dir: Order direction (asc, desc)

        Returns:
            Paginated Papers response
        """
        try:
            # Set default page size
            if page_size is None:
                page_size = self.settings.default_page_size

            # Limit page size
            page_size = min(page_size, self.settings.max_page_size)

            # Build base query
            query = self.db.query(DBPaper)

            # Filter for latest versions only
            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Apply search filter
            if search:
                search_term = f"%{search}%"
                query = query.filter(
                    or_(
                        DBPaper.title.ilike(search_term),
                        DBPaper.abstract.ilike(search_term),
                    )
                )

            # Apply date filters
            if published_after:
                query = query.filter(DBPaper.date_published >= published_after)

            if published_before:
                query = query.filter(DBPaper.date_published <= published_before)

            # Apply conference filter
            if conference:
                query = query.filter(DBPaper.conference.ilike(f"%{conference}%"))

            # Apply ordering
            order_column = getattr(DBPaper, order_by, DBPaper.date_published)
            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            # Convert to API models
            api_papers = [
                self._convert_db_paper_to_api(db_paper) for db_paper in db_papers
            ]

            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_papers,
            )

        except Exception as e:
            raise DatabaseError(f"Error fetching papers: {str(e)}")

    def get_paper_versions(self, arxiv_id: str) -> PaperVersions:
        """
        Get all versions of a paper by ArXiv ID.

        Args:
            arxiv_id: ArXiv ID

        Returns:
            PaperVersions with all versions

        Raises:
            PaperNotFoundError: If no versions found
        """
        try:
            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id)
                .order_by(desc(DBPaper.version))
                .all()
            )

            if not db_papers:
                raise PaperNotFoundError(f"No papers found for ArXiv ID {arxiv_id}")

            versions = []
            for db_paper in db_papers:
                abstract_preview = None
                if db_paper.abstract:
                    abstract_preview = (
                        db_paper.abstract[:200] + "..."
                        if len(db_paper.abstract) > 200
                        else db_paper.abstract
                    )

                version = PaperVersion(
                    id=str(db_paper.id),
                    version=db_paper.version,
                    title=db_paper.title,
                    is_latest=db_paper.is_latest_version,
                    published=db_paper.date_published,
                    url_abs=get_arxiv_abs_url(db_paper.arxiv_id, db_paper.version),
                    paper_url=get_paper_url(db_paper.id, db_paper.arxiv_id),
                    abstract_preview=abstract_preview,
                )
                versions.append(version)

            return PaperVersions(
                arxiv_id=arxiv_id, total_versions=len(versions), versions=versions
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(
                f"Error fetching paper versions for {arxiv_id}: {str(e)}"
            )

    def compare_paper_versions(
        self, arxiv_id: str, from_version: str, to_version: str
    ) -> VersionComparison:
        """
        Compare two versions of a paper.

        Args:
            arxiv_id: ArXiv ID
            from_version: Source version
            to_version: Target version

        Returns:
            VersionComparison object

        Raises:
            PaperNotFoundError: If either version is not found
        """
        try:
            # Get both versions
            old_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.version == from_version)
                .first()
            )

            new_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.arxiv_id == arxiv_id, DBPaper.version == to_version)
                .first()
            )

            if not old_paper:
                raise PaperNotFoundError(
                    f"Paper version {from_version} not found for ArXiv ID {arxiv_id}"
                )

            if not new_paper:
                raise PaperNotFoundError(
                    f"Paper version {to_version} not found for ArXiv ID {arxiv_id}"
                )

            # Calculate time difference
            time_between = None
            if old_paper.created_at and new_paper.created_at:
                time_between = (new_paper.created_at - old_paper.created_at).days

            return VersionComparison(
                from_version=from_version,
                to_version=to_version,
                title_changed=old_paper.title != new_paper.title,
                abstract_changed=old_paper.abstract != new_paper.abstract,
                date_changed=old_paper.date_published != new_paper.date_published,
                time_between_versions=time_between,
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error comparing paper versions: {str(e)}")

    def search_papers(self, query: str, limit: int = 10) -> List[PaperSummary]:
        """
        Full-text search for papers with citation-based ranking.

        This search implementation uses a multi-tier approach with citation count weighting:
        1. Exact title matches (highest priority) - sorted by citation count
        2. Title contains query (medium priority) - sorted by citation count
        3. Full-text search in title and abstract (lowest priority) - sorted by relevance + citation count

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of paper summaries ordered by relevance and importance (citation count)
        """
        try:
            # Use a prioritized search approach with citation-based ranking
            # Priority 1: Exact title match
            # Priority 2: Title contains query
            # Priority 3: Full-text search match

            # First, try prioritized title-based search with citation ranking
            title_results = (
                self.db.query(DBPaper)
                .filter(
                    or_(
                        DBPaper.title.ilike(query),  # Case-insensitive exact match
                        DBPaper.title.ilike(f"%{query}%"),  # Contains match
                    )
                )
                .filter(DBPaper.is_latest_version)
                .order_by(
                    # Prioritize exact matches first, then by citation count and publication date
                    case((DBPaper.title.ilike(query), 1), else_=2).asc(),
                    desc(
                        DBPaper.citation_count
                    ),  # Higher citation count = higher ranking
                    desc(DBPaper.date_published),  # More recent papers as tiebreaker
                )
                .limit(limit)
                .all()
            )

            # If we have enough title-based results, return them
            if len(title_results) >= limit:
                return [
                    self._convert_db_paper_to_summary(db_paper)
                    for db_paper in title_results
                ]

            # Otherwise, supplement with full-text search results
            title_ids = {paper.id for paper in title_results}
            remaining_limit = limit - len(title_results)

            if remaining_limit > 0:
                # Full-text search with combined ranking: text relevance + citation importance
                fulltext_results = (
                    self.db.query(DBPaper)
                    .filter(
                        func.to_tsvector(
                            "english",
                            DBPaper.title + " " + func.coalesce(DBPaper.abstract, ""),
                        ).op("@@")(func.plainto_tsquery("english", query))
                    )
                    .filter(DBPaper.is_latest_version)
                    .filter(~DBPaper.id.in_(title_ids))  # Exclude already found papers
                    .order_by(
                        # Combined ranking: text relevance score + normalized citation score
                        desc(
                            func.ts_rank(
                                func.to_tsvector(
                                    "english",
                                    DBPaper.title
                                    + " "
                                    + func.coalesce(DBPaper.abstract, ""),
                                ),
                                func.plainto_tsquery("english", query),
                            )
                            +
                            # Normalize citation count to 0-1 range and add to relevance score
                            (func.log(func.greatest(DBPaper.citation_count, 1)) / 10.0)
                        ),
                        desc(
                            DBPaper.citation_count
                        ),  # Secondary sort by citation count
                        desc(
                            DBPaper.date_published
                        ),  # Tertiary sort by publication date
                    )
                    .limit(remaining_limit)
                    .all()
                )

                # Combine results: title matches first, then full-text matches
                all_results = title_results + fulltext_results
            else:
                all_results = title_results

            return [
                self._convert_db_paper_to_summary(db_paper) for db_paper in all_results
            ]

        except Exception as e:
            raise DatabaseError(f"Error searching papers: {str(e)}")

    def get_recent_papers(self, limit: int = 10) -> List[PaperSummary]:
        """
        Get recently published papers.

        Args:
            limit: Maximum number of papers to return

        Returns:
            List of recent paper summaries
        """
        try:
            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.date_published.is_not(None))
                .order_by(desc(DBPaper.date_published))
                .limit(limit)
                .all()
            )

            return [
                self._convert_db_paper_to_summary(db_paper) for db_paper in db_papers
            ]

        except Exception as e:
            raise DatabaseError(f"Error fetching recent papers: {str(e)}")

    def get_paper_stats(self) -> Dict[str, Any]:
        """
        Get statistics about papers in the database.

        Returns:
            Dictionary with paper statistics
        """
        try:
            total_papers = self.db.query(DBPaper).count()
            total_latest = (
                self.db.query(DBPaper).filter(DBPaper.is_latest_version).count()
            )

            # Get papers by year
            year_stats = (
                self.db.query(
                    func.extract("year", DBPaper.date_published).label("year"),
                    func.count(DBPaper.id).label("count"),
                )
                .filter(DBPaper.date_published.is_not(None))
                .filter(DBPaper.is_latest_version)
                .group_by(func.extract("year", DBPaper.date_published))
                .order_by(desc("year"))
                .limit(10)
                .all()
            )

            # Get latest paper date
            latest_paper = (
                self.db.query(DBPaper)
                .filter(DBPaper.date_published.is_not(None))
                .order_by(desc(DBPaper.date_published))
                .first()
            )

            return {
                "total_papers": total_papers,
                "latest_versions_only": total_latest,
                "papers_by_year": [
                    {"year": int(stat.year), "count": stat.count} for stat in year_stats
                ],
                "latest_paper_date": latest_paper.date_published.isoformat()
                if latest_paper
                else None,
            }

        except Exception as e:
            raise DatabaseError(f"Error fetching paper statistics: {str(e)}")

    async def update_citation_counts(self, limit: int = 100) -> Dict[str, Any]:
        """
        Update citation counts for papers using Semantic Scholar API.

        Args:
            limit: Maximum number of papers to update

        Returns:
            Dictionary with update statistics
        """
        try:
            semantic_scholar_service = SemanticScholarService(self.db)
            updated_count = await semantic_scholar_service.batch_update_citation_counts(
                limit
            )

            return {
                "updated_count": updated_count,
                "limit": limit,
                "status": "completed",
            }

        except Exception as e:
            raise DatabaseError(f"Error updating citation counts: {str(e)}")

    async def search_papers_with_semantic_scholar(
        self, query: str, limit: int = 10
    ) -> List[PaperSummary]:
        """
        Enhanced search that also queries Semantic Scholar for highly cited papers.

        This method combines local database search with Semantic Scholar API results
        to ensure highly cited papers are included in search results.

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of paper summaries with enhanced citation-based ranking
        """
        try:
            # Get local search results
            local_results = self.search_papers(query, limit)

            # If we have enough results, return them
            if len(local_results) >= limit:
                return local_results

            # Otherwise, supplement with Semantic Scholar search
            semantic_scholar_service = SemanticScholarService(self.db)
            highly_cited = await semantic_scholar_service.get_highly_cited_papers(
                query, limit
            )

            # Try to find these papers in our database
            local_titles = {result.title.lower() for result in local_results}
            supplemental_results = []

            for title, citation_count in highly_cited:
                if (
                    title.lower() not in local_titles
                    and len(local_results) + len(supplemental_results) < limit
                ):
                    # Try to find this paper in our database
                    db_paper = (
                        self.db.query(DBPaper)
                        .filter(DBPaper.title.ilike(f"%{title}%"))
                        .filter(DBPaper.is_latest_version)
                        .first()
                    )

                    if db_paper:
                        # Update citation count if it's higher
                        if citation_count > db_paper.citation_count:
                            db_paper.citation_count = citation_count
                            self.db.commit()

                        supplemental_results.append(
                            self._convert_db_paper_to_summary(db_paper)
                        )

            # Combine and return results
            all_results = local_results + supplemental_results
            return all_results[:limit]

        except Exception:
            # Fall back to local search if Semantic Scholar fails
            return self.search_papers(query, limit)

    def add_paper(self, paper_data: Dict[str, Any]) -> Optional[int]:
        """
        Add a single paper to the database.

        Args:
            paper_data: Dictionary containing paper information with keys:
                - arxiv_id: ArXiv ID (required)
                - title: Paper title (required)
                - abstract: Paper abstract (optional)
                - version: Version string (default: 'v1')
                - date_published: Publication date (optional)
                - conference: Conference name (optional)
                - conference_url_abs: Conference abstract URL (optional)
                - conference_url_pdf: Conference PDF URL (optional)
                - proceeding: Proceeding information (optional)
                - is_latest_version: Whether this is the latest version (default: True)

        Returns:
            Paper ID if successful, None if paper already exists or on error
        """
        try:
            # Check if paper already exists
            existing = (
                self.db.query(DBPaper)
                .filter(
                    DBPaper.arxiv_id == paper_data["arxiv_id"],
                    DBPaper.version == paper_data.get("version", "v1"),
                )
                .first()
            )

            if existing:
                return None  # Paper already exists

            # Create new paper
            db_paper = DBPaper(
                arxiv_id=paper_data["arxiv_id"],
                title=paper_data["title"],
                abstract=paper_data.get("abstract"),
                version=paper_data.get("version", "v1"),
                date_published=paper_data.get("date_published"),
                conference=paper_data.get("conference"),
                conference_url_abs=paper_data.get("conference_url_abs"),
                conference_url_pdf=paper_data.get("conference_url_pdf"),
                proceeding=paper_data.get("proceeding"),
                is_latest_version=paper_data.get("is_latest_version", True),
                citation_count=paper_data.get("citation_count", 0),
                semantic_scholar_id=paper_data.get("semantic_scholar_id"),
            )

            self.db.add(db_paper)
            self.db.commit()
            self.db.refresh(db_paper)

            return db_paper.id

        except Exception as e:
            self.db.rollback()
            print(f"Error adding paper {paper_data.get('arxiv_id', 'unknown')}: {e}")
            return None

    def add_papers_batch(
        self, papers_data: List[Dict[str, Any]], batch_size: int = 100
    ) -> Dict[str, int]:
        """
        Add multiple papers to the database in batches for better performance.

        Args:
            papers_data: List of paper data dictionaries
            batch_size: Number of papers to process in each batch

        Returns:
            Dictionary with statistics: {'added': count, 'skipped': count, 'errors': count}
        """
        stats = {"added": 0, "skipped": 0, "errors": 0}

        try:
            for i in range(0, len(papers_data), batch_size):
                batch = papers_data[i : i + batch_size]

                # Process batch
                for paper_data in batch:
                    try:
                        paper_id = self.add_paper(paper_data)
                        if paper_id:
                            stats["added"] += 1
                        else:
                            stats["skipped"] += 1
                    except Exception as e:
                        stats["errors"] += 1
                        print(f"Error in batch processing: {e}")

                # Progress report
                if (i + len(batch)) % (batch_size * 10) == 0:
                    print(
                        f"Processed {i + len(batch):,} papers... (added: {stats['added']:,}, skipped: {stats['skipped']:,}, errors: {stats['errors']:,})"
                    )

            return stats

        except Exception as e:
            print(f"Error in batch processing: {e}")
            return stats
