"""
Paper service for business logic and data processing.

This service handles all paper-related operations, including:
- Fetching papers with proper URL construction
- Converting database models to API models
- Handling pagination
- Managing paper versions
"""

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc, asc, or_, func, text

from backend.models.database import (
    Paper as DBPaper,
    Author as DBAuthor,
    PaperAuthor,
    Task as DBTask,
    Method as DBMethod,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    Conference as DBConference,
    Organization as DBOrganization,
    HfArtifact as DBHfArtifact,
    PaperHfArtifact as DBPaperHfArtifact,
    Framework as DBFramework,
    TaskFramework as DBTaskFramework,
)
from backend.services.thumbnail_service import (
    ThumbnailService,
    build_custom_thumbnail_url,
    build_external_thumbnail_filename,
    build_thumbnail_filename,
    build_thumbnail_url,
)
from backend.models.api import (
    Paper,
    PaperFeedScope,
    Papers,
    PaperSummary,
    PaperSearchResults,
    RelatedPaperRecommendation,
    RepositoryTrendingPaper,
    RepositoryTrendingRepository,
    RepositoryTrendingScore,
    RepositoryTrendingTask,
    PaperVersion,
    PaperVersions,
    TaskSummary,
    VersionComparison,
    HfArtifactSummary,
)
from backend.utils.urls import (
    get_arxiv_abs_url,
    get_paper_abs_url,
    get_paper_pdf_url,
    get_paper_url,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings
from backend.services.paper_association_service import PaperAssociationService
from backend.services.paper_citation_refresh_service import PaperCitationRefreshService
from backend.services.paper_relation_loader import PaperRelationLoader, PaperRelations
from backend.services.paper_retrieval_service import PaperRetrievalService
from backend.services.paper_version_refresh_service import (
    ArxivPaperRefreshResult,
    PaperVersionRefreshService,
)
from backend.services.semantic_scholar_service import SemanticScholarService
from backend.services.trending_ranking_service import active_paper_score_components
from backend.utils.github_utils import normalize_github_url, parse_github_url


class PaperService:
    """
    Service class for paper-related operations.
    """

    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self._thumbnail_service: Optional[ThumbnailService] = None

    def _get_thumbnail_service(self) -> ThumbnailService:
        if self._thumbnail_service is None:
            self._thumbnail_service = ThumbnailService()
        return self._thumbnail_service

    def _resolve_thumbnail_url(self, db_paper: DBPaper) -> Optional[str]:
        """Return the public thumbnail URL for a paper row."""
        if db_paper.thumbnail_url:
            return db_paper.thumbnail_url
        if db_paper.source == "arxiv" and db_paper.arxiv_id:
            filename = build_thumbnail_filename(
                db_paper.arxiv_id, db_paper.version or "v1"
            )
            if self._get_thumbnail_service().get_local_thumbnail_path(filename):
                return build_thumbnail_url(filename)
        if db_paper.source == "external":
            filename = build_external_thumbnail_filename(db_paper.id)
            if self._get_thumbnail_service().get_local_custom_thumbnail_path(filename):
                return build_custom_thumbnail_url(filename)
        return None

    def hydrate_cards(
        self,
        db_papers: Sequence[DBPaper],
        *,
        include_resources: bool = False,
    ) -> list[Paper]:
        """Hydrate paper rows with the relations rendered by card surfaces."""
        papers = list(db_papers)
        paper_ids = [paper.id for paper in papers]
        loader = PaperRelationLoader(self.db)
        relations = loader.load_cards(paper_ids)
        if include_resources:
            loader.load_resources(paper_ids, relations)
        return [self._to_api_paper(paper, relations) for paper in papers]

    def hydrate_details(
        self,
        db_papers: Sequence[DBPaper],
        *,
        include_resources: bool = False,
    ) -> list[Paper]:
        """Hydrate paper rows with card and detail-only relations."""
        papers = list(db_papers)
        paper_ids = [paper.id for paper in papers]
        loader = PaperRelationLoader(self.db)
        relations = loader.load_details(paper_ids)
        if include_resources:
            loader.load_resources(paper_ids, relations)
        return [self._to_api_paper(paper, relations) for paper in papers]

    # Map the singular DB artifact kind to the Hugging Face listing path segment.
    _HF_KIND_TO_PATH = {"model": "models", "dataset": "datasets", "space": "spaces"}

    @staticmethod
    def _build_hf_artifact_summary(
        db_paper: DBPaper,
        junction_counts: Dict[str, int],
    ) -> Optional[HfArtifactSummary]:
        """
        Build the compact HF artifact summary used by feed cards.

        Counts combine the normalized junction-table artifacts (populated by the
        HF cron, authoritative for ArXiv papers) with any explicit URL arrays on
        the paper (used by `source='external'` rows). The winning category is the
        most populated kind, with a deterministic tie-break: model > dataset >
        space.
        """
        explicit = {
            "model": db_paper.hf_models or [],
            "dataset": db_paper.hf_datasets or [],
            "space": db_paper.hf_spaces or [],
        }
        counts = {
            kind: max(junction_counts.get(kind, 0), len(explicit[kind]))
            for kind in ("model", "dataset", "space")
        }

        if not any(counts.values()):
            return None

        # Deterministic tie-break order: model, then dataset, then space.
        best_kind = max(
            ("model", "dataset", "space"),
            key=lambda kind: counts[kind],
        )
        best_count = counts[best_kind]

        path = PaperService._HF_KIND_TO_PATH[best_kind]
        if db_paper.arxiv_id:
            if best_kind == "space":
                # HF has no working arXiv filter on the Spaces catalog; the paper
                # page lists linked Spaces instead.
                canonical = re.sub(r"v\d+$", "", db_paper.arxiv_id.strip())
                best_url = f"https://huggingface.co/papers/{canonical}"
            else:
                best_url = (
                    f"https://huggingface.co/{path}?other=arxiv:{db_paper.arxiv_id}"
                )
        else:
            best_url = explicit[best_kind][0] if explicit[best_kind] else None

        return HfArtifactSummary(
            model_count=counts["model"],
            dataset_count=counts["dataset"],
            space_count=counts["space"],
            best_kind=best_kind,
            best_count=best_count,
            best_url=best_url,
        )

    def get_linked_hf_artifact_urls(self, paper_id: int) -> dict[str, list[str]]:
        """Return normalized Hub links ordered by kind and popularity."""

        rows = (
            self.db.query(DBHfArtifact.kind, DBHfArtifact.url)
            .join(
                DBPaperHfArtifact,
                DBPaperHfArtifact.hf_artifact_id == DBHfArtifact.id,
            )
            .filter(DBPaperHfArtifact.paper_id == paper_id)
            .order_by(
                DBHfArtifact.kind,
                DBHfArtifact.trending_score.desc().nullslast(),
                DBHfArtifact.downloads.desc().nullslast(),
                DBHfArtifact.likes.desc().nullslast(),
                DBHfArtifact.repo_id,
            )
            .all()
        )
        fields = {
            "model": "hf_models",
            "dataset": "hf_datasets",
            "space": "hf_spaces",
        }
        result: dict[str, list[str]] = {field: [] for field in fields.values()}
        for kind, url in rows:
            result[fields[kind]].append(url)
        return result

    @staticmethod
    def _get_published_after_for_time_window(
        time_window: str,
        today: Optional[date] = None,
    ) -> Optional[date]:
        """
        Convert public feed time presets into UTC date boundaries.
        """
        current_date = today or datetime.now(timezone.utc).date()

        if time_window == "today":
            return current_date
        if time_window == "week":
            return current_date - timedelta(days=current_date.weekday())
        if time_window == "month":
            return current_date.replace(day=1)
        if time_window == "all_time":
            return None

        raise ValueError(f"Unsupported time window: {time_window}")

    def _to_api_paper(
        self,
        db_paper: DBPaper,
        relations: PaperRelations,
    ) -> Paper:
        """Convert one database paper using an already-loaded projection."""
        authors = relations.authors.get(db_paper.id, [])
        author_links = relations.author_links.get(db_paper.id, [])

        # Source-aware URL construction. ArXiv rows derive abs/pdf URLs from
        # `arxiv_id` + `version`. External rows use `source_url` for the
        # primary link and have no derived PDF.
        url_abs = get_paper_abs_url(
            db_paper.source,
            db_paper.arxiv_id,
            db_paper.version,
            db_paper.source_url,
        )
        url_pdf = get_paper_pdf_url(
            db_paper.source, db_paper.arxiv_id, db_paper.version
        )

        thumbnail_url = self._resolve_thumbnail_url(db_paper)

        tasks = relations.tasks.get(db_paper.id) or None
        methods = relations.methods.get(db_paper.id) or None
        introduced_benchmarks = relations.introduced_benchmarks.get(db_paper.id) or None
        introduced_frameworks = relations.introduced_frameworks.get(db_paper.id) or None
        predecessor_papers = relations.predecessor_papers.get(db_paper.id) or None
        successor_papers = relations.successor_papers.get(db_paper.id) or None
        organizations = relations.organizations.get(db_paper.id) or None
        leaderboard_ranks = relations.leaderboard_ranks.get(db_paper.id) or None
        linked_conference = relations.conferences.get(db_paper.id)
        hf_artifact_summary = self._build_hf_artifact_summary(
            db_paper,
            relations.hf_artifact_counts.get(db_paper.id) or {},
        )
        repositories = relations.repositories.get(db_paper.id) or None
        project_pages = relations.project_pages.get(db_paper.id) or None

        # Create the API model
        paper_data = {
            "id": str(db_paper.id),
            "arxiv_id": db_paper.arxiv_id,
            "source": db_paper.source,
            "source_url": db_paper.source_url,
            "url_abs": url_abs,
            "url_pdf": url_pdf,
            "thumbnail_url": thumbnail_url,
            "title": db_paper.title,
            "abstract": db_paper.abstract or "",
            "authors": authors,
            "author_links": author_links,
            "published": db_paper.date_published,
            "conference": db_paper.conference,
            "conference_url_abs": db_paper.conference_url_abs,
            "conference_url_pdf": db_paper.conference_url_pdf,
            "proceeding": db_paper.proceeding,
            "conference_slug": linked_conference.slug if linked_conference else None,
            "conference_name": linked_conference.name if linked_conference else None,
            "version": db_paper.version,
            "is_latest_version": db_paper.is_latest_version,
            "citation_count": db_paper.citation_count,
            "semantic_scholar_id": db_paper.semantic_scholar_id,
            "citation_updated_at": db_paper.citation_updated_at,
            "primary_category": db_paper.primary_category,
            "all_categories": db_paper.all_categories or [],
            "urls_extracted": db_paper.urls_extracted,
            "tldr": db_paper.tldr,
            "num_pages": db_paper.num_pages,
            "hf_models": db_paper.hf_models or [],
            "hf_datasets": db_paper.hf_datasets or [],
            "hf_spaces": db_paper.hf_spaces or [],
            "hf_artifact_summary": hf_artifact_summary,
            "repositories": repositories,
            "project_pages": project_pages,
            "tasks": tasks,
            "methods": methods,
            "introduced_benchmarks": introduced_benchmarks,
            "introduced_frameworks": introduced_frameworks,
            "predecessor_papers": predecessor_papers,
            "successor_papers": successor_papers,
            "organizations": organizations,
            "leaderboard_ranks": leaderboard_ranks,
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

        # Source-aware URL: ArXiv abs URL for ArXiv rows, source_url for external.
        url_abs = get_paper_abs_url(
            db_paper.source,
            db_paper.arxiv_id,
            db_paper.version,
            db_paper.source_url,
        )

        thumbnail_url = self._resolve_thumbnail_url(db_paper)

        return PaperSummary(
            id=str(db_paper.id),
            title=db_paper.title,
            arxiv_id=db_paper.arxiv_id,
            source=db_paper.source,
            source_url=db_paper.source_url,
            authors=authors,
            published=db_paper.date_published,
            url_abs=url_abs,
            citation_count=db_paper.citation_count,
            thumbnail_url=thumbnail_url,
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

            return self.hydrate_details(
                [db_paper], include_resources=include_resources
            )[0]

        except Exception as e:
            if isinstance(e, PaperNotFoundError):
                raise
            raise DatabaseError(f"Error fetching paper {paper_id}: {str(e)}")

    def get_paper_by_id_or_arxiv(
        self, identifier: str, include_resources: bool = False
    ) -> Paper:
        """
        Resolve a paper by either an ArXiv ID or an internal database ID.

        This is used by the public `/papers/{paper_id}` route so that:
          - `source='arxiv'` rows keep ArXiv-style URLs like `/papers/2504.12516`.
          - `source='external'` rows are addressed by their internal `papers.id`.

        ArXiv lookups are attempted first when the identifier matches the
        ArXiv format. Otherwise the identifier is parsed as an integer ID.
        """
        from backend.database.paper_merge import lookup_paper_merge_redirect
        from backend.utils.urls import (
            normalize_paper_route_identifier,
            validate_arxiv_id,
        )

        identifier = normalize_paper_route_identifier(identifier)

        if validate_arxiv_id(identifier):
            try:
                return self.get_paper_by_arxiv_id(
                    identifier, version=None, include_resources=include_resources
                )
            except PaperNotFoundError:
                # Fall through to internal-ID lookup; external rows or
                # unindexed ArXiv IDs are still addressable that way.
                pass

        try:
            paper_id = int(identifier)
        except (TypeError, ValueError):
            raise PaperNotFoundError(f"No paper found for identifier '{identifier}'")

        redirect = lookup_paper_merge_redirect(self.db, paper_id)
        if redirect:
            return self.get_paper_by_id_or_arxiv(
                redirect, include_resources=include_resources
            )

        return self.get_paper_by_id(paper_id, include_resources=include_resources)

    def _resolve_db_paper_by_id_or_arxiv(self, identifier: str) -> DBPaper:
        """Resolve the route identifier to its canonical database row."""
        resolved = self.get_paper_by_id_or_arxiv(identifier, include_resources=False)
        paper = self.db.query(DBPaper).filter(DBPaper.id == int(resolved.id)).first()
        if paper is None:
            raise PaperNotFoundError(f"No paper found for identifier '{identifier}'")
        return paper

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

            return self.hydrate_details(
                [db_paper], include_resources=include_resources
            )[0]

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
        task: Optional[str] = None,
        method: Optional[str] = None,
        organization: Optional[str] = None,
        latest_only: bool = True,
        order_by: str = "trending",
        order_dir: str = "desc",
        time_window: str = "all_time",
        include_resources: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
        framework: Optional[str] = None,
        repository: Optional[str] = None,
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
            task: Filter by an exact task name, slug, or ID
            method: Filter by an exact method name, full name, slug, or ID
            organization: Filter by an exact organization name, slug, or ID
            latest_only: Whether to only include latest versions of papers
            order_by: Field to order by (date_published, citation_count, trending)
            order_dir: Order direction (asc, desc)
            time_window: Feed time window (today, week, month, all_time)

        Returns:
            Paginated Papers response
        """
        try:
            # Set default page size
            if page_size is None:
                page_size = self.settings.default_page_size

            # Limit page size
            page_size = min(page_size, self.settings.max_page_size)

            allowed_order_columns = {
                "date_published": DBPaper.date_published,
                "citation_count": DBPaper.citation_count,
            }
            if order_by not in {*allowed_order_columns.keys(), "trending"}:
                raise ValueError(f"Unsupported order_by: {order_by}")

            if time_window != "all_time":
                published_after = self._get_published_after_for_time_window(time_window)

            applied_filters = {
                name: value
                for name, value in {
                    "task": task,
                    "method": method,
                    "conference": conference,
                    "framework": framework,
                    "organization": organization,
                }.items()
                if value is not None
            }

            if framework is not None and repository is not None:
                raise ValueError("framework and repository are mutually exclusive")

            repository_id, scope = self._resolve_paper_feed_scope(
                framework=framework,
                repository=repository,
            )
            is_repository_feed = framework is not None or repository is not None
            task_id = self._resolve_paper_filter_entity(
                DBTask, task, "Task", DBTask.slug, DBTask.name
            )
            method_id = self._resolve_paper_filter_entity(
                DBMethod,
                method,
                "Method",
                DBMethod.slug,
                DBMethod.name,
                DBMethod.full_name,
            )
            organization_id = self._resolve_paper_filter_entity(
                DBOrganization,
                organization,
                "Organization",
                DBOrganization.slug,
                DBOrganization.name,
            )
            conference_id = self._resolve_paper_filter_entity(
                DBConference,
                conference,
                "Conference",
                DBConference.slug,
                DBConference.name,
                DBConference.short_name,
                required=False,
            )
            has_catalog_filter = any(
                value is not None
                for value in (task_id, method_id, organization_id, conference_id)
            )
            if is_repository_feed:
                latest_only = True

            # The global trending SQL intentionally deduplicates by repository.
            # Repository-scoped feeds instead retain every linked paper.
            if (
                order_by == "trending"
                and not is_repository_feed
                and not has_catalog_filter
            ):
                response = self._get_trending_papers(
                    page=page,
                    page_size=page_size,
                    search=search,
                    published_after=published_after,
                    published_before=published_before,
                    conference=conference,
                    latest_only=latest_only,
                    include_resources=include_resources,
                    has_code=has_code,
                    has_hf_artifacts=has_hf_artifacts,
                )
                response.applied_filters = applied_filters
                return response

            # Build base query
            query = self.db.query(DBPaper)

            if is_repository_feed:
                if repository_id is None:
                    return Papers(
                        count=0,
                        next_page=None,
                        previous_page=None,
                        results=[],
                        scope=scope,
                        applied_filters=applied_filters,
                    )
                query = query.join(
                    DBPaperRepository,
                    DBPaperRepository.paper_id == DBPaper.id,
                ).filter(DBPaperRepository.repository_id == repository_id)

            if task_id is not None:
                query = query.filter(DBPaper.tasks.any(DBTask.id == task_id))

            if method_id is not None:
                query = query.filter(DBPaper.methods.any(DBMethod.id == method_id))

            if organization_id is not None:
                query = query.filter(
                    DBPaper.organizations.any(DBOrganization.id == organization_id)
                )

            # Filter for latest versions only
            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            if has_code:
                query = self.apply_has_code_filter(query)

            if has_hf_artifacts:
                query = self.apply_has_hf_artifacts_filter(query)

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
                conference_filters = [DBPaper.conference.ilike(f"%{conference}%")]
                if conference_id is not None:
                    conference_filters.append(
                        DBPaper.conferences.any(DBConference.id == conference_id)
                    )
                query = query.filter(or_(*conference_filters))

            # Apply ordering
            if order_by == "trending":
                query = self.apply_scoped_trending_order(query)
            else:
                order_column = allowed_order_columns[order_by]
                if order_dir.lower() == "desc":
                    query = query.order_by(desc(order_column).nullslast())
                else:
                    query = query.order_by(asc(order_column).nullslast())

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            api_papers = self.hydrate_cards(
                db_papers, include_resources=include_resources
            )

            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size
            next_page = page + 1 if page < total_pages else None
            previous_page = page - 1 if page > 1 else None

            return Papers(
                count=total_count,
                next_page=next_page,
                previous_page=previous_page,
                results=api_papers,
                scope=scope,
                applied_filters=applied_filters,
            )

        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Error fetching papers: {str(e)}")

    def _resolve_paper_feed_scope(
        self,
        framework: Optional[str],
        repository: Optional[str],
    ) -> tuple[Optional[int], Optional[PaperFeedScope]]:
        if framework is not None:
            reference = framework.strip()
            identity_filters = [
                func.lower(DBFramework.slug) == reference.lower(),
                func.lower(DBFramework.name) == reference.lower(),
            ]
            if reference.isdigit():
                identity_filters.append(DBFramework.id == int(reference))
            row = (
                self.db.query(DBFramework, DBRepository, DBPaper)
                .outerjoin(DBRepository, DBFramework.repository_id == DBRepository.id)
                .outerjoin(DBPaper, DBFramework.introducing_paper_id == DBPaper.id)
                .filter(or_(*identity_filters))
                .first()
            )
            if not row:
                raise PaperNotFoundError(f"Framework '{framework}' not found")
            db_framework, db_repository, introducing_paper = row
            recommended_tasks = (
                self.db.query(DBTask)
                .join(DBTaskFramework, DBTaskFramework.task_id == DBTask.id)
                .filter(DBTaskFramework.framework_id == db_framework.id)
                .order_by(asc(DBTaskFramework.display_order), asc(DBTask.name))
                .all()
            )
            repository_name = self._repository_identity(db_repository)
            return db_framework.repository_id, PaperFeedScope(
                kind="framework",
                repository=repository_name,
                framework_slug=db_framework.slug,
                framework_name=db_framework.name,
                github_url=db_repository.url if db_repository else None,
                num_stars=db_repository.num_stars if db_repository else None,
                introducing_paper_arxiv_id=(
                    introducing_paper.arxiv_id if introducing_paper else None
                ),
                recommended_tasks=[
                    TaskSummary.model_validate(task) for task in recommended_tasks
                ],
            )

        if repository is None:
            return None, None

        normalized_url = normalize_github_url(repository)
        if not normalized_url and len(repository.strip("/").split("/")) == 2:
            normalized_url = normalize_github_url(f"github.com/{repository.strip('/')}")
        if not normalized_url:
            return None, PaperFeedScope(kind="repository", repository=repository)
        owner, name = parse_github_url(normalized_url)
        identity = f"{owner}/{name}" if owner and name else repository
        db_repository = (
            self.db.query(DBRepository)
            .filter(
                or_(
                    func.lower(DBRepository.url) == normalized_url,
                    and_(
                        func.lower(DBRepository.owner) == owner.lower(),
                        func.lower(DBRepository.name) == name.lower(),
                    ),
                )
            )
            .first()
        )
        return (
            db_repository.id if db_repository else None,
            PaperFeedScope(
                kind="repository",
                repository=self._repository_identity(db_repository) or identity,
                github_url=db_repository.url if db_repository else normalized_url,
            ),
        )

    def _resolve_paper_filter_entity(
        self,
        model,
        reference: Optional[str],
        label: str,
        *name_columns,
        required: bool = True,
    ) -> Optional[int]:
        """Resolve one exact paper-list taxonomy filter to its database ID."""
        if reference is None:
            return None
        value = reference.strip()
        filters = [func.lower(column) == value.lower() for column in name_columns]
        if value.isdigit():
            filters.append(model.id == int(value))
        entity = self.db.query(model).filter(or_(*filters)).first()
        if not entity:
            if required:
                raise PaperNotFoundError(f"{label} '{reference}' not found")
            return None
        return int(entity.id)

    @staticmethod
    def _repository_identity(repository: Optional[DBRepository]) -> Optional[str]:
        if not repository:
            return None
        if repository.owner and repository.name:
            return f"{repository.owner}/{repository.name}"
        normalized_url = normalize_github_url(repository.url)
        if not normalized_url:
            return None
        owner, name = parse_github_url(normalized_url)
        return f"{owner}/{name}" if owner and name else None

    _REPOSITORY_TRENDING_SQL = text("""
        WITH ranked_trending_papers AS (
            SELECT
                tp.paper_id,
                tp.arxiv_id,
                tp.title,
                tp.date_published,
                tp.repository_id,
                tp.repository_url,
                tp.owner,
                tp.repo_name,
                tp.current_stars,
                COALESCE(tp.velocity_24h, 0) as velocity_24h,
                COALESCE(tp.trending_score, 0) as trending_score,
                COALESCE(tp.stars_gained_24h, 0) as stars_gained_24h,
                tp.paper_age_days,
                tp.abstract,
                p.source,
                p.source_url,
                p.thumbnail_url,
                p.version,
                ROW_NUMBER() OVER (
                    PARTITION BY tp.paper_id
                    ORDER BY tp.trending_score DESC NULLS LAST, tp.current_stars DESC
                ) as paper_repo_rank
            FROM trending_papers_24h tp
            JOIN papers p ON p.id = tp.paper_id
            WHERE tp.paper_age_days <= :max_age_days
            AND (:min_velocity IS NULL OR COALESCE(tp.velocity_24h, 0) >= :min_velocity)
        ),
        unique_repo_per_paper AS (
            SELECT *
            FROM ranked_trending_papers
            WHERE paper_repo_rank = 1
        ),
        ranked_by_repo AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY repository_id
                    ORDER BY date_published DESC NULLS LAST, paper_id DESC
                ) as repo_paper_rank
            FROM unique_repo_per_paper
        )
        SELECT
            paper_id,
            arxiv_id,
            title,
            date_published,
            repository_id,
            repository_url,
            owner,
            repo_name,
            current_stars,
            velocity_24h,
            trending_score,
            stars_gained_24h,
            paper_age_days,
            abstract,
            source,
            source_url,
            thumbnail_url,
            version
        FROM ranked_by_repo
        WHERE repo_paper_rank = 1
        ORDER BY trending_score DESC NULLS LAST, current_stars DESC
        LIMIT :limit
    """)

    _REPOSITORY_TRENDING_TASKS_SQL = text("""
        SELECT pt.paper_id, t.name, t.slug
        FROM paper_tasks pt
        JOIN tasks t ON pt.task_id = t.id
        WHERE pt.paper_id = ANY(:paper_ids)
        ORDER BY pt.paper_id, t.name
    """)

    _REPOSITORY_TRENDING_AUTHORS_SQL = text("""
        SELECT pa.paper_id, a.name
        FROM paper_authors pa
        JOIN authors a ON pa.author_id = a.id
        WHERE pa.paper_id = ANY(:paper_ids)
        ORDER BY pa.paper_id, pa.author_order
    """)

    def get_repository_trending_papers(
        self,
        limit: int = 20,
        max_age_days: int = 180,
        min_velocity: Optional[float] = None,
    ) -> list[RepositoryTrendingPaper]:
        """Return the repository-velocity trending projection.

        This is intentionally distinct from the paginated paper feed's
        configurable trending ranking. It reads ``trending_papers_24h``, keeps
        the best repository per paper, then keeps the newest paper per
        repository before loading only the authors and tasks rendered by this
        endpoint.
        """
        try:
            rows = self.db.execute(
                self._REPOSITORY_TRENDING_SQL,
                {
                    "limit": limit,
                    "max_age_days": max_age_days,
                    "min_velocity": min_velocity,
                },
            ).fetchall()
            paper_ids = [row[0] for row in rows]

            tasks_by_paper: dict[Any, list[RepositoryTrendingTask]] = {}
            authors_by_paper: dict[Any, list[str]] = {}
            if paper_ids:
                task_rows = self.db.execute(
                    self._REPOSITORY_TRENDING_TASKS_SQL,
                    {"paper_ids": paper_ids},
                ).fetchall()
                for paper_id, name, slug in task_rows:
                    tasks_by_paper.setdefault(paper_id, []).append(
                        RepositoryTrendingTask(name=name, slug=slug)
                    )

                author_rows = self.db.execute(
                    self._REPOSITORY_TRENDING_AUTHORS_SQL,
                    {"paper_ids": paper_ids},
                ).fetchall()
                for paper_id, name in author_rows:
                    authors_by_paper.setdefault(paper_id, []).append(name)

            return [
                self._to_repository_trending_paper(
                    row,
                    authors=authors_by_paper.get(row[0], []),
                    tasks=tasks_by_paper.get(row[0], []),
                )
                for row in rows
            ]
        except DatabaseError:
            raise
        except Exception as error:
            raise DatabaseError(str(error)) from error

    def _to_repository_trending_paper(
        self,
        row,
        *,
        authors: list[str],
        tasks: list[RepositoryTrendingTask],
    ) -> RepositoryTrendingPaper:
        paper_id = row[0]
        arxiv_id = row[1]
        source = row[14]
        thumbnail_url = self._resolve_repository_trending_thumbnail_url(
            paper_id=paper_id,
            arxiv_id=arxiv_id,
            source=source,
            explicit_thumbnail_url=row[16],
            version=row[17],
        )
        return RepositoryTrendingPaper(
            paper_id=str(paper_id),
            arxiv_id=arxiv_id,
            source=source,
            source_url=row[15],
            title=row[2],
            abstract=row[13],
            authors=authors,
            date_published=row[3],
            thumbnail_url=thumbnail_url,
            tasks=tasks,
            repository=RepositoryTrendingRepository(
                id=str(row[4]),
                url=row[5],
                owner=row[6],
                name=row[7],
                num_stars=row[8],
            ),
            trending=RepositoryTrendingScore(
                velocity_24h=float(row[9]) if row[9] else 0.0,
                trending_score=float(row[10]) if row[10] else 0.0,
                stars_gained_24h=int(row[11]) if row[11] else 0,
            ),
            paper_age_days=float(row[12]) if row[12] else 0.0,
        )

    def _resolve_repository_trending_thumbnail_url(
        self,
        *,
        paper_id: int,
        arxiv_id: Optional[str],
        source: str,
        explicit_thumbnail_url: Optional[str],
        version: Optional[str],
    ) -> Optional[str]:
        """Preserve the repository-trending endpoint's thumbnail policy."""
        if explicit_thumbnail_url is not None:
            return explicit_thumbnail_url
        if source == "arxiv" and arxiv_id:
            return build_thumbnail_url(
                build_thumbnail_filename(arxiv_id, version or "v1")
            )
        if source == "external":
            return self._get_thumbnail_service().get_external_thumbnail_url(paper_id)
        return None

    # GitHub-only ranking (default + rollback path): rank papers by the EMA
    # star velocity of their best official repository. Two-step dedup: pick the
    # best official repo per paper, then keep one paper per repo (most recently
    # published) so the feed never shows duplicate repo cards.
    _TRENDING_SQL_GITHUB = text("""
        WITH paper_trending AS (
            SELECT DISTINCT ON (p.id)
                p.id as paper_id,
                p.date_published,
                r.id as repository_id,
                r.trending_score,
                r.num_stars
            FROM papers p
            LEFT JOIN paper_repositories pr
                ON p.id = pr.paper_id
                AND pr.is_official = TRUE
            LEFT JOIN repositories r
                ON pr.repository_id = r.id
                AND r.trending_score IS NOT NULL
                AND r.trending_score_updated_at >= (NOW() - INTERVAL '24 hours')
            WHERE (:search_term IS NOT NULL OR r.id IS NOT NULL)
                AND (:search_term IS NULL OR p.title ILIKE :search_term OR p.abstract ILIKE :search_term)
                AND (:published_after IS NULL OR p.date_published >= :published_after)
                AND (:published_before IS NULL OR p.date_published <= :published_before)
                AND (:conference IS NULL OR p.conference ILIKE :conference)
                AND (:latest_only = FALSE OR p.is_latest_version = TRUE)
                AND (:has_code = FALSE OR EXISTS (
                    SELECT 1 FROM paper_repositories code_pr
                    WHERE code_pr.paper_id = p.id
                ))
                AND (:has_hf_artifacts = FALSE OR EXISTS (
                    SELECT 1 FROM paper_hf_artifacts artifact_link
                    WHERE artifact_link.paper_id = p.id
                ))
            ORDER BY p.id, r.trending_score DESC NULLS LAST, r.num_stars DESC NULLS LAST
        ),
        ranked_by_repo AS (
            SELECT
                paper_id,
                trending_score,
                num_stars,
                ROW_NUMBER() OVER (
                    PARTITION BY repository_id
                    ORDER BY date_published DESC NULLS LAST, paper_id DESC
                ) as repo_paper_rank
            FROM paper_trending
        )
        SELECT
            paper_id,
            COUNT(*) OVER() as total_count
        FROM ranked_by_repo
        WHERE repo_paper_rank = 1
        ORDER BY trending_score DESC NULLS LAST, num_stars DESC
        LIMIT :limit OFFSET :offset
    """)

    # Composite ranking: rank papers by papers.trending_score (GitHub velocity +
    # Hugging Face artifact trending) computed by the calculate_paper_trending_scores
    # cron. Papers with HF-only signal have a NULL repository_id and are NOT deduped
    # together (the `repository_id IS NULL` branch keeps every one of them); papers
    # sharing the same official repo are still deduped to the most recent paper.
    _TRENDING_SQL_COMPOSITE = text("""
        WITH paper_pool AS (
            SELECT DISTINCT ON (p.id)
                p.id as paper_id,
                p.date_published,
                p.trending_score,
                r.id as repository_id,
                r.num_stars
            FROM papers p
            LEFT JOIN paper_repositories pr
                ON p.id = pr.paper_id
                AND pr.is_official = TRUE
            LEFT JOIN repositories r
                ON pr.repository_id = r.id
            WHERE p.trending_score IS NOT NULL
                AND p.trending_score_updated_at >= (NOW() - INTERVAL '24 hours')
                AND (:search_term IS NULL OR p.title ILIKE :search_term OR p.abstract ILIKE :search_term)
                AND (:published_after IS NULL OR p.date_published >= :published_after)
                AND (:published_before IS NULL OR p.date_published <= :published_before)
                AND (:conference IS NULL OR p.conference ILIKE :conference)
                AND (:latest_only = FALSE OR p.is_latest_version = TRUE)
                AND (:has_code = FALSE OR EXISTS (
                    SELECT 1 FROM paper_repositories code_pr
                    WHERE code_pr.paper_id = p.id
                ))
                AND (:has_hf_artifacts = FALSE OR EXISTS (
                    SELECT 1 FROM paper_hf_artifacts artifact_link
                    WHERE artifact_link.paper_id = p.id
                ))
            ORDER BY p.id, r.num_stars DESC NULLS LAST
        ),
        ranked_by_repo AS (
            SELECT
                paper_id,
                trending_score,
                num_stars,
                repository_id,
                ROW_NUMBER() OVER (
                    PARTITION BY repository_id
                    ORDER BY date_published DESC NULLS LAST, paper_id DESC
                ) as repo_paper_rank
            FROM paper_pool
        )
        SELECT
            paper_id,
            COUNT(*) OVER() as total_count
        FROM ranked_by_repo
        WHERE repository_id IS NULL OR repo_paper_rank = 1
        ORDER BY trending_score DESC NULLS LAST, num_stars DESC NULLS LAST, paper_id DESC
        LIMIT :limit OFFSET :offset
    """)

    def _build_trending_query(
        self,
        mode: str,
        search: Optional[str],
        published_after: Optional[str],
        published_before: Optional[str],
        conference: Optional[str],
        latest_only: bool,
        page: int,
        page_size: int,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ):
        """Return ``(sql, params)`` for the requested trending ranking mode.

        ``mode`` is the configured ``PWC_TRENDING_RANKING_MODE``. Anything other
        than ``"composite"`` falls back to the GitHub-only ranking, so an unset
        or invalid value keeps the current (safe) behavior.
        """
        sql = (
            self._TRENDING_SQL_COMPOSITE
            if mode == "composite"
            else self._TRENDING_SQL_GITHUB
        )
        params = {
            "search_term": f"%{search}%" if search else None,
            "published_after": published_after,
            "published_before": published_before,
            "conference": f"%{conference}%" if conference else None,
            "latest_only": latest_only,
            "has_code": has_code,
            "has_hf_artifacts": has_hf_artifacts,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        }
        return sql, params

    def _get_trending_papers(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
        conference: Optional[str] = None,
        latest_only: bool = True,
        include_resources: bool = False,
        has_code: bool = False,
        has_hf_artifacts: bool = False,
    ) -> Papers:
        """
        Get papers sorted by trending score.

        The ranking depends on ``PWC_TRENDING_RANKING_MODE``:
        - ``github`` (default/rollback): EMA star velocity of the paper's best
          official repository (``repositories.trending_score``).
        - ``composite``: the paper-level composite score (GitHub velocity +
          Hugging Face artifact trending) computed by the
          ``calculate_paper_trending_scores`` cron (``papers.trending_score``).

        Args:
            Same as get_papers()

        Returns:
            Paginated Papers response sorted by the active trending score
        """
        try:
            sql_query, query_params = self._build_trending_query(
                mode=self.settings.trending_ranking_mode,
                search=search,
                published_after=published_after,
                published_before=published_before,
                conference=conference,
                latest_only=latest_only,
                has_code=has_code,
                has_hf_artifacts=has_hf_artifacts,
                page=page,
                page_size=page_size,
            )

            # Execute the query to get paper IDs
            result = self.db.execute(sql_query, query_params).fetchall()

            if not result:
                # No trending data available yet
                return Papers(
                    count=0,
                    next_page=None,
                    previous_page=None,
                    results=[],
                )

            # Extract paper IDs and total count
            paper_ids = [row[0] for row in result]
            total_count = result[0][1] if result else 0

            papers_by_id = {
                paper.id: paper
                for paper in self.db.query(DBPaper)
                .filter(DBPaper.id.in_(paper_ids))
                .all()
            }
            db_papers = [
                papers_by_id[paper_id]
                for paper_id in paper_ids
                if paper_id in papers_by_id
            ]

            api_papers = self.hydrate_cards(
                db_papers, include_resources=include_resources
            )

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
            raise DatabaseError(f"Error fetching trending papers: {str(e)}")

    def apply_scoped_trending_order(self, query):
        """Order an existing ``DBPaper`` query by the active trending metric.

        This is the shared ranking used by scoped paper feeds (task, method,
        conference, and organization pages) so they match the home feed. The
        ranking mirrors ``PWC_TRENDING_RANKING_MODE``:

        - ``composite``: rank by the paper-level composite score
          (``papers.trending_score``), the GitHub velocity + Hugging Face
          artifact blend computed by ``calculate_paper_trending_scores``.
        - otherwise (``github``, the rollback path): rank by the best official
          repository's EMA star velocity (``repositories.trending_score``).

        Scores older than 24h are treated as missing, matching the home feed's
        freshness window. Papers without a fresh score remain in the result set
        but sort after scored papers (via the ``-1`` fallbacks), so scoped pages
        never drop tagged papers. ``query`` must select ``DBPaper`` rows.
        """
        repo_stats, active_score = active_paper_score_components(
            self.db,
            self.settings.trending_ranking_mode,
            missing_score=-1.0,
        )

        query = query.outerjoin(repo_stats, repo_stats.c.paper_id == DBPaper.id)

        if self.settings.trending_ranking_mode == "composite":
            return query.order_by(
                desc(active_score),
                desc(func.coalesce(repo_stats.c.max_stars, -1)),
                desc(DBPaper.date_published),
                desc(DBPaper.id),
            )

        return query.order_by(
            desc(active_score),
            desc(func.coalesce(repo_stats.c.max_stars, -1)),
            desc(DBPaper.date_published),
            desc(DBPaper.id),
        )

    @staticmethod
    def apply_has_code_filter(query):
        """Keep papers with at least one linked GitHub repository."""
        return query.filter(DBPaper.repositories.any())

    @staticmethod
    def apply_has_hf_artifacts_filter(query):
        """Keep papers with at least one linked Hugging Face artifact."""
        return query.filter(DBPaper.hf_artifacts.any())

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

    def _retrieval_service(self) -> PaperRetrievalService:
        return PaperRetrievalService(
            self.db,
            settings=self.settings,
            summary_factory=self._convert_db_paper_to_summary,
            paper_resolver=self._resolve_db_paper_by_id_or_arxiv,
        )

    def search_papers(
        self, query: str, limit: int = 10, mode: str | None = None
    ) -> List[PaperSummary]:
        return self._retrieval_service().search_papers(query, limit, mode=mode)

    def search_papers_page(
        self,
        query: str,
        page: int = 1,
        page_size: int = 10,
        mode: str | None = None,
    ) -> PaperSearchResults:
        return self._retrieval_service().search_papers_page(
            query, page, page_size, mode=mode
        )

    def get_related_papers(
        self, paper_identifier: str, limit: int = 4
    ) -> list[RelatedPaperRecommendation]:
        return self._retrieval_service().get_related_papers(paper_identifier, limit)

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
        return await PaperCitationRefreshService(self.db).update_citation_counts(limit)

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

    async def refresh_arxiv_paper(self, arxiv_id: str) -> ArxivPaperRefreshResult:
        service = PaperVersionRefreshService(
            self.db,
            paper_factory=lambda paper_id: self.get_paper_by_id(
                paper_id, include_resources=True
            ),
        )
        return await service.refresh_arxiv_paper(arxiv_id)

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

    def get_papers_needing_citation_update_count(self, threshold_days: int = 7) -> int:
        return PaperCitationRefreshService(self.db).count_pending(threshold_days)

    def get_papers_needing_citation_update_chunk(
        self, offset: int, limit: int, threshold_days: int = 7
    ) -> List[Dict[str, Any]]:
        return PaperCitationRefreshService(self.db).pending_chunk(
            offset, limit, threshold_days
        )

    def update_citation_counts_batch(
        self, citation_updates: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        return PaperCitationRefreshService(self.db).update_batch(citation_updates)

    def get_citation_statistics(self) -> Dict[str, Any]:
        return PaperCitationRefreshService(self.db).statistics()

    def update_paper_tasks(
        self, paper_id: int, task_ids: List[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        return PaperAssociationService(self.db, self.get_paper_by_id).update_tasks(
            paper_id, task_ids, commit=commit
        )

    def update_paper_organizations(
        self,
        paper_id: int,
        organization_ids: List[int],
        *,
        manual_added_by_hf_subject: Optional[str] = None,
        manual_added_by_hf_username: Optional[str] = None,
        commit: bool = True,
    ) -> Paper | DBPaper:
        return PaperAssociationService(
            self.db, self.get_paper_by_id
        ).update_organizations(
            paper_id,
            organization_ids,
            manual_added_by_hf_subject=manual_added_by_hf_subject,
            manual_added_by_hf_username=manual_added_by_hf_username,
            commit=commit,
        )

    def update_paper_methods(
        self, paper_id: int, method_ids: List[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        return PaperAssociationService(self.db, self.get_paper_by_id).update_methods(
            paper_id, method_ids, commit=commit
        )

    def update_paper_repositories(
        self,
        paper_id: int,
        repositories: List[Dict[str, Any]],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        return PaperAssociationService(
            self.db, self.get_paper_by_id
        ).update_repositories(paper_id, repositories, commit=commit)

    def update_paper_project_pages(
        self,
        paper_id: int,
        project_pages: List[Dict[str, Any]],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        return PaperAssociationService(
            self.db, self.get_paper_by_id
        ).update_project_pages(paper_id, project_pages, commit=commit)

    def update_paper_source_url(
        self, paper_id: int, source_url: str, *, commit: bool = True
    ) -> Paper | DBPaper:
        return PaperAssociationService(self.db, self.get_paper_by_id).update_source_url(
            paper_id, source_url, commit=commit
        )

    def update_paper_hf_artifacts(
        self,
        paper_id: int,
        hf_models: List[str],
        hf_datasets: List[str],
        hf_spaces: List[str],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        return PaperAssociationService(
            self.db, self.get_paper_by_id
        ).update_hf_artifacts(
            paper_id,
            hf_models,
            hf_datasets,
            hf_spaces,
            commit=commit,
        )
