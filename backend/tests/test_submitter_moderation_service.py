from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.routers import profiles
from backend.services import submitter_moderation_service as moderation_module
from backend.services.submitter_moderation_service import (
    SubmissionSuspensionResult,
    SubmitterModerationService,
)
from backend.services.user_profile_service import UserProfileError
from backend.services.user_profile_service import UserProfileService


ACTOR = {
    "hf_subject": "admin-subject",
    "username": "admin",
    "role": "admin",
}


def _request(request_id: str | None = "request-id") -> Request:
    headers = [] if request_id is None else [(b"x-request-id", request_id.encode())]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/submitters/subject/moderation",
            "headers": headers,
        }
    )


class _ProfileService:
    def __init__(self, db):
        self.db = db
        self.calls = []

    def moderation_snapshot(self, hf_subject, *, lock=False):
        self.calls.append(("snapshot", hf_subject, lock))
        return {
            "hf_subject": hf_subject,
            "is_submission_suspended": False,
            "submissions": [
                {"id": 1, "status": "pending"},
                {"id": 2, "status": "approved"},
                {"id": 3, "status": "pending"},
            ],
        }

    def suspend(self, **kwargs):
        self.calls.append(("suspend", kwargs))

    def reject_active_as_spam(self, **kwargs):
        self.calls.append(("reject", kwargs))
        return 2


class _MutationService:
    instances = []

    def __init__(self, db):
        self.db = db
        self.calls = []
        self.__class__.instances.append(self)

    def mutate(self, **kwargs):
        recorded = {
            key: value
            for key, value in kwargs.items()
            if key not in {"snapshot", "apply"}
        }
        self.calls.append(recorded)
        before = kwargs["snapshot"]()
        kwargs["apply"]()
        after = {
            **before,
            "is_submission_suspended": kwargs["request_payload"].get(
                "suspended", False
            ),
        }
        return after, object(), False


@pytest.fixture(autouse=True)
def _reset_mutation_instances():
    _MutationService.instances = []


def _service(monkeypatch):
    monkeypatch.setattr(moderation_module, "CatalogMutationService", _MutationService)
    service = SubmitterModerationService(object())
    service.profiles = _ProfileService(service.db)
    return service


def test_suspension_owns_exact_audit_workflow_and_locked_snapshot(monkeypatch):
    service = _service(monkeypatch)

    result = service.set_suspension(
        hf_subject="submitter-subject",
        suspended=True,
        reason=" policy breach ",
        actor=ACTOR,
        request_id="request-id",
    )

    assert result == SubmissionSuspensionResult("submitter-subject", True)
    assert service.profiles.calls == [
        ("snapshot", "submitter-subject", True),
        (
            "suspend",
            {
                "hf_subject": "submitter-subject",
                "suspended": True,
                "reason": " policy breach ",
                "actor": ACTOR,
            },
        ),
    ]
    assert _MutationService.instances[0].calls == [
        {
            "actor": ACTOR,
            "operation": "moderate",
            "entity_type": "submitter_moderation",
            "entity_id": "submitter-subject",
            "request_payload": {
                "suspended": True,
                "reason": " policy breach ",
            },
            "idempotency_key": None,
            "expected_version": None,
            "request_id": "request-id",
        }
    ]


def test_spam_rejection_preserves_unlocked_precount_then_locked_audit(monkeypatch):
    service = _service(monkeypatch)

    count = service.reject_active_as_spam(
        hf_subject="submitter-subject",
        actor=ACTOR,
        request_id="request-id",
    )

    assert count == 2
    assert service.profiles.calls == [
        ("snapshot", "submitter-subject", False),
        ("snapshot", "submitter-subject", True),
        (
            "reject",
            {"hf_subject": "submitter-subject", "actor": ACTOR},
        ),
    ]
    assert _MutationService.instances[0].calls[0]["request_payload"] == {
        "reject_active_as_spam": True
    }


def test_suspension_router_maps_missing_profile_and_exact_request_id(monkeypatch):
    calls = []

    class Service:
        def __init__(self, db):
            calls.append(("init", db))

        def set_suspension(self, **kwargs):
            calls.append(("suspend", kwargs))
            raise UserProfileError("Profile not found")

    monkeypatch.setattr(profiles, "SubmitterModerationService", Service)

    with pytest.raises(HTTPException) as error:
        profiles.set_submission_suspension(
            "submitter-subject",
            profiles.SuspendRequest(suspended=False, reason=" restored "),
            _request(),
            ACTOR,
            object(),
        )

    assert error.value.status_code == 404
    assert error.value.detail == "Profile not found"
    assert calls[1][1]["request_id"] == "request-id"


def test_spam_confirmation_rejects_before_constructing_service(monkeypatch):
    monkeypatch.setattr(
        profiles,
        "SubmitterModerationService",
        lambda _db: pytest.fail("invalid confirmation reached the service"),
    )

    with pytest.raises(HTTPException) as error:
        profiles.reject_submitter_spam(
            "submitter-subject",
            profiles.SpamRejectRequest(confirm="reject_active_submissions_as_spam"),
            _request(),
            ACTOR,
            object(),
        )

    assert error.value.status_code == 400
    assert error.value.detail == "Confirmation value is required"


def test_spam_router_preserves_count_and_missing_profile_propagation(monkeypatch):
    class Service:
        def __init__(self, _db):
            pass

        def reject_active_as_spam(self, **kwargs):
            assert kwargs["request_id"]
            if kwargs["hf_subject"] == "missing":
                raise UserProfileError("Profile not found")
            return 7

    monkeypatch.setattr(profiles, "SubmitterModerationService", Service)
    body = profiles.SpamRejectRequest(confirm="REJECT_ACTIVE_SUBMISSIONS_AS_SPAM")

    assert profiles.reject_submitter_spam(
        "submitter-subject", body, _request(None), ACTOR, object()
    ) == {"rejected": 7}
    with pytest.raises(UserProfileError, match="Profile not found"):
        profiles.reject_submitter_spam("missing", body, _request(), ACTOR, object())


def test_profile_suspension_field_semantics_are_preserved():
    profile = type(
        "Profile",
        (),
        {
            "is_submission_suspended": False,
            "suspension_reason": None,
            "suspended_at": None,
            "suspended_by_hf_subject": None,
        },
    )()

    class Database:
        def get(self, _model, hf_subject):
            assert hf_subject == "submitter-subject"
            return profile

    service = UserProfileService(Database())
    service.suspend(
        hf_subject="submitter-subject",
        suspended=True,
        reason="  policy breach  ",
        actor=ACTOR,
    )
    assert profile.is_submission_suspended is True
    assert profile.suspension_reason == "policy breach"
    assert profile.suspended_at is not None
    assert profile.suspended_by_hf_subject == "admin-subject"

    service.suspend(
        hf_subject="submitter-subject",
        suspended=False,
        reason="  restored  ",
        actor=ACTOR,
    )
    assert profile.is_submission_suspended is False
    assert profile.suspension_reason == "restored"
    assert profile.suspended_at is None
    assert profile.suspended_by_hf_subject is None


def test_profile_spam_rejection_changes_only_pending_rows_with_safe_reasons():
    pending = type("Submission", (), {"status": "pending"})()
    approved = type("Submission", (), {"status": "approved"})()

    class Query:
        def filter(self, *_criteria):
            return self

        def with_for_update(self):
            return self

        def all(self):
            return [pending]

    class Database:
        def query(self, _model):
            return Query()

    count = UserProfileService(Database()).reject_active_as_spam(
        hf_subject="submitter-subject", actor=ACTOR
    )

    assert count == 1
    assert pending.status == "rejected"
    assert pending.admin_note == (
        "Rejected as spam by a separately confirmed moderation action"
    )
    assert pending.user_review_reason == "Rejected under the submission abuse policy."
    assert pending.reviewed_by == "admin"
    assert pending.reviewed_by_kind == "human"
    assert pending.reviewed_by_hf_subject == "admin-subject"
    assert pending.reviewed_at is not None
    assert approved.status == "approved"


def _dependency_names(route) -> set[str]:
    names = set()

    def collect(dependant):
        for child in dependant.dependencies:
            names.add(getattr(child.call, "__name__", type(child.call).__name__))
            collect(child)

    collect(route.dependant)
    return names


def test_submitter_moderation_routes_remain_hf_session_admin_only():
    routes = {
        (method, route.path): route
        for route in profiles.router.routes
        for method in route.methods
    }
    for path in (
        "/admin/submitters/{hf_subject}/suspension",
        "/admin/submitters/{hf_subject}/reject-spam",
    ):
        assert "require_hf_admin" in _dependency_names(routes[("POST", path)])
