"""
User-scoped bookmark endpoints.

All endpoints below require a valid ``pwc_session`` cookie and a user-granted
Hugging Face Bucket credential. Bookmarks are stored in a private Bucket owned
by the user; ``user_bookmarks`` is read only as a one-time migration source.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.database.connection import get_database_session
from backend.models.api import Paper as ApiPaper
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    UserBookmark,
)
from backend.services.hf_inference_billing_service import decrypt_oauth_credential
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    PaperBucketError,
)
from backend.services.paper_service import PaperService
from backend.services.saved_papers_bucket_service import (
    SavedPaperRef,
    SavedPapersBucket,
)
from backend.utils.auth import require_user

router = APIRouter(prefix="/me", tags=["bookmarks"])


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class BookmarkIdsResponse(BaseModel):
    paper_ids: List[int] = Field(
        default_factory=list,
        description="IDs of papers bookmarked by the current user",
    )


class SavedTaskGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(
        None, description="Task ID, NULL for the 'Untagged' bucket"
    )
    slug: Optional[str] = Field(
        None, description="Task slug, NULL for the 'Untagged' bucket"
    )
    name: str = Field(..., description="Task display name")
    papers: List[ApiPaper] = Field(default_factory=list)


class SavedAreaGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = Field(None, description="Area ID, NULL for the 'Other' bucket")
    name: str = Field(..., description="Area display name")
    tasks: List[SavedTaskGroup] = Field(default_factory=list)


class SavedPapersResponse(BaseModel):
    count: int = Field(..., description="Total number of bookmarked papers")
    areas: List[SavedAreaGroup] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _bucket_error(error: PaperBucketError) -> HTTPException:
    if error.authorization_required:
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "saved_papers_bucket_authorization_required",
                "message": str(error),
            },
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))


def _bucket_store(request: Request, user: dict, db: Session) -> SavedPapersBucket:
    encrypted = request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME)
    credential = (
        decrypt_oauth_credential(encrypted, user["hf_user_id"], get_settings())
        if encrypted
        else None
    )
    if credential is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "saved_papers_bucket_authorization_required",
                "message": (
                    "Authorize Papers With Code to manage your saved-papers Bucket."
                ),
            },
        )

    store = SavedPapersBucket(token=credential.token, username=user["username"])

    def load_legacy() -> list[SavedPaperRef]:
        legacy_rows = (
            db.query(
                UserBookmark.paper_id,
                UserBookmark.created_at,
                DBPaper.title,
                DBPaper.arxiv_id,
                DBPaper.source_url,
            )
            .join(DBPaper, DBPaper.id == UserBookmark.paper_id)
            .filter(UserBookmark.hf_username == user["username"])
            .order_by(desc(UserBookmark.created_at))
            .all()
        )
        return [
            SavedPaperRef(
                paper_id=int(row[0]),
                saved_at=row[1],
                title=row[2],
                arxiv_id=row[3],
                source_url=row[4],
            )
            for row in legacy_rows
        ]

    try:
        store.initialize(load_legacy)
    except PaperBucketError as error:
        raise _bucket_error(error) from error
    return store


def _bookmark_refs(request: Request, user: dict, db: Session) -> list[SavedPaperRef]:
    store = _bucket_store(request, user, db)
    try:
        return store.list()
    except PaperBucketError as error:
        raise _bucket_error(error) from error


@router.get(
    "/bookmarks/ids",
    response_model=BookmarkIdsResponse,
    summary="List the current user's bookmarked paper IDs",
)
def get_my_bookmark_ids(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> BookmarkIdsResponse:
    """Return just the IDs (cheap; used to hydrate the Save button state)."""

    refs = _bookmark_refs(request, user, db)
    return BookmarkIdsResponse(paper_ids=[item.paper_id for item in refs])


@router.get(
    "/bookmarks",
    response_model=SavedPapersResponse,
    summary="List the current user's bookmarked papers grouped by area and task",
)
def get_my_bookmarks(
    request: Request,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> SavedPapersResponse:
    """Return all bookmarks for the user, grouped by Area and then Task.

    Each paper is classified using its primary task (the row in ``paper_tasks``
    with the lowest ``task_id``). Papers without any tagged task land in a
    catch-all ``Other / Untagged`` bucket.
    """

    bookmark_refs = _bookmark_refs(request, user, db)
    paper_ids: List[int] = [item.paper_id for item in bookmark_refs]

    if not paper_ids:
        return SavedPapersResponse(count=0, areas=[])

    db_papers = db.query(DBPaper).filter(DBPaper.id.in_(paper_ids)).all()
    paper_by_id: Dict[int, DBPaper] = {p.id: p for p in db_papers}
    # Preserve "most recently bookmarked first" ordering from `bookmark_rows`.
    ordered_papers: List[DBPaper] = [
        paper_by_id[pid] for pid in paper_ids if pid in paper_by_id
    ]

    # Resolve each paper's primary task + that task's area in a single query.
    primary_rows = db.execute(
        text(
            """
            SELECT pt.paper_id,
                   t.id   AS task_id,
                   t.slug AS task_slug,
                   t.name AS task_name,
                   a.id   AS area_id,
                   a.name AS area_name
            FROM paper_tasks pt
            JOIN tasks t ON t.id = pt.task_id
            LEFT JOIN areas a ON a.id = t.area_id
            WHERE pt.paper_id = ANY(:paper_ids)
              AND pt.task_id = (
                  SELECT MIN(pt2.task_id)
                  FROM paper_tasks pt2
                  WHERE pt2.paper_id = pt.paper_id
              )
            """
        ),
        {"paper_ids": paper_ids},
    ).fetchall()

    primary_by_paper: Dict[
        int,
        Tuple[
            Optional[int], Optional[str], Optional[str], Optional[int], Optional[str]
        ],
    ] = {
        int(row[0]): (
            int(row[1]) if row[1] is not None else None,
            row[2],
            row[3],
            int(row[4]) if row[4] is not None else None,
            row[5],
        )
        for row in primary_rows
    }

    service = PaperService(db)
    relation_data = service._get_paper_relation_data(paper_ids, include_resources=False)
    api_papers: Dict[int, ApiPaper] = {
        p.id: service._convert_db_paper_to_api(
            p, include_resources=False, relation_data=relation_data
        )
        for p in ordered_papers
    }

    # Two-level grouping: area → task → papers. We use `None` keys for the
    # catch-all buckets (paper has no task, or task has no area).
    AreaKey = Optional[int]
    TaskKey = Optional[int]

    areas: Dict[AreaKey, Dict[str, object]] = {}
    area_order: List[AreaKey] = []

    for db_paper in ordered_papers:
        primary = primary_by_paper.get(db_paper.id)
        if primary is None:
            task_id, task_slug, task_name = None, None, "Untagged"
            area_id, area_name = None, "Other"
        else:
            task_id, task_slug, task_name, area_id, area_name = primary
            if area_id is None:
                area_name = "Other"
            if task_id is None:
                task_name = "Untagged"

        if area_id not in areas:
            areas[area_id] = {
                "id": area_id,
                "name": area_name or "Other",
                "tasks": {},
                "task_order": [],
            }
            area_order.append(area_id)

        area_bucket = areas[area_id]
        tasks_dict: Dict[TaskKey, Dict[str, object]] = area_bucket["tasks"]  # type: ignore[assignment]
        task_order: List[TaskKey] = area_bucket["task_order"]  # type: ignore[assignment]

        if task_id not in tasks_dict:
            tasks_dict[task_id] = {
                "id": task_id,
                "slug": task_slug,
                "name": task_name or "Untagged",
                "papers": [],
            }
            task_order.append(task_id)

        tasks_dict[task_id]["papers"].append(api_papers[db_paper.id])  # type: ignore[index]

    # Materialise into Pydantic objects in deterministic order.
    out_areas: List[SavedAreaGroup] = []
    for area_id in area_order:
        bucket = areas[area_id]
        task_buckets: Dict[TaskKey, Dict[str, object]] = bucket["tasks"]  # type: ignore[assignment]
        task_order_list: List[TaskKey] = bucket["task_order"]  # type: ignore[assignment]
        out_areas.append(
            SavedAreaGroup(
                id=bucket["id"],  # type: ignore[arg-type]
                name=str(bucket["name"]),
                tasks=[
                    SavedTaskGroup(
                        id=task_buckets[tid]["id"],  # type: ignore[arg-type]
                        slug=task_buckets[tid]["slug"],  # type: ignore[arg-type]
                        name=str(task_buckets[tid]["name"]),
                        papers=task_buckets[tid]["papers"],  # type: ignore[arg-type]
                    )
                    for tid in task_order_list
                ],
            )
        )

    return SavedPapersResponse(count=len(api_papers), areas=out_areas)


@router.post(
    "/bookmarks/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add the given paper to the current user's bookmarks",
)
def add_bookmark(
    request: Request,
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    paper = db.query(DBPaper).filter(DBPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found"
        )

    store = _bucket_store(request, user, db)
    try:
        store.add(
            paper_id,
            title=paper.title,
            arxiv_id=paper.arxiv_id,
            source_url=paper.source_url,
        )
    except PaperBucketError as error:
        raise _bucket_error(error) from error
    return None


@router.delete(
    "/bookmarks/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the given paper from the current user's bookmarks",
)
def remove_bookmark(
    request: Request,
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    store = _bucket_store(request, user, db)
    try:
        store.remove(paper_id)
    except PaperBucketError as error:
        raise _bucket_error(error) from error
    return None
