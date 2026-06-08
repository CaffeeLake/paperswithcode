"""
User-scoped account preferences endpoints.

All endpoints below require a valid ``pwc_session`` cookie (HF OAuth) and
operate on rows in the ``user_preferences`` table keyed on the lowercased HF
username carried in the session JWT.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.database.connection import get_database_session
from backend.models.database import UserPreference
from backend.utils.auth import require_user

router = APIRouter(prefix="/me", tags=["preferences"])


class UserPreferences(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hide_closed_source_evals: bool = Field(
        default=False,
        description=(
            "When True, closed-source model rows are hidden on benchmark "
            "leaderboards and paper evaluation tables."
        ),
    )


class UserPreferencesUpdate(BaseModel):
    hide_closed_source_evals: bool = Field(
        ..., description="Whether to hide closed-source model evaluations."
    )


def _get_or_create(db: Session, hf_username: str) -> UserPreference:
    pref = (
        db.query(UserPreference)
        .filter(UserPreference.hf_username == hf_username)
        .first()
    )
    if pref is None:
        pref = UserPreference(hf_username=hf_username)
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


@router.get(
    "/preferences",
    response_model=UserPreferences,
    summary="Get the current user's account preferences",
)
def get_my_preferences(
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> UserPreferences:
    pref = _get_or_create(db, user["username"])
    return UserPreferences(hide_closed_source_evals=pref.hide_closed_source_evals)


@router.put(
    "/preferences",
    response_model=UserPreferences,
    summary="Update the current user's account preferences",
)
def update_my_preferences(
    request: UserPreferencesUpdate,
    user: dict = Depends(require_user),
    db: Session = Depends(get_database_session),
) -> UserPreferences:
    pref = _get_or_create(db, user["username"])
    pref.hide_closed_source_evals = request.hide_closed_source_evals
    db.add(pref)
    db.commit()
    db.refresh(pref)
    return UserPreferences(hide_closed_source_evals=pref.hide_closed_source_evals)
