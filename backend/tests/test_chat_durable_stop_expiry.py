from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.config import get_settings
from backend.routers import chat as chat_router
from backend.services import chat_session_service as chat_session_module
from backend.services.chat_session_service import (
    ChatOwner,
    ChatServiceError,
    ChatSessionService,
)
from backend.services.chat_turn_job_repository import (
    AccountBusy,
    StaleTurnClaim,
    TurnLeaseClaim,
)


def _enabled_settings():
    return get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": True}
    )


def test_enabled_stop_commits_cancelling_before_manager_signal(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    ordering: list[str] = []

    class DB:
        def commit(self):
            ordering.append("commit")

        def rollback(self):
            ordering.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, owner, requested_session_id):
            assert owner.hf_user_id == "owner-1"
            assert requested_session_id == session_id
            ordering.append("cancelling")
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

    class Manager:
        async def cancel(self, requested_session_id, requested_turn_id):
            assert (requested_session_id, requested_turn_id) == (session_id, turn_id)
            ordering.append("signal")
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: Manager())
    db = DB()

    response = asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=db,
            settings=_enabled_settings(),
        )
    )

    assert response.status_code == 204
    assert ordering == ["cancelling", "commit", "signal"]


def test_enabled_missing_cancel_control_terminalizes_projection(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, owner, request):
            assert owner.hf_user_id == "owner-1"
            assert request.turn_id == turn_id
            calls.append("interrupted")

    class Manager:
        async def cancel(self, *_args):
            calls.append("cancel")
            return False

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: Manager())
    db = DB()

    asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=db,
            settings=_enabled_settings(),
        )
    )

    assert calls == [
        "commit",
        "cancel",
        "terminate",
        "interrupted",
        "commit",
    ]


def test_enabled_failed_termination_still_terminalizes_projection(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[str] = []

    class DB:
        def commit(self):
            calls.append("commit")

        def rollback(self):
            calls.append("rollback")

    class Service:
        def __init__(self, *_args):
            pass

        def request_cancel(self, *_args):
            return SimpleNamespace(session_id=session_id, turn_id=turn_id)

        def interrupt_cancel_without_control(self, *_args):
            calls.append("interrupted")

    class Manager:
        async def cancel(self, *_args):
            calls.append("cancel")
            return False

        async def terminate(self, *_args, **_kwargs):
            calls.append("terminate")
            raise RuntimeError("termination failed")

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: Manager())

    with pytest.raises(RuntimeError, match="termination failed"):
        asyncio.run(
            chat_router.cancel_active_turn(
                session_id,
                user={"hf_user_id": "owner-1", "username": "owner"},
                db=DB(),
                settings=_enabled_settings(),
            )
        )

    assert calls == [
        "commit",
        "cancel",
        "terminate",
        "interrupted",
        "commit",
    ]


def test_false_mode_cancel_keeps_old_path_without_durable_method(monkeypatch):
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()

    class Service:
        def __init__(self, *_args):
            pass

        def get_session(self, *_args):
            return SimpleNamespace(active_turn_id=turn_id), []

        def request_cancel(self, *_args):
            pytest.fail("durable Stop queried while switch is false")

    class Manager:
        async def cancel(self, *_args):
            return True

    monkeypatch.setattr(chat_router, "ChatSessionService", Service)
    monkeypatch.setattr(chat_router, "shared_sandbox_manager", lambda _: Manager())

    asyncio.run(
        chat_router.cancel_active_turn(
            session_id,
            user={"hf_user_id": "owner-1", "username": "owner"},
            db=SimpleNamespace(),
            settings=get_settings().model_copy(
                update={"chat_durable_turn_dispatch_enabled": False}
            ),
        )
    )


def test_request_cancel_uses_exact_persisted_claim(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    claim = TurnLeaseClaim(turn_id, "other-process", 19, 4)
    session = SimpleNamespace(id=session_id, active_turn_id=turn_id)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="running",
    )
    seen: list[TurnLeaseClaim] = []

    class Repository:
        def load_by_turn(self, _db, requested_turn_id, *, lock=False):
            assert requested_turn_id == turn_id
            assert lock is True
            return job

        def request_cancelling(self, _db, **kwargs):
            assert kwargs["turn_id"] == turn_id
            assert kwargs["worker_id"].startswith("local-runner:")
            seen.append(claim)
            job.state = "cancelling"
            return claim

    service = ChatSessionService(SimpleNamespace(), settings)
    service._owned = lambda *_args, **kwargs: session
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    request = service.request_cancel(ChatOwner("owner-1", "owner"), session_id)

    assert request.turn_id == turn_id
    assert seen == [claim]


def test_active_expiry_reconciles_durable_before_legacy_projection(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    ordering: list[str] = []
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="admitted",
    )

    class Repository:
        def load_by_turn(self, _db, requested_turn_id, *, lock=False):
            assert requested_turn_id == turn_id
            assert lock
            return job

        def interrupt_exact_expired(self, _db, **kwargs):
            ordering.append("durable")
            assert kwargs["turn_id"] == turn_id
            assert kwargs["admitted_worker_id"].startswith("local-runner:")
            job.state = "interrupted"
            return job

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    assert service._apply_expired_active_turn(session, message) is True

    ordering.append("legacy" if session.active_turn_id is None else "not-cleared")
    assert ordering == ["durable", "legacy"]
    assert message.status == "interrupted"
    assert message.error_code == "lease_expired"


def test_live_durable_claim_fails_closed_before_legacy_expiry(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    expiry = object()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=expiry,
    )
    message = SimpleNamespace(status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="running",
    )

    class Repository:
        def load_by_turn(self, *_args, **_kwargs):
            return job

        def interrupt_exact_expired(self, *_args, **_kwargs):
            raise StaleTurnClaim("still live")

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    with pytest.raises(ChatServiceError) as exc_info:
        service._apply_expired_active_turn(session, message)

    assert exc_info.value.code == "durable_control_conflict"
    assert session.active_turn_id == turn_id
    assert session.active_turn_expires_at is expiry
    assert message.status == "generating"
    assert message.error_code is None


def test_replay_expiry_reconciles_exact_durable_job(monkeypatch):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    calls: list[uuid.UUID] = []
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(turn_id=turn_id, status="generating", error_code=None)
    job = SimpleNamespace(
        turn_id=turn_id,
        chat_session_id=session_id,
        hf_user_id="owner-1",
        state="leased",
    )

    class Repository:
        def load_by_turn(self, *_args, **_kwargs):
            return job

        def interrupt_exact_expired(self, _db, **kwargs):
            calls.append(kwargs["turn_id"])
            return job

    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(service, "_turn_job_repository", lambda: Repository())

    service._apply_expired_replay(session, message)

    assert calls == [turn_id]
    assert session.active_turn_id is None
    assert message.status == "interrupted"


def test_false_mode_expiry_never_constructs_durable_repository(monkeypatch):
    settings = get_settings().model_copy(
        update={"chat_durable_turn_dispatch_enabled": False}
    )
    turn_id = uuid.uuid4()
    session = SimpleNamespace(
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    message = SimpleNamespace(status="generating", error_code=None)
    service = ChatSessionService(SimpleNamespace(), settings)
    monkeypatch.setattr(
        service,
        "_turn_job_repository",
        lambda: pytest.fail("durable expiry queried while switch is false"),
    )

    assert service._apply_expired_active_turn(session, message) is True
    assert session.active_turn_id is None
    assert message.status == "interrupted"


def test_account_busy_preflight_reconciles_expired_projection_then_retries(
    monkeypatch,
):
    settings = _enabled_settings()
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    session = SimpleNamespace(
        id=session_id,
        hf_user_id="owner-1",
        selected_model=next(iter(settings.chat_model_routes)),
        reasoning_effort="low",
        transcript_status="ready",
        primary_paper_id=None,
        active_turn_id=turn_id,
        active_turn_expires_at=object(),
    )
    stale = SimpleNamespace(turn_id=turn_id, status="generating", error_code=None)
    calls: list[str] = []

    class Coordinator:
        def __init__(self, *_args):
            self.calls = 0

        def preflight(self, **_kwargs):
            self.calls += 1
            calls.append(f"preflight-{self.calls}")
            if self.calls == 1:
                raise AccountBusy("existing expired turn")
            return SimpleNamespace(existing_job=None)

    monkeypatch.setattr(
        chat_session_module, "ChatTurnAdmissionCoordinator", Coordinator
    )
    service = ChatSessionService(SimpleNamespace(), settings)
    service._owned = lambda *_args, **_kwargs: session

    def load_stale(_session, _now):
        return stale if session.active_turn_id else None

    def apply_expired(_session, _stale):
        if _session.active_turn_id is None:
            return False
        calls.append("reconcile")
        _session.active_turn_id = None
        _session.active_turn_expires_at = None
        return True

    monkeypatch.setattr(service, "_load_expired_active_message", load_stale)
    monkeypatch.setattr(service, "_apply_expired_active_turn", apply_expired)
    monkeypatch.setattr(
        service,
        "_resolve_replay",
        lambda *_args, **_kwargs: SimpleNamespace(kind="continue"),
    )
    monkeypatch.setattr(service, "_has_unresolved_turn", lambda _session: True)

    with pytest.raises(ChatServiceError) as exc_info:
        service.begin_turn(
            ChatOwner("owner-1", "owner"),
            session_id=session_id,
            client_message_id="new-request",
            text="retry after expiry",
        )

    assert exc_info.value.code == "turn_requires_retry"
    assert exc_info.value.commit_changes is True
    assert calls == ["preflight-1", "reconcile", "preflight-2"]
