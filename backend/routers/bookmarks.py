"""
User-scoped bookmark endpoints.

All endpoints below require a valid ``pwc_session`` cookie (HF OAuth) and
operate on rows in the ``user_bookmarks`` table keyed on the lowercased HF
username carried in the session JWT.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Path, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, text
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import Paper as ApiPaper
from backend.models.database import (
    Paper as DBPaper,
    UserBookmark,
)
from backend.services.paper_service import PaperService
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


@router.get(
    "/bookmarks/ids",
    response_model=BookmarkIdsResponse,
    summary="List the current user's bookmarked paper IDs",
)
def get_my_bookmark_ids(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> BookmarkIdsResponse:
    """Return just the IDs (cheap; used to hydrate the Save button state)."""

    rows = (
        db.query(UserBookmark.paper_id)
        .filter(UserBookmark.hf_username == user["username"])
        .order_by(desc(UserBookmark.created_at))
        .all()
    )
    return BookmarkIdsResponse(paper_ids=[int(r[0]) for r in rows])


@router.get(
    "/bookmarks",
    response_model=SavedPapersResponse,
    summary="List the current user's bookmarked papers grouped by area and task",
)
def get_my_bookmarks(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> SavedPapersResponse:
    """Return all bookmarks for the user, grouped by Area and then Task.

    Each paper is classified using its primary task (the row in ``paper_tasks``
    with the lowest ``task_id``). Papers without any tagged task land in a
    catch-all ``Other / Untagged`` bucket.
    """

    bookmark_rows = (
        db.query(UserBookmark.paper_id, UserBookmark.created_at)
        .filter(UserBookmark.hf_username == user["username"])
        .order_by(desc(UserBookmark.created_at))
        .all()
    )
    paper_ids: List[int] = [int(r[0]) for r in bookmark_rows]

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
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    paper = db.query(DBPaper.id).filter(DBPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found"
        )

    existing = (
        db.query(UserBookmark)
        .filter(
            UserBookmark.hf_username == user["username"],
            UserBookmark.paper_id == paper_id,
        )
        .first()
    )
    if existing is not None:
        return None

    db.add(UserBookmark(hf_username=user["username"], paper_id=paper_id))
    db.commit()
    return None


@router.delete(
    "/bookmarks/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove the given paper from the current user's bookmarks",
)
def remove_bookmark(
    paper_id: int = Path(..., ge=1),
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> None:
    db.query(UserBookmark).filter(
        UserBookmark.hf_username == user["username"],
        UserBookmark.paper_id == paper_id,
    ).delete(synchronize_session=False)
    db.commit()
    return None
