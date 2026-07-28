"""
Paper service for business logic and data processing.

This service handles all paper-related operations, including:
- Fetching papers with proper URL construction
- Converting database models to API models
- Handling pagination
- Managing paper versions
"""

import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, func, text, case

from backend.models.database import (
    Paper as DBPaper,
    Author as DBAuthor,
    PaperAuthor,
    Task as DBTask,
    Method as DBMethod,
    PaperTask,
    PaperMethod,
    PaperRelation as DBPaperRelation,
    Repository as DBRepository,
    PaperRepository as DBPaperRepository,
    ProjectPage as DBProjectPage,
    PaperProjectPage as DBPaperProjectPage,
    Dataset as DBDataset,
    Conference as DBConference,
    PaperConference as DBPaperConference,
    Organization as DBOrganization,
    PaperOrganization as DBPaperOrganization,
    HfArtifact as DBHfArtifact,
    PaperHfArtifact as DBPaperHfArtifact,
    Evaluation as DBEvaluation,
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
    Papers,
    PaperSummary,
    PaperSearchResults,
    RelatedPaperRecommendation,
    PaperVersion,
    PaperVersions,
    Repository,
    ProjectPage,
    TaskSummary,
    MethodSummary,
    BenchmarkSummary,
    LeaderboardRankSummary,
    RelatedPaperSummary,
    VersionComparison,
    AuthorLink,
    OrganizationSummary,
    HfArtifactSummary,
)
from backend.utils.urls import (
    get_arxiv_abs_url,
    get_method_source_url,
    get_paper_abs_url,
    get_paper_pdf_url,
    get_paper_route_identifier,
    get_paper_url,
)
from backend.utils.exceptions import PaperNotFoundError, DatabaseError
from backend.config import get_settings
from backend.services.hf_artifact_service import sync_explicit_hf_artifact_links
from backend.services.paper_retrieval_service import PaperRetrievalService
from backend.services.paper_version_refresh_service import (
    ArxivPaperRefreshResult,
    PaperVersionRefreshService,
)
from backend.services.semantic_scholar_service import SemanticScholarService


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

    @staticmethod
    def _convert_db_method_to_summary(
        method: DBMethod, source_paper: Optional[DBPaper] = None
    ) -> MethodSummary:
        return MethodSummary(
            id=str(method.id),
            name=method.name,
            slug=method.slug,
            introduced_year=method.introduced_year,
            source_paper_id=str(method.source_paper_id)
            if method.source_paper_id is not None
            else None,
            source_url=get_method_source_url(method.source_url, source_paper),
            source_title=method.source_title,
            code_snippet_url=method.code_snippet_url,
        )

    @staticmethod
    def _convert_db_paper_to_related_summary(
        related: DBPaper,
    ) -> RelatedPaperSummary:
        """
        Convert a related (predecessor/successor) paper row into the lightweight
        summary used inside the paper detail response lineage banner.
        """
        return RelatedPaperSummary(
            id=str(related.id),
            title=related.title,
            arxiv_id=related.arxiv_id,
            source=related.source,
            source_url=related.source_url,
            published=related.date_published,
            route_identifier=get_paper_route_identifier(
                related.source, related.arxiv_id, related.id
            ),
        )

    def _get_paper_relation_data(
        self,
        paper_ids: List[int],
        include_resources: bool = False,
        card_view: bool = False,
    ) -> Dict[str, Dict[int, list]]:
        """
        Load paper relationships in batches for API serialization.

        When `card_view` is True, only the relations the paper-card UI actually
        renders are loaded (authors, tasks, methods, and — when
        `include_resources` is set — repositories and project pages). The
        heavier detail-only relations (author links, introduced benchmarks,
        paper lineage, conference, organizations) are skipped to cut both SQL
        round-trips and serialized payload size for list endpoints.
        """
        unique_ids = list(dict.fromkeys(int(paper_id) for paper_id in paper_ids))
        relation_data = {
            "authors": defaultdict(list),
            "author_links": defaultdict(list),
            "tasks": defaultdict(list),
            "methods": defaultdict(list),
            "repositories": defaultdict(list),
            "project_pages": defaultdict(list),
            "introduced_benchmarks": defaultdict(list),
            "predecessor_papers": defaultdict(list),
            "successor_papers": defaultdict(list),
            "conferences": {},
            "organizations": defaultdict(list),
            "hf_artifact_counts": defaultdict(dict),
            "leaderboard_ranks": defaultdict(list),
        }

        if not unique_ids:
            return relation_data

        author_rows = (
            self.db.query(
                PaperAuthor.paper_id,
                DBAuthor.id,
                DBAuthor.name,
                DBAuthor.hf_username,
            )
            .join(DBAuthor, PaperAuthor.author_id == DBAuthor.id)
            .filter(PaperAuthor.paper_id.in_(unique_ids))
            .order_by(PaperAuthor.paper_id, PaperAuthor.author_order)
            .all()
        )
        for paper_id, author_id, author_name, hf_username in author_rows:
            relation_data["authors"][paper_id].append(author_name)
            if not card_view:
                relation_data["author_links"][paper_id].append(
                    AuthorLink(
                        id=str(author_id),
                        name=author_name,
                        hf_username=hf_username,
                    )
                )

        task_rows = (
            self.db.query(PaperTask.paper_id, DBTask)
            .join(DBTask, PaperTask.task_id == DBTask.id)
            .filter(PaperTask.paper_id.in_(unique_ids))
            .order_by(PaperTask.paper_id, DBTask.name)
            .all()
        )
        for paper_id, task in task_rows:
            relation_data["tasks"][paper_id].append(
                TaskSummary(id=str(task.id), name=task.name, slug=task.slug)
            )

        method_rows = (
            self.db.query(PaperMethod.paper_id, DBMethod)
            .join(DBMethod, PaperMethod.method_id == DBMethod.id)
            .filter(PaperMethod.paper_id.in_(unique_ids))
            .order_by(PaperMethod.paper_id, DBMethod.name)
            .all()
        )
        source_paper_ids = [
            method.source_paper_id
            for _, method in method_rows
            if method.source_paper_id is not None
        ]
        source_papers_by_id = {}
        if source_paper_ids:
            source_papers_by_id = {
                paper.id: paper
                for paper in self.db.query(DBPaper)
                .filter(DBPaper.id.in_(set(source_paper_ids)))
                .all()
            }
        for paper_id, method in method_rows:
            relation_data["methods"][paper_id].append(
                self._convert_db_method_to_summary(
                    method,
                    source_papers_by_id.get(method.source_paper_id),
                )
            )

        # Hugging Face artifact counts per paper, grouped by kind. Powers the
        # feed-card HF link, which points at the most populated category. One
        # batched aggregate query keeps round-trips at O(1) for list views.
        hf_count_rows = (
            self.db.query(
                DBPaperHfArtifact.paper_id,
                DBHfArtifact.kind,
                func.count().label("cnt"),
            )
            .join(
                DBHfArtifact,
                DBPaperHfArtifact.hf_artifact_id == DBHfArtifact.id,
            )
            .filter(DBPaperHfArtifact.paper_id.in_(unique_ids))
            .group_by(DBPaperHfArtifact.paper_id, DBHfArtifact.kind)
            .all()
        )
        for paper_id, kind, cnt in hf_count_rows:
            relation_data["hf_artifact_counts"][paper_id][kind] = int(cnt)

        # Top-3 leaderboard placements per paper, powering the SOTA/#2/#3 badges
        # on feed cards. `best_rank` is precomputed per (task, dataset, metric),
        # so this is one batched indexed query. A paper can rank on the same
        # dataset under multiple tasks/metrics; we dedupe by dataset keeping the
        # best (lowest) rank. Loaded for card views too since cards render it.
        rank_rows = (
            self.db.query(
                DBEvaluation.paper_id,
                DBEvaluation.dataset_id,
                DBEvaluation.id,
                DBEvaluation.best_rank,
                DBEvaluation.best_metric,
                DBDataset.name,
                DBDataset.slug,
                DBTask.slug,
            )
            .join(DBDataset, DBEvaluation.dataset_id == DBDataset.id)
            .join(DBTask, DBEvaluation.task_id == DBTask.id)
            .filter(
                DBEvaluation.paper_id.in_(unique_ids),
                DBEvaluation.best_rank.isnot(None),
                DBEvaluation.best_rank <= 3,
            )
            .order_by(
                DBEvaluation.paper_id,
                DBEvaluation.best_rank.asc(),
                DBDataset.name,
                DBEvaluation.id,
            )
            .all()
        )
        seen_paper_datasets: set = set()
        for (
            paper_id,
            dataset_id,
            evaluation_id,
            best_rank,
            best_metric,
            name,
            slug,
            task_slug,
        ) in rank_rows:
            key = (paper_id, dataset_id)
            if key in seen_paper_datasets:
                continue
            seen_paper_datasets.add(key)
            relation_data["leaderboard_ranks"][paper_id].append(
                LeaderboardRankSummary(
                    evaluation_id=str(evaluation_id),
                    dataset_name=name,
                    dataset_slug=slug,
                    best_rank=int(best_rank),
                    best_metric=best_metric,
                    task_slug=task_slug,
                )
            )

        # Detail-only relations. Paper cards never render introduced
        # benchmarks, lineage banners, the conference badge, or organizations,
        # so list endpoints skip these queries and payloads via `card_view`.
        if not card_view:
            introduced_dataset_rows = (
                self.db.query(DBDataset)
                .filter(DBDataset.introducing_paper_id.in_(unique_ids))
                .order_by(DBDataset.introducing_paper_id, DBDataset.name)
                .all()
            )
            for dataset in introduced_dataset_rows:
                relation_data["introduced_benchmarks"][
                    dataset.introducing_paper_id
                ].append(
                    BenchmarkSummary(
                        id=str(dataset.id),
                        name=dataset.name,
                        slug=dataset.slug,
                        full_name=dataset.full_name,
                        introduced_year=dataset.introduced_year,
                    )
                )

            # Directed paper lineage edges. For each requested paper, load
            # successors (outgoing edges where the requested paper is the
            # predecessor) and predecessors (incoming edges where the requested
            # paper is the successor). Two batched queries with eager-loaded
            # related Paper rows keep round-trips at O(1) per detail call.
            successor_rows = (
                self.db.query(DBPaperRelation.source_paper_id, DBPaper)
                .join(DBPaper, DBPaperRelation.target_paper_id == DBPaper.id)
                .filter(DBPaperRelation.source_paper_id.in_(unique_ids))
                .order_by(
                    DBPaperRelation.source_paper_id,
                    DBPaper.date_published.asc().nullslast(),
                    DBPaper.id,
                )
                .all()
            )
            for paper_id, related in successor_rows:
                relation_data["successor_papers"][paper_id].append(
                    self._convert_db_paper_to_related_summary(related)
                )

            predecessor_rows = (
                self.db.query(DBPaperRelation.target_paper_id, DBPaper)
                .join(DBPaper, DBPaperRelation.source_paper_id == DBPaper.id)
                .filter(DBPaperRelation.target_paper_id.in_(unique_ids))
                .order_by(
                    DBPaperRelation.target_paper_id,
                    DBPaper.date_published.asc().nullslast(),
                    DBPaper.id,
                )
                .all()
            )
            for paper_id, related in predecessor_rows:
                relation_data["predecessor_papers"][paper_id].append(
                    self._convert_db_paper_to_related_summary(related)
                )

            conference_rows = (
                self.db.query(DBPaperConference.paper_id, DBConference)
                .join(DBConference, DBPaperConference.conference_id == DBConference.id)
                .filter(DBPaperConference.paper_id.in_(unique_ids))
                .order_by(
                    DBPaperConference.paper_id,
                    desc(DBConference.year),
                    DBConference.name,
                )
                .all()
            )
            for paper_id, conference in conference_rows:
                if paper_id not in relation_data["conferences"]:
                    relation_data["conferences"][paper_id] = conference

            organization_rows = (
                self.db.query(DBPaperOrganization.paper_id, DBOrganization)
                .join(
                    DBOrganization,
                    DBPaperOrganization.organization_id == DBOrganization.id,
                )
                .filter(DBPaperOrganization.paper_id.in_(unique_ids))
                .order_by(DBPaperOrganization.paper_id, DBOrganization.name)
                .all()
            )
            for paper_id, organization in organization_rows:
                relation_data["organizations"][paper_id].append(
                    OrganizationSummary(
                        id=str(organization.id),
                        name=organization.name,
                        slug=organization.slug,
                        logo_url=organization.logo_url,
                    )
                )

        if include_resources:
            repository_rows = (
                self.db.query(
                    DBPaperRepository.paper_id,
                    DBPaperRepository.is_official,
                    DBRepository,
                )
                .join(
                    DBRepository,
                    DBPaperRepository.repository_id == DBRepository.id,
                )
                .filter(DBPaperRepository.paper_id.in_(unique_ids))
                .order_by(
                    DBPaperRepository.paper_id,
                    desc(DBPaperRepository.is_official),
                    desc(DBRepository.num_stars),
                )
                .all()
            )
            for paper_id, is_official, repository in repository_rows:
                relation_data["repositories"][paper_id].append(
                    Repository(
                        id=str(repository.id),
                        url=repository.url,
                        owner=repository.owner,
                        name=repository.name,
                        num_stars=repository.num_stars,
                        is_official=is_official,
                        source=repository.source,
                        trending_score=float(repository.trending_score)
                        if repository.trending_score is not None
                        else None,
                        trending_score_updated_at=repository.trending_score_updated_at,
                        created_at=repository.created_at.date()
                        if repository.created_at
                        else None,
                        updated_at=repository.updated_at.date()
                        if repository.updated_at
                        else None,
                    )
                )

            project_page_rows = (
                self.db.query(DBPaperProjectPage.paper_id, DBProjectPage)
                .join(
                    DBProjectPage,
                    DBPaperProjectPage.project_page_id == DBProjectPage.id,
                )
                .filter(DBPaperProjectPage.paper_id.in_(unique_ids))
                .order_by(DBPaperProjectPage.paper_id, desc(DBProjectPage.created_at))
                .all()
            )
            for paper_id, project_page in project_page_rows:
                relation_data["project_pages"][paper_id].append(
                    ProjectPage(
                        id=str(project_page.id),
                        url=project_page.url,
                        is_official=project_page.is_official,
                        source=project_page.source,
                        created_at=project_page.created_at.date()
                        if project_page.created_at
                        else None,
                        updated_at=project_page.updated_at.date()
                        if project_page.updated_at
                        else None,
                    )
                )

        return relation_data

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

    def _convert_db_paper_to_api(
        self,
        db_paper: DBPaper,
        include_resources: bool = False,
        relation_data: Optional[Dict[str, Dict[int, list]]] = None,
    ) -> Paper:
        """
        Convert database paper model to API paper model.

        Args:
            db_paper: Database paper instance
            include_resources: Whether to include repositories and project pages

        Returns:
            API Paper model
        """
        if relation_data is None:
            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )

        authors = relation_data["authors"].get(db_paper.id, [])
        author_links = relation_data["author_links"].get(db_paper.id, [])

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

        tasks = relation_data["tasks"].get(db_paper.id) or None
        methods = relation_data["methods"].get(db_paper.id) or None
        introduced_benchmarks = (
            relation_data["introduced_benchmarks"].get(db_paper.id) or None
        )
        predecessor_papers = (
            relation_data["predecessor_papers"].get(db_paper.id) or None
        )
        successor_papers = relation_data["successor_papers"].get(db_paper.id) or None
        organizations = relation_data["organizations"].get(db_paper.id) or None
        leaderboard_ranks = relation_data["leaderboard_ranks"].get(db_paper.id) or None
        linked_conference = relation_data["conferences"].get(db_paper.id)
        hf_artifact_summary = self._build_hf_artifact_summary(
            db_paper,
            relation_data["hf_artifact_counts"].get(db_paper.id) or {},
        )
        repositories = (
            relation_data["repositories"].get(db_paper.id) or None
            if include_resources
            else None
        )
        project_pages = (
            relation_data["project_pages"].get(db_paper.id) or None
            if include_resources
            else None
        )

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

            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )
            return self._convert_db_paper_to_api(
                db_paper,
                include_resources=include_resources,
                relation_data=relation_data,
            )

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

            relation_data = self._get_paper_relation_data(
                [db_paper.id], include_resources=include_resources
            )
            return self._convert_db_paper_to_api(
                db_paper,
                include_resources=include_resources,
                relation_data=relation_data,
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
        order_by: str = "trending",
        order_dir: str = "desc",
        time_window: str = "all_time",
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

            # Special handling for trending sort
            if order_by == "trending":
                return self._get_trending_papers(
                    page=page,
                    page_size=page_size,
                    search=search,
                    published_after=published_after,
                    published_before=published_before,
                    conference=conference,
                    latest_only=latest_only,
                    include_resources=include_resources,
                )

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
            order_column = allowed_order_columns[order_by]
            if order_dir.lower() == "desc":
                query = query.order_by(desc(order_column))
            else:
                query = query.order_by(asc(order_column))

            # Get total count
            total_count = query.count()

            # Apply pagination
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            # Paginated list endpoints render paper cards, so fetch only the
            # card relations rather than full detail-page relation sets.
            relation_data = self._get_paper_relation_data(
                [paper.id for paper in db_papers],
                include_resources=include_resources,
                card_view=True,
            )

            # Convert to API models
            api_papers = [
                self._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
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

            # The homepage feed renders paper cards, so only fetch the relations
            # the card UI needs (card_view=True) instead of the full detail-page
            # relation set (lineage, introduced benchmarks, conferences, orgs).
            relation_data = self._get_paper_relation_data(
                [paper.id for paper in db_papers],
                include_resources=include_resources,
                card_view=True,
            )

            # Convert to API models
            api_papers = [
                self._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
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
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

        # Best official-repo stats per paper: max stars (a stable tie-breaker)
        # and the freshest official repo velocity. Stale repo scores are
        # ignored via the CASE so they don't outrank fresh signals.
        repo_stats = (
            self.db.query(
                DBPaperRepository.paper_id.label("paper_id"),
                func.max(DBRepository.num_stars).label("max_stars"),
                func.max(
                    case(
                        (
                            DBRepository.trending_score_updated_at >= cutoff,
                            DBRepository.trending_score,
                        )
                    )
                ).label("repo_trending_score"),
            )
            .join(DBRepository, DBPaperRepository.repository_id == DBRepository.id)
            .filter(DBPaperRepository.is_official.is_(True))
            .group_by(DBPaperRepository.paper_id)
            .subquery()
        )

        query = query.outerjoin(repo_stats, repo_stats.c.paper_id == DBPaper.id)

        if self.settings.trending_ranking_mode == "composite":
            paper_score = func.coalesce(
                case(
                    (
                        DBPaper.trending_score_updated_at >= cutoff,
                        DBPaper.trending_score,
                    )
                ),
                -1.0,
            )
            return query.order_by(
                desc(paper_score),
                desc(func.coalesce(repo_stats.c.max_stars, -1)),
                desc(DBPaper.date_published),
                desc(DBPaper.id),
            )

        return query.order_by(
            desc(func.coalesce(repo_stats.c.repo_trending_score, -1.0)),
            desc(func.coalesce(repo_stats.c.max_stars, -1)),
            desc(DBPaper.date_published),
            desc(DBPaper.id),
        )

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
        """Return the number of papers whose citation data needs refreshing."""
        try:
            from datetime import datetime, timedelta

            threshold_date = datetime.now() - timedelta(days=threshold_days)
            return (
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
        except Exception as e:
            raise DatabaseError(
                f"Error counting papers needing citation updates: {str(e)}"
            )

    def get_papers_needing_citation_update_chunk(
        self, offset: int, limit: int, threshold_days: int = 7
    ) -> List[Dict[str, Any]]:
        """Return one priority-ordered chunk of papers needing citation updates."""
        try:
            from datetime import datetime, timedelta
            from sqlalchemy import case

            threshold_date = datetime.now() - timedelta(days=threshold_days)
            priority_order = case(
                (DBPaper.citation_updated_at.is_(None), 0),
                (DBPaper.citation_count == 0, 1),
                else_=2,
            )
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
            return [
                {
                    "id": paper.id,
                    "arxiv_id": paper.arxiv_id,
                    "title": paper.title,
                    "citation_count": paper.citation_count or 0,
                    "citation_updated_at": paper.citation_updated_at,
                    "date_published": paper.date_published,
                    "priority_type": (
                        "NEVER_UPDATED"
                        if paper.citation_updated_at is None
                        else (
                            "ZERO_CITATIONS" if paper.citation_count == 0 else "REFRESH"
                        )
                    ),
                }
                for paper in db_papers
            ]
        except Exception as e:
            raise DatabaseError(
                f"Error fetching papers chunk for citation updates: {str(e)}"
            )

    def update_citation_counts_batch(
        self, citation_updates: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """Persist a batch of Semantic Scholar citation updates."""
        try:
            stats = {"updated": 0, "failed": 0}
            for update in citation_updates:
                try:
                    db_paper = (
                        self.db.query(DBPaper)
                        .filter(DBPaper.id == update["paper_id"])
                        .first()
                    )
                    if not db_paper:
                        stats["failed"] += 1
                        continue

                    if update.get("success", True) and update.get(
                        "semantic_scholar_id"
                    ):
                        db_paper.citation_count = update["citation_count"]
                        db_paper.semantic_scholar_id = update["semantic_scholar_id"]
                        stats["updated"] += 1
                    else:
                        stats["failed"] += 1

                    db_paper.citation_updated_at = func.now()
                    db_paper.updated_at = func.now()
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
        """Return aggregate citation-refresh coverage statistics."""
        try:
            latest_papers = self.db.query(DBPaper).filter(DBPaper.is_latest_version)
            total_papers = latest_papers.count()
            papers_processed = latest_papers.filter(
                DBPaper.citation_updated_at.is_not(None)
            ).count()
            papers_with_citations = latest_papers.filter(
                DBPaper.citation_count > 0
            ).count()

            return {
                "total_papers": total_papers,
                "papers_processed": papers_processed,
                "papers_with_citations": papers_with_citations,
                "processed_percentage": round(
                    papers_processed / total_papers * 100 if total_papers else 0, 1
                ),
                "citations_percentage": round(
                    papers_with_citations / total_papers * 100 if total_papers else 0,
                    1,
                ),
            }
        except Exception as e:
            raise DatabaseError(f"Error getting citation statistics: {str(e)}")

    def update_paper_tasks(
        self, paper_id: int, task_ids: List[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        """
        Update the tasks associated with a paper.

        Args:
            paper_id: Database paper ID
            task_ids: List of task IDs to associate with the paper

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import Task as DBTask, PaperTask

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Verify all task IDs exist
            existing_tasks = self.db.query(DBTask).filter(DBTask.id.in_(task_ids)).all()
            existing_task_ids = {task.id for task in existing_tasks}
            invalid_task_ids = set(task_ids) - existing_task_ids
            if invalid_task_ids:
                raise DatabaseError(f"Invalid task IDs: {invalid_task_ids}")

            # Replace all existing paper_tasks associations with the new set.
            # An admin override always wins: every row inserted here is marked
            # source='manual' so the keyword-matcher rebuild pass won't touch it.
            self.db.query(PaperTask).filter(PaperTask.paper_id == paper_id).delete()

            for task_id in task_ids:
                paper_task = PaperTask(
                    paper_id=paper_id, task_id=task_id, source="manual"
                )
                self.db.add(paper_task)

            if not commit:
                self.db.flush()
                return db_paper
            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper tasks: {str(e)}")

    def update_paper_organizations(
        self, paper_id: int, organization_ids: List[int]
    ) -> Paper:
        """
        Update the organizations associated with a paper.

        Replaces all existing paper_organizations associations with the
        provided list. Rows inserted here are marked source='manual'.

        Args:
            paper_id: Database paper ID
            organization_ids: List of organization IDs to associate

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            existing_orgs = (
                self.db.query(DBOrganization)
                .filter(DBOrganization.id.in_(organization_ids))
                .all()
            )
            existing_org_ids = {org.id for org in existing_orgs}
            invalid_org_ids = set(organization_ids) - existing_org_ids
            if invalid_org_ids:
                raise DatabaseError(f"Invalid organization IDs: {invalid_org_ids}")

            self.db.query(DBPaperOrganization).filter(
                DBPaperOrganization.paper_id == paper_id
            ).delete()

            for organization_id in organization_ids:
                self.db.add(
                    DBPaperOrganization(
                        paper_id=paper_id,
                        organization_id=organization_id,
                        source="manual",
                    )
                )

            self.db.commit()

            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper organizations: {str(e)}")

    def update_paper_methods(
        self, paper_id: int, method_ids: List[int], *, commit: bool = True
    ) -> Paper | DBPaper:
        """
        Update the methods associated with a paper.

        Args:
            paper_id: Database paper ID
            method_ids: List of method IDs to associate with the paper

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import Method as DBMethod, PaperMethod

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Verify all method IDs exist
            existing_methods = (
                self.db.query(DBMethod).filter(DBMethod.id.in_(method_ids)).all()
            )
            existing_method_ids = {method.id for method in existing_methods}
            invalid_method_ids = set(method_ids) - existing_method_ids
            if invalid_method_ids:
                raise DatabaseError(f"Invalid method IDs: {invalid_method_ids}")

            # Delete existing paper_methods associations
            self.db.query(PaperMethod).filter(PaperMethod.paper_id == paper_id).delete()

            # Add new associations
            for method_id in method_ids:
                paper_method = PaperMethod(paper_id=paper_id, method_id=method_id)
                self.db.add(paper_method)

            if not commit:
                self.db.flush()
                return db_paper
            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper methods: {str(e)}")

    def update_paper_repositories(
        self,
        paper_id: int,
        repositories: List[Dict[str, Any]],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        """
        Update the repositories associated with a paper.

        Creates repositories if they don't exist, and establishes the paper-repository
        associations with the is_official flag.

        Args:
            paper_id: Database paper ID
            repositories: List of dicts with 'url' and 'is_official' keys

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import (
                Repository as DBRepository,
                PaperRepository,
            )
            import re

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Delete existing paper_repositories associations
            self.db.query(PaperRepository).filter(
                PaperRepository.paper_id == paper_id
            ).delete()

            from backend.services.repository_service import find_repository_by_url
            from backend.utils.github_utils import (
                normalize_github_url,
                parse_github_url,
            )

            # Resolve URLs to repository rows, then dedupe by repository_id.
            # Legacy data may list the same GitHub repo twice (e.g. base URL and
            # a /tree/... subpath); find_repository_by_url collapses both to one
            # row, so we must not insert duplicate paper_repositories keys.
            associations: dict[int, bool] = {}
            for repo_data in repositories:
                url = repo_data.get("url", "").strip()
                is_official = repo_data.get("is_official", False)

                if not url:
                    continue

                normalized = normalize_github_url(url)
                if normalized:
                    url = normalized

                existing_repo = find_repository_by_url(self.db, url)

                if existing_repo:
                    # find_repository_by_url matches case-insensitively; do not
                    # rewrite url here — another row may already own the
                    # normalized lowercase form (repositories.url is unique).
                    repository_id = existing_repo.id
                else:
                    owner, name = parse_github_url(url) if normalized else (None, None)
                    if not owner or not name:
                        github_match = re.match(
                            r"https?://github\.com/([^/]+)/([^/]+)(?:/.*)?", url
                        )
                        if github_match:
                            owner = github_match.group(1)
                            name = github_match.group(2)
                            if name.endswith(".git"):
                                name = name[:-4]

                    new_repo = DBRepository(
                        url=url,
                        owner=owner,
                        name=name,
                        num_stars=0,
                        source="manual",
                    )
                    self.db.add(new_repo)
                    self.db.flush()
                    repository_id = new_repo.id

                if repository_id in associations:
                    associations[repository_id] = (
                        associations[repository_id] or is_official
                    )
                else:
                    associations[repository_id] = is_official

            # A lone repository is the paper page's canonical code link by
            # default. This intentionally favors outreach coverage over strict
            # provenance when no competing repository is present.
            if len(associations) == 1:
                only_repository_id = next(iter(associations))
                associations[only_repository_id] = True

            for repository_id, is_official in associations.items():
                paper_repository = PaperRepository(
                    paper_id=paper_id,
                    repository_id=repository_id,
                    is_official=is_official,
                )
                self.db.add(paper_repository)

            if not commit:
                self.db.flush()
                return db_paper
            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper repositories: {str(e)}")

    def update_paper_project_pages(
        self,
        paper_id: int,
        project_pages: List[Dict[str, Any]],
        *,
        commit: bool = True,
    ) -> Paper | DBPaper:
        """
        Update the project pages associated with a paper.

        Creates project pages if they don't exist, and establishes the paper-project page
        associations.

        Args:
            paper_id: Database paper ID
            project_pages: List of dicts with 'url' and 'is_official' keys

        Returns:
            Updated Paper object

        Raises:
            PaperNotFoundError: If paper is not found
            DatabaseError: If update fails
        """
        try:
            from backend.models.database import (
                ProjectPage as DBProjectPage,
                PaperProjectPage as DBPaperProjectPage,
            )

            # Verify paper exists
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            # Delete existing paper_project_pages associations
            self.db.query(DBPaperProjectPage).filter(
                DBPaperProjectPage.paper_id == paper_id
            ).delete()

            # Process each project page URL
            for page_data in project_pages:
                url = page_data.get("url", "").strip()
                is_official = page_data.get("is_official", False)

                if not url:
                    continue

                # Check if project page already exists
                existing_page = (
                    self.db.query(DBProjectPage)
                    .filter(DBProjectPage.url == url)
                    .first()
                )

                if existing_page:
                    # Use existing project page, update is_official if needed
                    if is_official and not existing_page.is_official:
                        existing_page.is_official = True
                    project_page_id = existing_page.id
                else:
                    # Create new project page
                    new_page = DBProjectPage(
                        url=url,
                        is_official=is_official,
                        source="manual",  # Marked as manually added by admin
                    )
                    self.db.add(new_page)
                    self.db.flush()  # Get the ID without committing
                    project_page_id = new_page.id

                # Create paper-project page association
                paper_project_page = DBPaperProjectPage(
                    paper_id=paper_id,
                    project_page_id=project_page_id,
                )
                self.db.add(paper_project_page)

            if not commit:
                self.db.flush()
                return db_paper
            self.db.commit()

            # Return updated paper
            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper project pages: {str(e)}")

    def update_paper_source_url(self, paper_id: int, source_url: str) -> Paper:
        """
        Update the canonical source URL of an external paper.

        Only valid for rows where ``source = 'external'``: ArXiv rows derive
        their abstract URL from ``arxiv_id`` and must not have ``source_url``
        rewritten. Raises :class:`DatabaseError` if another external row
        already owns the new URL (the partial-unique constraint
        ``uq_papers_source_url_external`` would otherwise raise a less
        readable ``IntegrityError``).
        """
        try:
            normalized = (source_url or "").strip()
            if not normalized:
                raise DatabaseError("source_url must be a non-empty string")
            if len(normalized) > 2000:
                raise DatabaseError("source_url must be at most 2000 characters")

            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            if db_paper.source != "external":
                raise DatabaseError(
                    "source_url can only be edited on external papers; "
                    "ArXiv rows derive their URL from arxiv_id"
                )

            if normalized == db_paper.source_url:
                return self.get_paper_by_id(paper_id, include_resources=True)

            collision = (
                self.db.query(DBPaper.id)
                .filter(
                    DBPaper.source == "external",
                    DBPaper.source_url == normalized,
                    DBPaper.id != paper_id,
                )
                .first()
            )
            if collision is not None:
                raise DatabaseError(
                    f"Another external paper already uses source_url={normalized!r}"
                )

            db_paper.source_url = normalized
            self.db.commit()

            return self.get_paper_by_id(paper_id, include_resources=True)

        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper source URL: {str(e)}")

    def update_paper_hf_artifacts(
        self,
        paper_id: int,
        hf_models: List[str],
        hf_datasets: List[str],
        hf_spaces: List[str],
    ) -> Paper:
        """Replace explicit Hugging Face artifact URLs linked to a paper."""
        from backend.utils.hf_utils import normalize_hf_artifact_payload

        try:
            db_paper = self.db.query(DBPaper).filter(DBPaper.id == paper_id).first()
            if not db_paper:
                raise PaperNotFoundError(f"Paper with ID {paper_id} not found")

            models, datasets, spaces = normalize_hf_artifact_payload(
                hf_models, hf_datasets, hf_spaces
            )
            db_paper.hf_models = models or None
            db_paper.hf_datasets = datasets or None
            db_paper.hf_spaces = spaces or None
            sync_explicit_hf_artifact_links(
                self.db,
                db_paper.id,
                db_paper.hf_models,
                db_paper.hf_datasets,
                db_paper.hf_spaces,
            )
            # Explicit URL edits must invalidate the discovery checkpoint so
            # the cron can reconcile removed links and arXiv-discovered extras.
            db_paper.hf_artifacts_scanned_at = None
            self.db.commit()

            return self.get_paper_by_id(paper_id, include_resources=True)

        except ValueError as e:
            self.db.rollback()
            raise DatabaseError(str(e))
        except Exception as e:
            self.db.rollback()
            if isinstance(e, (PaperNotFoundError, DatabaseError)):
                raise
            raise DatabaseError(f"Error updating paper HF artifacts: {str(e)}")
