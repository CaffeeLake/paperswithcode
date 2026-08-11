from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import StagingAccessRequest
from backend.routers import staging_access
from backend.services.staging_access_service import submit_staging_access_request
from backend.utils import auth as auth_utils


def request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/staging-access-request",
            "scheme": "https",
            "headers": [],
        }
    )


def database() -> Session:
    engine = create_engine("sqlite://")
    StagingAccessRequest.__table__.create(engine)
    return Session(engine)


def test_submit_staging_access_request_is_idempotent():
    db = database()
    try:
        first = submit_staging_access_request(
            db,
            hf_subject="hf-subject",
            hf_username="first-name",
            email="first@example.com",
        )
        second = submit_staging_access_request(
            db,
            hf_subject="hf-subject",
            hf_username="renamed-user",
            email="renamed@example.com",
        )

        assert first.hf_subject == second.hf_subject
        assert second.hf_username == "renamed-user"
        assert second.email == "renamed@example.com"
        assert second.email_verified is True
        assert second.status == "pending"
        assert db.query(StagingAccessRequest).count() == 1
    finally:
        db.close()


def test_authorized_request_preserves_approval_while_collecting_email():
    db = database()
    try:
        row = submit_staging_access_request(
            db,
            hf_subject="hf-subject",
            hf_username="verified-user",
            email="verified@example.com",
            already_authorized=True,
        )

        assert row.status == "approved"
        assert row.email == "verified@example.com"
    finally:
        db.close()


def test_request_uses_verified_session_identity(monkeypatch):
    current = Settings(environment="staging")
    monkeypatch.setattr(staging_access, "get_settings", lambda: current)
    monkeypatch.setattr(auth_utils, "get_settings", lambda: current)
    monkeypatch.setattr(
        staging_access,
        "decode_request_session",
        lambda _request: {
            "sub": "hf-subject",
            "username": "verified-user",
            "email": "verified@example.com",
            "email_verified": True,
        },
    )
    db = database()
    try:
        response = staging_access.request_staging_access(request(), db)
        assert response.hf_username == "verified-user"
        assert response.status == "pending"
        row = db.get(StagingAccessRequest, "hf-subject")
        assert row is not None
        assert row.email == "verified@example.com"
    finally:
        db.close()


def test_request_is_staging_only(monkeypatch):
    monkeypatch.setattr(
        staging_access, "get_settings", lambda: Settings(environment="production")
    )
    db = database()
    try:
        try:
            staging_access.request_staging_access(request(), db)
        except HTTPException as error:
            assert error.status_code == 404
        else:
            raise AssertionError("production request should be hidden")
    finally:
        db.close()


def test_request_requires_email_verified_by_hugging_face(monkeypatch):
    current = Settings(environment="staging")
    monkeypatch.setattr(staging_access, "get_settings", lambda: current)
    monkeypatch.setattr(
        staging_access,
        "decode_request_session",
        lambda _request: {
            "sub": "hf-subject",
            "username": "verified-user",
            "email": "unverified@example.com",
            "email_verified": False,
        },
    )
    db = database()
    try:
        with pytest.raises(HTTPException, match="verified email") as caught:
            staging_access.request_staging_access(request(), db)
        assert caught.value.status_code == 401
        assert db.query(StagingAccessRequest).count() == 0
    finally:
        db.close()


def test_access_request_migration_is_staging_owned_and_guarded():
    migration = (
        Path(__file__).resolve().parents[1]
        / "database/migrations/add_staging_access_requests.sql"
    ).read_text()

    assert "current_schema() <> 'staging'" in migration
    assert "ALTER TABLE staging_access_requests OWNER TO pwc_staging_owner" in migration
    assert (
        "GRANT SELECT, INSERT, UPDATE ON staging_access_requests TO pwc_staging"
        in migration
    )


def test_access_request_email_migration_is_staging_owned_and_verified():
    migration = (
        Path(__file__).resolve().parents[1]
        / "database/migrations/add_staging_access_request_emails.sql"
    ).read_text()

    assert "current_schema() <> 'staging'" in migration
    assert "email VARCHAR(320)" in migration
    assert "CHECK (email IS NULL OR email_verified)" in migration
    assert "ALTER TABLE staging_access_requests OWNER TO pwc_staging_owner" in migration
