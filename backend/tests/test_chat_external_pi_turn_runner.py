import asyncio
from datetime import UTC, datetime, timedelta
import json
from types import SimpleNamespace
import uuid

import pytest

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import (
    MAX_EXTERNAL_TURN_FRAME_BYTES,
    ExternalPiChatTurnRunner,
)
from backend.services.chat_external_pi_shadow import (
    ExternalPiWorkerControlRejected,
    ExternalPiWorkerUnavailable,
)
from backend.services.chat_external_worker_registry import (
    ExternalWorkerClaim,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)
from backend.services.chat_sandbox_executor import ExecutorReadResult
from backend.services.chat_session_service import TurnAdmission
from backend.services.chat_turn_job_repository import TurnLeaseClaim


class FakeSocket:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    async def send(self, value):
        self.sent.append(value)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            value = next(self.messages)
        except StopIteration:
            raise StopAsyncIteration from None
        if isinstance(value, BaseException):
            raise value
        return value


class SocketContext:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, *_args):
        return None


class SequencedConnector:
    def __init__(self, *sockets):
        self.sockets = iter(sockets)
        self.calls = []

    def __call__(self, url, **kwargs):
        socket = next(self.sockets)
        self.calls.append((url, kwargs, socket))
        return SocketContext(socket)


class SessionContext:
    def __enter__(self):
        return object()

    def __exit__(self, *_args):
        return None


class FakeWorkerRepository:
    def __init__(self, claim):
        self.claim = claim
        self.calls = []

    def select_ready_claim(self, db, *, claim, now):
        self.calls.append(("select", db, claim, now))
        if claim != self.claim:
            raise StaleWorkerClaim("External worker claim was fenced")
        return self.claim

    def require_ready_claim(self, db, *, claim, now):
        self.calls.append(("require", db, claim, now))

    def require_live_claim(self, db, *, claim, now):
        self.calls.append(("require_live", db, claim, now))
        if claim != self.claim:
            raise StaleWorkerClaim("External worker claim was fenced")


class FakeProvider:
    def __init__(self):
        self.created = []
        self.terminated = []

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return type("Sandbox", (), {"object_id": "sb-test"})()

    async def terminate(self, sandbox_id, sandbox=None):
        self.terminated.append((sandbox_id, sandbox))
        return True


class FakeExecutor:
    def __init__(self):
        self.contexts = []
        self.reads = 0

    async def ensure_workspace(self, context):
        self.contexts.append(context)

    async def read_file(self, context, *, path, offset, max_bytes):
        self.contexts.append(context)
        self.reads += 1
        assert path == "/opt/pwc/PWC_CLI_SKILL.md"
        return ExecutorReadResult(path=path, offset=offset, data=b"guide", eof=True)


def worker_status(claim):
    return SimpleNamespace(
        worker_id=claim.worker_id,
        instance_id=claim.instance_id,
        worker_generation=claim.generation,
        release_id=claim.release_id,
        protocol=claim.contract_version,
        state="ready",
        active_sessions=0,
        maximum_sessions=8,
    )


def test_external_pi_runner_lazily_creates_executor_for_remote_read():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
    socket = FakeSocket(
        [
            '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
            '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,"max_bytes":1024,"worker_sequence":1}',
            '{"type":"workspace_ready","worker_sequence":2}',
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":3}',
            '{"type":"worker_done","status":"complete","worker_sequence":4}',
        ]
    )
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
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=(
            repository := FakeWorkerRepository(
                ExternalWorkerClaim(
                    "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
                )
            )
        ),
        worker_status_resolver=lambda: _async_value(worker_status(repository.claim)),
        session_factory=SessionContext,
    )

    async def exercise():
        events = [event async for event in runner.events()]
        await runner.close()
        return events

    events = asyncio.run(exercise())

    assert [event["type"] for event in events] == ["workspace_ready", "done"]
    assert len(provider.created) == 1
    assert provider.created[0]["launch_mode"] == "executor"
    assert provider.terminated[0][0] == "sb-test"
    assert executor.contexts[0].session_id == str(admission.session_id)
    assert '"type":"tool_result"' in socket.sent[1]


def test_external_pi_runner_uses_no_sandbox_without_tools():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    socket = FakeSocket(
        [
            '{"type":"workspace_ready","worker_sequence":1}',
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
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
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=(
            repository := FakeWorkerRepository(
                ExternalWorkerClaim(
                    "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
                )
            )
        ),
        worker_status_resolver=lambda: _async_value(worker_status(repository.claim)),
        session_factory=SessionContext,
    )

    async def exercise():
        events = [event["type"] async for event in runner.events()]
        await runner.close()
        return events

    assert asyncio.run(exercise()) == ["workspace_ready", "done"]
    assert provider.created == []


def test_external_pi_runner_delivers_contiguous_worker_buffer_exhaustion():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
    socket = FakeSocket(
        [
            '{"type":"workspace_ready","worker_sequence":1}',
            '{"type":"error","code":"worker_event_buffer_exhausted",'
            '"message":"The research run failed.","worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=lambda *_args, **_kwargs: SocketContext(socket),
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "worker_event_buffer_exhausted",
            "message": "The research run failed.",
        },
    ]


def test_external_pi_runner_fences_socket_and_run_with_distinct_claims():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.UUID("20000000-0000-4000-8000-000000000001")
    admission = TurnAdmission(
        session_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
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
    worker_claim = ExternalWorkerClaim(
        "external-pi-1",
        uuid.UUID("30000000-0000-4000-8000-000000000001"),
        7,
        "release-a",
        "external-pi-v1",
    )
    repository = FakeWorkerRepository(worker_claim)
    socket = FakeSocket(
        ['{"type":"worker_done","status":"complete","worker_sequence":1}']
    )
    connection = {}

    def connect(url, **kwargs):
        connection.update(
            url=url, kwargs=kwargs, repository_calls=list(repository.calls)
        )
        return SocketContext(socket)

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_repository=repository,
        worker_status_resolver=lambda: _async_value(worker_status(worker_claim)),
        session_factory=SessionContext,
        now=lambda: datetime(2026, 8, 29, 12, tzinfo=UTC),
    )

    assert asyncio.run(_collect(runner)) == []
    assert [call[0] for call in connection["repository_calls"]] == [
        "select",
        "require",
    ]
    assert connection["kwargs"]["additional_headers"] == {
        "Authorization": f"Bearer {settings.chat_external_pi_worker_token}",
        "X-PWC-Worker-Generation": "7",
    }
    assert connection["kwargs"]["max_size"] == MAX_EXTERNAL_TURN_FRAME_BYTES
    assert connection["kwargs"]["open_timeout"] == (
        settings.chat_external_pi_startup_timeout_seconds
    )
    assert connection["kwargs"]["ping_interval"] == 20
    assert connection["kwargs"]["ping_timeout"] == 20
    assert json.loads(socket.sent[0])["turnClaim"] == {
        "turnId": str(turn_id),
        "workerId": "api-1",
        "workerGeneration": 4,
        "leaseGeneration": 9,
    }


def test_external_pi_runner_rejects_endpoint_status_mismatch_before_connect():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    selected = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    endpoint = ExternalWorkerClaim(
        "external-pi-2", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    connected = False

    def connect(*_args, **_kwargs):
        nonlocal connected
        connected = True
        raise AssertionError("stale endpoint must not connect")

    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connect,
        worker_repository=FakeWorkerRepository(selected),
        worker_status_resolver=lambda: _async_value(worker_status(endpoint)),
        session_factory=SessionContext,
    )

    with pytest.raises(StaleWorkerClaim):
        asyncio.run(_collect(runner))
    assert connected is False


def test_external_pi_runner_rejects_worker_becoming_full_before_connect():
    class FullWorkerRepository(FakeWorkerRepository):
        def require_ready_claim(self, db, *, claim, now):
            super().require_ready_claim(db, claim=claim, now=now)
            raise WorkerLeaseUnavailable("External worker is not ready")

    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
        durable_claim=TurnLeaseClaim(turn_id, "api-1", 4, 9),
    )
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 1, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=lambda *_args, **_kwargs: pytest.fail("connected"),
        worker_repository=FullWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        asyncio.run(_collect(runner))


async def _collect(runner):
    return [event async for event in runner.events()]


async def _async_value(value):
    return value


def test_external_pi_runner_reattaches_same_run_from_last_acknowledged_sequence():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    turn_id = uuid.UUID("20000000-0000-4000-8000-000000000001")
    admission = TurnAdmission(
        session_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
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
    worker_claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    first = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("link lost")]
    )
    second = FakeSocket(
        [
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    connector = SequencedConnector(first, second)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=(repository := FakeWorkerRepository(worker_claim)),
        worker_status_resolver=lambda: _async_value(worker_status(worker_claim)),
        session_factory=SessionContext,
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "done",
            "finish_reason": "success",
            "followups": [],
        },
    ]
    assert json.loads(first.sent[0])["type"] == "run_turn"
    assert json.loads(second.sent[0]) == {
        "v": 1,
        "type": "attach_turn",
        "request_id": "request-1",
        "turnClaim": {
            "turnId": str(turn_id),
            "workerId": "api-1",
            "workerGeneration": 4,
            "leaseGeneration": 9,
        },
        "afterSequence": 1,
    }
    assert json.loads(second.sent[1]) == {
        "v": 1,
        "type": "ack_terminal",
        "request_id": "request-1",
        "turnClaim": {
            "turnId": str(turn_id),
            "workerId": "api-1",
            "workerGeneration": 4,
            "leaseGeneration": 9,
        },
        "sequence": 3,
    }
    assert [call[0] for call in repository.calls] == [
        "select",
        "require",
        "require_live",
    ]


def test_external_pi_runner_never_reexecutes_replayed_tool_request():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
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
    tool = (
        '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
        '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,'
        '"max_bytes":1024,"worker_sequence":1}'
    )
    first = FakeSocket([tool, OSError("result acknowledgement lost")])
    second = FakeSocket(
        [
            tool,
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":2}',
            '{"type":"worker_done","status":"complete","worker_sequence":3}',
        ]
    )
    connector = SequencedConnector(first, second)
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == ["done"]
    assert executor.reads == 1
    assert json.loads(second.sent[0])["afterSequence"] == 0
    assert json.loads(first.sent[1]) == json.loads(second.sent[1])
    assert [json.loads(frame)["type"] for frame in second.sent] == [
        "attach_turn",
        "tool_result",
        "ack_terminal",
    ]


def test_external_pi_runner_does_not_resend_resolved_tool_result_after_later_loss():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
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
    tool = (
        '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
        '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,'
        '"max_bytes":1024,"worker_sequence":1}'
    )
    first = FakeSocket(
        [
            tool,
            '{"type":"workspace_ready","worker_sequence":2}',
            OSError("later link loss"),
        ]
    )
    second = FakeSocket(
        [
            '{"type":"done","finish_reason":"success","followups":[],"worker_sequence":3}',
            '{"type":"worker_done","status":"complete","worker_sequence":4}',
        ]
    )
    connector = SequencedConnector(first, second)
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        provider=provider,
        executor=executor,
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(worker_status(claim)),
        session_factory=SessionContext,
    )

    assert [event["type"] for event in asyncio.run(_collect(runner))] == [
        "workspace_ready",
        "done",
    ]
    assert executor.reads == 1
    assert [json.loads(frame)["type"] for frame in second.sent] == [
        "attach_turn",
        "ack_terminal",
    ]
    assert json.loads(second.sent[0])["afterSequence"] == 2


def test_external_pi_runner_classifies_exact_worker_loss_without_new_model_run():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    replacement = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 8, "release-b", "external-pi-v1"
    )
    statuses = iter([worker_status(claim), worker_status(replacement)])
    socket = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("worker lost")]
    )
    connector = SequencedConnector(socket)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=lambda: _async_value(next(statuses)),
        session_factory=SessionContext,
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "external_worker_lost",
            "message": "The research run was interrupted.",
        },
    ]
    assert len(connector.calls) == 1


@pytest.mark.parametrize(
    "status_error",
    [
        ExternalPiWorkerUnavailable("worker unavailable"),
        ExternalPiWorkerControlRejected("malformed worker status"),
    ],
    ids=["unavailable", "malformed-or-rejected"],
)
def test_external_pi_runner_classifies_status_control_failure_as_worker_loss(
    status_error,
):
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )
    statuses = iter([worker_status(claim), status_error])

    async def resolve_status():
        status = next(statuses)
        if isinstance(status, BaseException):
            raise status
        return status

    socket = FakeSocket(
        ['{"type":"workspace_ready","worker_sequence":1}', OSError("link lost")]
    )
    connector = SequencedConnector(socket)
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=resolve_status,
        session_factory=SessionContext,
    )

    assert asyncio.run(_collect(runner)) == [
        {"type": "workspace_ready"},
        {
            "type": "error",
            "code": "external_worker_lost",
            "message": "The research run was interrupted.",
        },
    ]
    assert len(connector.calls) == 1


@pytest.mark.parametrize(
    "status_error",
    [
        ExternalPiWorkerUnavailable("worker unavailable"),
        ExternalPiWorkerControlRejected("malformed worker status"),
    ],
)
def test_external_pi_detached_cancel_tolerates_status_control_failure(status_error):
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
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
    claim = ExternalWorkerClaim(
        "external-pi-1", uuid.uuid4(), 7, "release-a", "external-pi-v1"
    )

    async def rejected_status():
        raise status_error

    connector = SequencedConnector()
    runner = ExternalPiChatTurnRunner(
        settings=settings,
        admission=admission,
        prompt="answer",
        request_id="request-1",
        resume_id=None,
        capability=IssuedCapability(
            token="opaque-capability",
            capability_id=None,
            expires_at=datetime.now(UTC) + timedelta(minutes=1),
        ),
        hf_username="qualification",
        websocket_connector=connector,
        worker_repository=FakeWorkerRepository(claim),
        worker_status_resolver=rejected_status,
        session_factory=SessionContext,
    )
    runner.external_worker_claim = claim

    asyncio.run(runner.cancel())
    assert connector.calls == []
