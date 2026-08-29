from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.chat_gateway_app as gateway
import backend.services.chat_turn_runner as turn_runner
from backend.config import get_settings
from backend.services.chat_capability_service import (
    ChatCapabilityService,
    IssuedCapability,
)
from backend.services.chat_session_service import ChatOwner, TurnAdmission
from backend.services.chat_turn_job_repository import StaleTurnClaim, TurnLeaseClaim


class FenceDB:
    def __init__(self) -> None:
        self.rollbacks = 0

    def rollback(self) -> None:
        self.rollbacks += 1

    def commit(self) -> None:
        pass


def _external_capability(turn_id: uuid.UUID):
    return SimpleNamespace(
        turn_id=turn_id,
        scopes=["model", "catalog", "session_store", "external_turn"],
    )


def test_capability_service_accepts_the_external_turn_scope():
    added = []

    class DB:
        def add(self, row):
            added.append(row)

        def flush(self):
            pass

    issued = ChatCapabilityService(DB()).issue(
        chat_session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        owner_id="owner-1",
        model="route",
        scopes={"model", "external_turn"},
        agent_harness="pi",
    )

    assert issued.capability_id == added[0].id
    assert added[0].scopes == ["external_turn", "model"]


def test_external_turn_scope_requires_all_claim_headers(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    with pytest.raises(HTTPException) as error:
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "chat_turn_fence_missing"


def test_external_turn_scope_rejects_a_stale_claim(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    class Jobs:
        def require_live_claim(self, *_args, **_kwargs):
            raise StaleTurnClaim("stale")

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    with pytest.raises(HTTPException) as error:
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
            turn_worker_id="api-1",
            turn_worker_generation="4",
            turn_lease_generation="9",
        )

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "chat_turn_fence_stale"


def test_external_turn_scope_checks_the_exact_immutable_claim(monkeypatch):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    observed: list[TurnLeaseClaim] = []

    class Jobs:
        def require_live_claim(self, _db, *, claim, now):
            assert now.tzinfo is not None
            observed.append(claim)

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    assert (
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(turn_id),
            FenceDB(),
            turn_worker_id="api-1",
            turn_worker_generation="4",
            turn_lease_generation="9",
        )
        is row
    )
    assert observed == [TurnLeaseClaim(turn_id, "api-1", 4, 9)]


def test_legacy_sandbox_scope_remains_header_free(monkeypatch):
    row = SimpleNamespace(scopes=["model"])
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )

    class Jobs:
        def require_live_claim(self, *_args, **_kwargs):
            raise AssertionError("legacy capabilities must not consult the turn fence")

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs, raising=False)

    assert (
        gateway._scope(
            "token",
            "model",
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            FenceDB(),
        )
        is row
    )


@pytest.mark.parametrize(
    ("path", "body", "extra_headers"),
    [
        ("/catalog", {"operation": "search", "arguments": {"query": "x"}}, {}),
        (
            "/catalog",
            {"operation": "web_search", "arguments": {"query": "x"}},
            {},
        ),
        (
            "/hf-catalog",
            {"operation": "model_info", "arguments": {"repo_id": "owner/model"}},
            {},
        ),
        ("/session-store", {"action": "load_session"}, {}),
        ("/artifact-prepare", {"paper_route_id": "2401.00001"}, {}),
        ("/paper", {"operation": "create", "title": "Draft"}, {}),
        (
            "/artifact-publish?publication_id=publication-1",
            b"x",
            {"Content-Type": "application/zip"},
        ),
        ("/web-fetch", {"url": "https://example.com"}, {}),
        (
            "/v1/responses",
            {"model": "gpt-5.6", "input": "x", "max_output_tokens": 1},
            {},
        ),
        ("/v1/messages", {"model": "route", "messages": [], "max_tokens": 1}, {}),
    ],
)
def test_every_gateway_entry_rejects_an_external_capability_before_side_effects(
    monkeypatch, path, body, extra_headers
):
    turn_id = uuid.uuid4()
    row = _external_capability(turn_id)
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    settings = get_settings().model_copy(deep=True)
    settings.chat_hf_catalog_enabled = True
    settings.chat_openai_direct_enabled = True
    settings.openai_api_key = "test-openai-key"
    settings.chat_openai_model = "gpt-5.6"
    db = FenceDB()
    gateway.app.dependency_overrides[gateway.get_database_session] = lambda: db
    gateway.app.dependency_overrides[gateway.get_settings] = lambda: settings
    headers = {
        "Authorization": "Bearer token",
        "X-PWC-Session": str(uuid.uuid4()),
        "X-PWC-Turn": str(turn_id),
        **extra_headers,
    }
    try:
        with TestClient(gateway.app, raise_server_exceptions=False) as client:
            if isinstance(body, bytes):
                response = client.post(path, content=body, headers=headers)
            else:
                response = client.post(path, json=body, headers=headers)
    finally:
        gateway.app.dependency_overrides.clear()

    assert response.status_code == 403, (path, response.text)
    assert response.json()["detail"]["code"] == "chat_turn_fence_missing"


def test_gateway_accepts_complete_external_turn_headers(monkeypatch):
    turn_id = uuid.uuid4()
    row = SimpleNamespace(
        turn_id=turn_id,
        scopes=["catalog", "external_turn"],
        owner_hash="a" * 64,
    )
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "validate",
        lambda *_args, **_kwargs: row,
    )
    monkeypatch.setattr(
        gateway.ChatCapabilityService,
        "meter_catalog",
        lambda *_args, **_kwargs: None,
    )

    class Jobs:
        def require_live_claim(self, _db, *, claim, now):
            assert claim == TurnLeaseClaim(turn_id, "api-1", 4, 9)
            assert now.tzinfo is not None

    monkeypatch.setattr(gateway, "ChatTurnJobRepository", Jobs)
    monkeypatch.setattr(
        gateway.ChatGatewayService,
        "catalog",
        lambda *_args, **_kwargs: {"papers": []},
    )
    db = FenceDB()
    gateway.app.dependency_overrides[gateway.get_database_session] = lambda: db
    try:
        with TestClient(gateway.app) as client:
            response = client.post(
                "/catalog",
                json={"operation": "search", "arguments": {"query": "x"}},
                headers={
                    "Authorization": "Bearer token",
                    "X-PWC-Session": str(uuid.uuid4()),
                    "X-PWC-Turn": str(turn_id),
                    "X-PWC-Turn-Worker-ID": "api-1",
                    "X-PWC-Turn-Worker-Generation": "4",
                    "X-PWC-Turn-Lease-Generation": "9",
                },
            )
    finally:
        gateway.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"result": {"papers": []}}


@pytest.mark.parametrize("external", [False, True])
def test_only_external_pi_runner_capabilities_receive_external_turn_scope(
    monkeypatch, external
):
    settings = get_settings().model_copy(deep=True)
    settings.chat_external_pi_admission_enabled = external
    turn_id = uuid.uuid4()
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=turn_id,
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    owner = ChatOwner(
        hf_user_id="owner-1",
        hf_username="owner",
        hf_inference_token=None,
        hf_inference_bill_to=None,
        openrouter_token=None,
        openrouter_mode="openrouter_funded",
        openrouter_credential_revision=None,
    )
    observed_scopes: list[set[str]] = []

    class DB:
        def commit(self):
            pass

    @contextmanager
    def session():
        yield DB()

    def issue(_self, **kwargs):
        observed_scopes.append(kwargs["scopes"])
        return IssuedCapability("token", None, datetime.now(UTC) + timedelta(minutes=1))

    monkeypatch.setattr(
        turn_runner, "db_manager", SimpleNamespace(session_local=session)
    )
    monkeypatch.setattr(ChatCapabilityService, "issue", issue)
    monkeypatch.setattr(
        turn_runner,
        "ExternalPiChatTurnRunner",
        lambda **_kwargs: "external-runner",
    )
    monkeypatch.setattr(
        turn_runner,
        "ModalChatTurnRunner",
        lambda **_kwargs: "sandbox-runner",
    )

    created = turn_runner.create_chat_turn_runner(
        settings=settings,
        owner=owner,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        store=SimpleNamespace(),
    )

    assert created == ("external-runner" if external else "sandbox-runner")
    assert ("external_turn" in observed_scopes[0]) is external
