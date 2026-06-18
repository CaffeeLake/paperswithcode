"""
Organization service for listing organizations and organization-scoped taxonomy.
"""

from typing import Optional

from sqlalchemy import and_, asc, desc, func
from sqlalchemy.orm import Session

from backend.models.api import (
    ConferenceTaskSummary,
    Organization,
    OrganizationAreaWithTasks,
    OrganizationAreasWithTasks,
    Organizations,
    Papers,
)
from backend.models.database import Area as DBArea
from backend.models.database import Organization as DBOrganization
from backend.models.database import Paper as DBPaper
from backend.models.database import PaperOrganization
from backend.models.database import PaperTask
from backend.models.database import Task as DBTask
from backend.utils.exceptions import DatabaseError, PaperNotFoundError


class OrganizationService:
    """Service layer for organization endpoints."""

    def __init__(self, db: Session):
        self.db = db

    def _get_organization_by_slug(self, slug: str) -> DBOrganization:
        organization = (
            self.db.query(DBOrganization).filter(DBOrganization.slug == slug).first()
        )
        if not organization:
            raise PaperNotFoundError(f"Organization with slug '{slug}' not found")
        return organization

    def _organization_to_api(
        self, db_org: DBOrganization, paper_count: Optional[int] = None
    ) -> Organization:
        if paper_count is None:
            paper_count = (
                self.db.query(func.count(PaperOrganization.paper_id))
                .filter(PaperOrganization.organization_id == db_org.id)
                .scalar()
                or 0
            )

        return Organization(
            id=str(db_org.id),
            name=db_org.name,
            slug=db_org.slug,
            hf_url=db_org.hf_url,
            logo_url=db_org.logo_url,
            website_url=db_org.website_url,
            github_url=db_org.github_url,
            description=db_org.description,
            paper_count=paper_count,
            created_at=db_org.created_at,
            updated_at=db_org.updated_at,
        )

    def get_organizations(self) -> Organizations:
        try:
            paper_count_col = func.count(PaperOrganization.paper_id).label(
                "paper_count"
            )
            rows = (
                self.db.query(DBOrganization, paper_count_col)
                .outerjoin(
                    PaperOrganization,
                    DBOrganization.id == PaperOrganization.organization_id,
                )
                .group_by(DBOrganization.id)
                .order_by(desc(paper_count_col), DBOrganization.name)
                .all()
            )

            results = [
                self._organization_to_api(db_org, paper_count or 0)
                for db_org, paper_count in rows
            ]
            return Organizations(count=len(results), results=results)
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organizations: {str(e)}")

    def get_organization(self, slug: str) -> Organization:
        try:
            organization = self._get_organization_by_slug(slug)
            return self._organization_to_api(organization)
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organization: {str(e)}")

    def get_organization_areas_with_tasks(
        self, slug: str
    ) -> OrganizationAreasWithTasks:
        try:
            organization = self._get_organization_by_slug(slug)

            total_paper_count = (
                self.db.query(func.count(PaperOrganization.paper_id))
                .filter(PaperOrganization.organization_id == organization.id)
                .scalar()
                or 0
            )

            area_rows = self.db.query(DBArea).order_by(DBArea.name).all()

            paper_count_col = func.count(
                func.distinct(PaperOrganization.paper_id)
            ).label("paper_count")
            task_rows = (
                self.db.query(DBTask, paper_count_col)
                .outerjoin(
                    PaperTask,
                    DBTask.id == PaperTask.task_id,
                )
                .outerjoin(
                    PaperOrganization,
                    and_(
                        PaperTask.paper_id == PaperOrganization.paper_id,
                        PaperOrganization.organization_id == organization.id,
                    ),
                )
                .filter(DBTask.is_visible)
                .group_by(DBTask.id)
                .order_by(DBTask.name)
                .all()
            )

            tasks_by_area: dict[Optional[int], list[ConferenceTaskSummary]] = {}
            for db_task, paper_count in task_rows:
                if not paper_count:
                    continue
                summary = ConferenceTaskSummary(
                    id=str(db_task.id),
                    name=db_task.name,
                    slug=db_task.slug,
                    paper_count=paper_count or 0,
                )
                tasks_by_area.setdefault(db_task.area_id, []).append(summary)

            results = [
                OrganizationAreaWithTasks(
                    id=str(area.id),
                    name=area.name,
                    description=area.description,
                    tasks=tasks_by_area.get(area.id, []),
                )
                for area in area_rows
                if tasks_by_area.get(area.id)
            ]

            return OrganizationAreasWithTasks(
                organization=self._organization_to_api(
                    organization, paper_count=total_paper_count
                ),
                total_paper_count=total_paper_count,
                results=results,
            )
        except PaperNotFoundError:
            raise
        except Exception as e:
            raise DatabaseError(
                f"Failed to retrieve organization areas with tasks: {str(e)}"
            )

    def get_organization_papers(
        self,
        slug: str,
        task_slug: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
        latest_only: bool = True,
        order_by: str = "date_published",
        order_dir: str = "desc",
        include_resources: bool = False,
    ) -> Papers:
        try:
            organization = self._get_organization_by_slug(slug)

            query = (
                self.db.query(DBPaper)
                .join(
                    PaperOrganization,
                    DBPaper.id == PaperOrganization.paper_id,
                )
                .filter(PaperOrganization.organization_id == organization.id)
            )

            if task_slug:
                task = self.db.query(DBTask).filter(DBTask.slug == task_slug).first()
                if not task:
                    raise PaperNotFoundError(f"Task with slug '{task_slug}' not found")
                query = query.join(
                    PaperTask,
                    DBPaper.id == PaperTask.paper_id,
                ).filter(PaperTask.task_id == task.id)

            if latest_only:
                query = query.filter(DBPaper.is_latest_version)

            if order_by == "trending":
                # Match the home feed: rank by the active trending metric
                # (paper-level composite score or official-repo velocity per
                # PWC_TRENDING_RANKING_MODE). Unscored papers stay in the list
                # but sort after scored papers.
                from backend.services.paper_service import PaperService

                query = PaperService(self.db).apply_scoped_trending_order(query)
            else:
                if order_by == "title":
                    order_field = DBPaper.title
                elif order_by == "citation_count":
                    order_field = DBPaper.citation_count
                else:
                    order_field = DBPaper.date_published

                if order_dir == "desc":
                    query = query.order_by(desc(order_field), desc(DBPaper.id))
                else:
                    query = query.order_by(asc(order_field), asc(DBPaper.id))

            total_count = query.count()
            offset = (page - 1) * page_size
            db_papers = query.offset(offset).limit(page_size).all()

            from backend.services.paper_service import PaperService

            paper_service = PaperService(self.db)
            relation_data = paper_service._get_paper_relation_data(
                [paper.id for paper in db_papers],
                include_resources=include_resources,
                card_view=True,
            )

            papers = [
                paper_service._convert_db_paper_to_api(
                    db_paper,
                    include_resources=include_resources,
                    relation_data=relation_data,
                )
                for db_paper in db_papers
            ]

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
        except Exception as e:
            raise DatabaseError(f"Failed to retrieve organization papers: {str(e)}")
