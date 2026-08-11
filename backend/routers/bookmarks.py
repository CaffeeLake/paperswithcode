"""
User-scoped bookmark endpoints.

All endpoints below require a valid ``pwc_session`` cookie. Existing database
bookmarks remain readable until the user opts into a private Hugging Face
Bucket. After migration, database rows are retained as a compatibility mirror.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.api import Paper as ApiPaper
from backend.models.database import (
    Paper as DBPaper,
)
from backend.models.database import (
    UserBookmark,
)
from backend.services.bookmark_service import BookmarkReadService
from backend.services.paper_bucket_service import (
    BUCKET_MANAGE_OAUTH_COOKIE_NAME,
    PaperBucketError,
)
from backend.services.saved_papers_bucket_service import SavedPapersBucket
from backend.utils.auth import require_user

router = APIRouter(prefix="/me", tags=["bookmarks"])


# ---------------------------------------------------------------------------
# Response shapes
# ---------------------------------------------------------------------------


class BookmarkIdsResponse(BaseModel):
    paper_ids: list[int] = Field(
        default_factory=list,
        description="IDs of papers bookmarked by the current user",
    )


class SavedTaskGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(None, description="Task ID, NULL for the 'Untagged' bucket")
    slug: str | None = Field(
        None, description="Task slug, NULL for the 'Untagged' bucket"
    )
    name: str = Field(..., description="Task display name")
    papers: list[ApiPaper] = Field(default_factory=list)


class SavedAreaGroup(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = Field(None, description="Area ID, NULL for the 'Other' bucket")
    name: str = Field(..., description="Area display name")
    tasks: list[SavedTaskGroup] = Field(default_factory=list)


class SavedPapersResponse(BaseModel):
    count: int = Field(..., description="Total number of bookmarked papers")
    areas: list[SavedAreaGroup] = Field(default_factory=list)
    bucket_connected: bool = Field(
        False,
        description="Whether the response was read from the user's HF Bucket",
    )


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


def _bucket_authorization_required() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={
            "code": "saved_papers_bucket_authorization_required",
            "message": "Authorize Papers With Code to manage your saved-papers Bucket.",
        },
    )


def _bucket_store(
    request: Request, user: dict, db: Session
) -> SavedPapersBucket | None:
    encrypted = request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME)
    return BookmarkReadService(db).initialize_bucket(
        encrypted_credential=encrypted,
        hf_user_id=user["hf_user_id"],
        username=user["username"],
    )


def _require_bucket_store(
    request: Request, user: dict, db: Session
) -> SavedPapersBucket:
    try:
        store = _bucket_store(request, user, db)
    except PaperBucketError as error:
        raise _bucket_error(error) from error
    if store is None:
        raise _bucket_authorization_required()
    return store


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

    listing = BookmarkReadService(db).list_refs(
        encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
        hf_user_id=user["hf_user_id"],
        username=user["username"],
    )
    return BookmarkIdsResponse(paper_ids=[item.paper_id for item in listing.refs])


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

    projection = BookmarkReadService(db).list_grouped(
        encrypted_credential=request.cookies.get(BUCKET_MANAGE_OAUTH_COOKIE_NAME),
        hf_user_id=user["hf_user_id"],
        username=user["username"],
    )
    areas = [
        SavedAreaGroup(
            id=area.id,
            name=area.name,
            tasks=[
                SavedTaskGroup(
                    id=task.id,
                    slug=task.slug,
                    name=task.name,
                    papers=list(task.papers),
                )
                for task in area.tasks
            ],
        )
        for area in projection.areas
    ]
    return SavedPapersResponse(
        count=projection.count,
        areas=areas,
        bucket_connected=projection.bucket_connected,
    )


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

    store = _require_bucket_store(request, user, db)
    try:
        store.add(
            paper_id,
            title=paper.title,
            arxiv_id=paper.arxiv_id,
            source_url=paper.source_url,
        )
    except PaperBucketError as error:
        raise _bucket_error(error) from error

    existing = (
        db.query(UserBookmark)
        .filter(
            UserBookmark.hf_username == user["username"],
            UserBookmark.paper_id == paper_id,
        )
        .first()
    )
    if existing is None:
        db.add(UserBookmark(hf_username=user["username"], paper_id=paper_id))
        db.commit()
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
    store = _require_bucket_store(request, user, db)
    try:
        store.remove(paper_id)
    except PaperBucketError as error:
        raise _bucket_error(error) from error
    db.query(UserBookmark).filter(
        UserBookmark.hf_username == user["username"],
        UserBookmark.paper_id == paper_id,
    ).delete(synchronize_session=False)
    db.commit()
    return None
