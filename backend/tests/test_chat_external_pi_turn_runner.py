import asyncio
from datetime import UTC, datetime, timedelta
import uuid

from backend.config import get_settings
from backend.services.chat_capability_service import IssuedCapability
from backend.services.chat_external_pi_turn_runner import ExternalPiChatTurnRunner
from backend.services.chat_sandbox_executor import ExecutorReadResult
from backend.services.chat_session_service import TurnAdmission


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
            return next(self.messages)
        except StopIteration:
            raise StopAsyncIteration from None


class SocketContext:
    def __init__(self, socket):
        self.socket = socket

    async def __aenter__(self):
        return self.socket

    async def __aexit__(self, *_args):
        return None


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

    async def ensure_workspace(self, context):
        self.contexts.append(context)

    async def read_file(self, context, *, path, offset, max_bytes):
        self.contexts.append(context)
        assert path == "/opt/pwc/PWC_CLI_SKILL.md"
        return ExecutorReadResult(path=path, offset=offset, data=b"guide", eof=True)


def test_external_pi_runner_lazily_creates_executor_for_remote_read():
    settings = get_settings().model_copy(deep=True)
    settings.environment = "staging"
    settings.chat_external_pi_worker_url = "http://127.0.0.1:8766"
    provider = FakeProvider()
    executor = FakeExecutor()
    socket = FakeSocket(
        [
            '{"type":"tool_request","operation_id":"operation-1","tool_call_id":"tool-1",'
            '"operation":"read","path":"/opt/pwc/PWC_CLI_SKILL.md","offset":0,"max_bytes":1024}',
            '{"type":"workspace_ready"}',
            '{"type":"done","finish_reason":"success","followups":[]}',
            '{"type":"worker_done","status":"complete"}',
        ]
    )
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
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
            '{"type":"workspace_ready"}',
            '{"type":"done","finish_reason":"success","followups":[]}',
            '{"type":"worker_done","status":"complete"}',
        ]
    )
    admission = TurnAdmission(
        session_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        user_message_id=uuid.uuid4(),
        selected_model="test",
        model_route=settings.chat_deepseek_v4_flash_route,
        sdk_session_id=None,
        sdk_project_key=None,
        agent_harness="pi",
        execution_backend="modal_cli",
        reasoning_effort="low",
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
    )

    async def exercise():
        events = [event["type"] async for event in runner.events()]
        await runner.close()
        return events

    assert asyncio.run(exercise()) == ["workspace_ready", "done"]
    assert provider.created == []
