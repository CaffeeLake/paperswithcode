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
from sqlalchemy import desc, asc, or_, func

from backend.models.database import Paper as DBPaper, Author as DBAuthor, PaperAuthor
from backend.models.api import (
    Paper,
    Papers,
    PaperSummary,
    PaperVersion,
    PaperVersions,
    VersionComparison,
)
from backend.utils.urls import (
    get_arxiv_abs_url,
    get_arxiv_pdf_url,
    get_paper_url,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings
from backend.services.semantic_scholar_service import SemanticScholarService


class PaperService:
    """
    Service class for paper-related operations.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()

    def _convert_db_paper_to_api(
        self,
        db_paper: DBPaper,
        include_full_data: bool = True,
        include_resources: bool = False,
    ) -> Paper:
        """
        Convert database paper model to API paper model.

        Args:
            db_paper: Database paper instance
            include_full_data: Whether to include full paper data or just summary
            include_resources: Whether to include repositories and project pages

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
                .order_by(PaperAuthor.author_order)
            )
            authors = [author.name for author in authors_query.all()]
        except Exception:
            # Authors table doesn't exist yet, use empty list
            authors = []

        # Construct URLs
        url_abs = get_arxiv_abs_url(db_paper.arxiv_id, db_paper.version)
        url_pdf = get_arxiv_pdf_url(db_paper.arxiv_id, db_paper.version)

        # Always provide thumbnail URL for ArXiv papers (on-demand generation)
        thumbnail_url = None
        if db_paper.arxiv_id:
            # Generate thumbnail URL that will trigger on-demand generation
            # Format: {arxiv_id_with_underscores}_{version}.jpg
            safe_arxiv_id = db_paper.arxiv_id.replace(".", "_")
            filename = f"{safe_arxiv_id}_{db_paper.version}.jpg"
            thumbnail_url = f"/api/thumbnails/{filename}"

        # Get repositories and project pages if requested
        repositories = None
        project_pages = None

        if include_resources:
            try:
                from .repository_service import RepositoryService
                from .project_page_service import ProjectPageService

                repo_service = RepositoryService(self.db)
                project_page_service = ProjectPageService(self.db)

                # Get repositories for this paper
                paper_repositories = repo_service.get_repositories_for_paper(
                    str(db_paper.id)
                )
                # Extract just the Repository objects from the PaperRepository relationships
                repositories = [
                    pr.repository for pr in paper_repositories if pr.repository
                ]

                # Get project pages for this paper using the new normalized service
                project_pages = project_page_service.get_project_pages_for_paper(
                    str(db_paper.id)
                )

            except Exception:
                # If there's an error fetching resources, just leave them as None
                repositories = None
                project_pages = None

        # Create the API model
        paper_data = {
            "id": str(db_paper.id),
            "arxiv_id": db_paper.arxiv_id,
            "url_abs": url_abs,
            "url_pdf": url_pdf,
            "thumbnail_url": thumbnail_url,
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
            "citation_updated_at": db_paper.citation_updated_at,
            "primary_category": db_paper.primary_category,
            "all_categories": db_paper.all_categories or [],
            "urls_extracted": db_paper.urls_extracted,
            "repositories": repositories,
            "project_pages": project_pages,
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
                .order_by(PaperAuthor.author_order)
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

    def get_paper_by_id(self, paper_id: int, include_resources: bool = False) -> Paper:
        """
        Get a paper by its database ID.

        Args:
            paper_id: Database paper ID
            include_resources: Whether to include repositories and project pages

        Returns:
            API Paper model

        Raises:
            PaperNotFoundError: If paper is not found
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()

            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            return self._convert_db_paper_to_api(
                db_paper, include_resources=include_resources
            )

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {paper_id}: {str(e)}")

    def get_paper_by_arxiv_id(
        self,
        arxiv_id: str,
        version: Optional[str] = None,
        include_resources: bool = False,
    ) -> Paper:
        """
        Get a paper by ArXiv ID and optional version.

        Args:
            arxiv_id: ArXiv ID
            version: Specific version (if None, gets latest version)
            include_resources: Whether to include repositories and project pages

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

            return self._convert_db_paper_to_api(
                db_paper, include_resources=include_resources
            )

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
        include_resources: bool = False,
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
                self._convert_db_paper_to_api(
                    db_paper, include_resources=include_resources
                )
                for db_paper in db_papers
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
        Fast search for papers with improved ranking that prioritizes exact matches.

        Uses ILIKE queries with enhanced ranking:
        1. Exact title matches (highest priority)
        2. Title contains query (sorted by citation count)
        3. Abstract contains query (sorted by citation count)

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of paper summaries ordered by relevance and citation count
        """
        try:
            from sqlalchemy import case

            # Create a ranking score based on match type and citation count
            # Exact title match gets highest score, then partial matches
            ranking_score = case(
                (
                    DBPaper.title.ilike(query),
                    1000000 + DBPaper.citation_count,
                ),  # Exact title match
                (
                    DBPaper.title.ilike(f"%{query}%"),
                    100000 + DBPaper.citation_count,
                ),  # Title contains
                (
                    DBPaper.abstract.ilike(f"%{query}%"),
                    DBPaper.citation_count,
                ),  # Abstract contains
                else_=0,
            )

            results = (
                self.db.query(DBPaper)
                .filter(
                    or_(
                        DBPaper.title.ilike(query),  # Exact match
                        DBPaper.title.ilike(f"%{query}%"),  # Title contains
                        DBPaper.abstract.ilike(f"%{query}%"),  # Abstract contains
                    )
                )
                .filter(DBPaper.is_latest_version)
                .order_by(
                    desc(ranking_score),  # Custom ranking score
                    desc(DBPaper.date_published),  # Date as tiebreaker
                )
                .limit(limit)
                .all()
            )

            return [self._convert_db_paper_to_summary(db_paper) for db_paper in results]

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
                citation_updated_at=paper_data.get("citation_updated_at"),
                primary_category=paper_data.get("primary_category"),
                all_categories=paper_data.get("all_categories"),
                urls_extracted=paper_data.get("urls_extracted", False),
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

    def update_paper_metadata(
        self, paper_id: int, metadata_updates: Dict[str, Any]
    ) -> bool:
        """
        Update paper metadata fields like URLs extracted status, categories, etc.

        Args:
            paper_id: Database paper ID
            metadata_updates: Dictionary of fields to update

        Returns:
            True if successful, False otherwise
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                return False

            # Update allowed metadata fields
            allowed_fields = {
                "urls_extracted",
                "primary_category",
                "all_categories",
                "citation_count",
                "semantic_scholar_id",
                "citation_updated_at",
            }

            for field, value in metadata_updates.items():
                if field in allowed_fields and hasattr(db_paper, field):
                    setattr(db_paper, field, value)

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            print(f"Error updating paper metadata {paper_id}: {e}")
            return False

    def mark_urls_extracted(self, paper_ids: List[int]) -> int:
        """
        Mark papers as having their URLs extracted.

        Args:
            paper_ids: List of paper IDs to update

        Returns:
            Number of papers successfully updated
        """
        try:
            updated_count = (
                self.db.query(DBPaper)
                .filter(DBPaper.id.in_(paper_ids))
                .update({DBPaper.urls_extracted: True}, synchronize_session=False)
            )
            self.db.commit()
            return updated_count

        except Exception as e:
            self.db.rollback()
            print(f"Error marking URLs as extracted: {e}")
            return 0

    def get_papers_needing_url_extraction(self, limit: int = 100) -> List[DBPaper]:
        """
        Get papers that haven't had their URLs extracted yet.

        Args:
            limit: Maximum number of papers to return

        Returns:
            List of papers needing URL extraction
        """
        try:
            return (
                self.db.query(DBPaper)
                .filter(not DBPaper.urls_extracted)
                .filter(DBPaper.is_latest_version)
                .limit(limit)
                .all()
            )

        except Exception as e:
            print(f"Error fetching papers needing URL extraction: {e}")
            return []

    def get_papers_by_category(
        self, category: str, limit: int = 100, latest_only: bool = True
    ) -> List[PaperSummary]:
        """
        Get papers by ArXiv category.

        Args:
            category: ArXiv category (e.g., "cs.CV", "cs.LG")
            limit: Maximum number of papers to return
            latest_only: Whether to only include latest versions

        Returns:
            List of paper summaries in the category
        """
        try:
            query = self.db.query(DBPaper)

            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            # Filter by primary category or any category in all_categories
            query = query.filter(
                or_(
                    DBPaper.primary_category == category,
                    DBPaper.all_categories.contains([category]),
                )
            )

            db_papers = query.order_by(desc(DBPaper.date_published)).limit(limit).all()

            return [
                self._convert_db_paper_to_summary(db_paper) for db_paper in db_papers
            ]

        except Exception as e:
            raise DatabaseError(
                f"Error fetching papers by category {category}: {str(e)}"
            )

    def get_papers_needing_citation_update_count(self, threshold_days: int = 7) -> int:
        """
        Get count of papers that need citation updates.

        Args:
            threshold_days: Only count papers older than this many days

        Returns:
            Number of papers needing citation updates
        """
        try:
            from datetime import datetime, timedelta

            threshold_date = datetime.now() - timedelta(days=threshold_days)

            count = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .count()
            )

            return count

        except Exception as e:
            raise DatabaseError(
                f"Error counting papers needing citation updates: {str(e)}"
            )

    def get_papers_needing_citation_update_chunk(
        self, offset: int, limit: int, threshold_days: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Get a chunk of papers that need citation updates with priority ordering.

        Args:
            offset: Offset for pagination
            limit: Maximum number of papers to return
            threshold_days: Only get papers older than this many days

        Returns:
            List of paper dictionaries with citation update information
        """
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import case

            threshold_date = datetime.now() - timedelta(days=threshold_days)

            # Create priority ordering for citation updates
            priority_order = case(
                (
                    DBPaper.citation_updated_at.is_(None),
                    0,
                ),  # Never updated (highest priority)
                (
                    DBPaper.citation_count == 0,
                    1,
                ),  # Zero citations (may have gained citations)
                else_=2,  # Regular refresh
            )

            # Year-based priority for high-citation periods
            year_priority = case(
                (func.extract("year", DBPaper.date_published).between(2019, 2022), 1),
                (func.extract("year", DBPaper.date_published).between(2017, 2018), 2),
                (func.extract("year", DBPaper.date_published).between(2023, 2024), 3),
                else_=4,
            )

            db_papers = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.arxiv_id.is_not(None))
                .filter(
                    or_(
                        DBPaper.citation_updated_at.is_(None),
                        DBPaper.citation_updated_at < threshold_date,
                    )
                )
                .order_by(
                    priority_order,
                    year_priority,
                    DBPaper.citation_updated_at.asc().nullsfirst(),
                    DBPaper.id.asc(),
                )
                .offset(offset)
                .limit(limit)
                .all()
            )

            # Convert to dictionaries with priority information
            papers_data = []
            for paper in db_papers:
                priority_type = (
                    "NEVER_UPDATED"
                    if paper.citation_updated_at is None
                    else ("ZERO_CITATIONS" if paper.citation_count == 0 else "REFRESH")
                )

                papers_data.append(
                    {
                        "id": paper.id,
                        "arxiv_id": paper.arxiv_id,
                        "title": paper.title,
                        "citation_count": paper.citation_count or 0,
                        "citation_updated_at": paper.citation_updated_at,
                        "date_published": paper.date_published,
                        "priority_type": priority_type,
                    }
                )

            return papers_data

        except Exception as e:
            raise DatabaseError(
                f"Error fetching papers chunk for citation updates: {str(e)}"
            )

    def update_citation_counts_batch(
        self, citation_updates: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Update citation counts for multiple papers in batch.

        Args:
            citation_updates: List of dictionaries with keys:
                - paper_id: Database paper ID
                - citation_count: New citation count
                - semantic_scholar_id: Semantic Scholar paper ID (optional)
                - success: Whether the update was successful

        Returns:
            Dictionary with update statistics: {'updated': count, 'failed': count}
        """
        try:
            stats = {"updated": 0, "failed": 0}

            for update in citation_updates:
                try:
                    paper_id = update["paper_id"]
                    citation_count = update["citation_count"]
                    semantic_scholar_id = update.get("semantic_scholar_id")
                    success = update.get("success", True)

                    if success and semantic_scholar_id:
                        # Successful update with citation data
                        db_paper = (
                            self.db.query(DBPaper)
                            .filter(DBPaper.id == paper_id)
                            .first()
                        )
                        if db_paper:
                            db_paper.citation_count = citation_count
                            db_paper.semantic_scholar_id = semantic_scholar_id
                            db_paper.citation_updated_at = func.now()
                            db_paper.updated_at = func.now()
                            stats["updated"] += 1
                        else:
                            stats["failed"] += 1
                    else:
                        # Failed update - just mark as processed to avoid re-processing
                        db_paper = (
                            self.db.query(DBPaper)
                            .filter(DBPaper.id == paper_id)
                            .first()
                        )
                        if db_paper:
                            db_paper.citation_updated_at = func.now()
                            db_paper.updated_at = func.now()
                            stats["failed"] += 1
                        else:
                            stats["failed"] += 1

                except Exception as e:
                    print(
                        f"Error updating paper {update.get('paper_id', 'unknown')}: {e}"
                    )
                    stats["failed"] += 1

            self.db.commit()
            return stats

        except Exception as e:
            self.db.rollback()
            raise DatabaseError(f"Error updating citation counts batch: {str(e)}")

    def get_citation_statistics(self) -> Dict[str, Any]:
        """
        Get citation update statistics for the database.

        Returns:
            Dictionary with citation statistics
        """
        try:
            # Get overall statistics
            total_papers = (
                self.db.query(DBPaper).filter(DBPaper.is_latest_version).count()
            )

            papers_processed = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.citation_updated_at.is_not(None))
                .count()
            )

            papers_with_citations = (
                self.db.query(DBPaper)
                .filter(DBPaper.is_latest_version)
                .filter(DBPaper.citation_count > 0)
                .count()
            )

            # Calculate percentages
            processed_pct = (
                (papers_processed / total_papers * 100) if total_papers > 0 else 0
            )
            citations_pct = (
                (papers_with_citations / total_papers * 100) if total_papers > 0 else 0
            )

            return {
                "total_papers": total_papers,
                "papers_processed": papers_processed,
                "papers_with_citations": papers_with_citations,
                "processed_percentage": round(processed_pct, 1),
                "citations_percentage": round(citations_pct, 1),
            }

        except Exception as e:
            raise DatabaseError(f"Error getting citation statistics: {str(e)}")
