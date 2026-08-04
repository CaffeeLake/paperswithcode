from __future__ import annotations

import asyncio
import socket
import urllib.error
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import backend.services.deployment_lifecycle as lifecycle_module
import backend.services.postgres_sdk_session_store as postgres_store_module
import deploy.cli as deploy_cli
import deploy.nginx_tool as nginx_tool_module
import deploy.runtime as runtime_module
import deploy.topology_audit as topology_audit_module
from backend.chat_sandbox_worker import agent
from backend.chat_sandbox_worker.remote_store import RemoteSessionStore, RetryPolicy
from backend.config import get_settings
from backend.main import create_app
from backend.services.deployment_lifecycle import (
    DeploymentAccountingMiddleware,
    DeploymentLifecycle,
)
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore
from backend.utils.auth import require_user
from deploy.nginx_validate import validate as validate_nginx
from deploy.release import atomic_symlink, validate_rolling_compatibility
from deploy.runtime import prepare_runtime, runtime_id, runtime_manifest


def test_accounting_covers_complete_streaming_body(
    monkeypatch: pytest.MonkeyPatch,
):
    lifecycle = DeploymentLifecycle()
    monkeypatch.setattr(lifecycle_module, "deployment_lifecycle", lifecycle)

    async def exercise() -> None:
        started = asyncio.Event()
        finish = asyncio.Event()

        async def streaming_app(scope, receive, send):
            await send({"type": "http.response.start", "status": 200, "headers": []})
            started.set()
            await finish.wait()
            await send({"type": "http.response.body", "body": b"done"})

        middleware = DeploymentAccountingMiddleware(streaming_app)
        task = asyncio.create_task(
            middleware(
                {"type": "http", "path": "/api/v1/chat/stream"},
                lambda: None,
                lambda _message: asyncio.sleep(0),
            )
        )
        await started.wait()
        status = lifecycle.status()
        assert status.active_http_requests == 1
        assert status.active_chat_streams == 1
        finish.set()
        await task
        assert lifecycle.status().active_http_requests == 0
        assert lifecycle.status().active_chat_streams == 0

    asyncio.run(exercise())


def test_drain_is_idempotent_and_blocks_only_new_admission():
    lifecycle = DeploymentLifecycle()
    with lifecycle.request("/api/v1/chat/stream"):
        drained = lifecycle.drain()
        assert not drained.accepting_chat_turns
        assert drained.active_chat_streams == 1
        assert lifecycle.drain().drain_started_at == drained.drain_started_at
    assert lifecycle.status().active_chat_streams == 0
    assert lifecycle.undrain().accepting_chat_turns


def test_draining_chat_endpoint_returns_retry_after(
    monkeypatch: pytest.MonkeyPatch,
):
    settings = get_settings()
    monkeypatch.setattr(settings, "chat_enabled", True)
    monkeypatch.setattr(settings, "hf_token", "test-token")
    app = create_app()
    app.dependency_overrides[require_user] = lambda: {
        "hf_user_id": "user-1",
        "username": "user",
    }
    lifecycle_module.deployment_lifecycle.drain()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/chat/stream",
                json={"message": "hello", "client_message_id": "message-1"},
            )
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "3"
    finally:
        lifecycle_module.deployment_lifecycle.undrain()


def test_unix_operator_endpoints_have_request_injected(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("PWC_DEPLOY_TESTING", "1")
    app = create_app()
    with TestClient(app) as client:
        status = client.get("/internal/deployment-status")
        drained = client.post("/internal/drain")
        not_ready = client.get("/internal/ready")
        undrained = client.post("/internal/undrain")
    assert status.status_code == 200
    assert drained.status_code == 200
    assert not_ready.status_code == 503
    assert undrained.status_code == 200


def test_operator_endpoints_require_exact_unix_listener(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("PWC_DEPLOY_TESTING", raising=False)
    socket_path = tmp_path / "staging-blue.sock"
    socket_alias = tmp_path / "slot" / "backend.sock"
    socket_alias.parent.mkdir()
    socket_alias.symlink_to(socket_path)
    monkeypatch.setenv("PWC_BACKEND_SOCKET", str(socket_alias))

    assert lifecycle_module.operator_socket_allowed(
        {"server": (str(socket_path), None)}
    )
    assert lifecycle_module.operator_socket_allowed({"server": str(socket_alias)})
    assert not lifecycle_module.operator_socket_allowed({"server": ("127.0.0.1", 8001)})
    assert not lifecycle_module.operator_socket_allowed(
        {"server": (str(tmp_path / "staging-green.sock"), None)}
    )
    assert not lifecycle_module.operator_socket_allowed({"server": None})


def test_topology_audit_ignores_its_own_checkout_interpreter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_output(command: list[str]) -> str:
        if command[:3] == ["ps", "-eo", "user,pid,args"]:
            return (
                "root 123 /root/python_projects/paperswithcode/.venv/bin/python "
                "deploy/topology_audit.py --json\n"
            )
        return ""

    monkeypatch.setattr(topology_audit_module, "output", fake_output)

    result = topology_audit_module.audit(tmp_path)

    assert "running process references developer checkout" not in result["findings"]


def test_immutable_runtime_build_reuse_and_failed_cleanup(tmp_path: Path):
    release = tmp_path / "release"
    release.mkdir()
    (release / "uv.lock").write_text("lock")
    runtimes = tmp_path / "runtimes"
    builds = 0

    def build(command, *, env, check):
        nonlocal builds
        builds += 1
        target = Path(env["UV_PROJECT_ENVIRONMENT"])
        (target / "bin").mkdir()
        (target / "bin" / "python").symlink_to("/usr/bin/python3")
        (target / "lib").mkdir()
        (target / "lib" / "module.py").write_text("value = 1\n")

    def version(*args, **kwargs):
        return SimpleNamespace(stdout="Python 3.12.11\n")

    first, created = prepare_runtime(
        release, runtimes, runner=build, version_runner=version
    )
    assert created
    assert runtime_manifest(first)["lock_sha256"] == first.name
    assert first.stat().st_mode & 0o222 == 0
    assert (first / "runtime.json").stat().st_mode & 0o222 == 0
    assert (first / "lib" / "module.py").stat().st_mode & 0o222 == 0
    second, created = prepare_runtime(
        release, runtimes, runner=build, version_runner=version
    )
    assert second == first
    assert not created
    assert builds == 1

    other = tmp_path / "other"
    other.mkdir()
    (other / "uv.lock").write_text("different")

    def fail(*args, **kwargs):
        raise OSError("build failed")

    with pytest.raises(OSError, match="build failed"):
        prepare_runtime(other, runtimes, runner=fail, version_runner=version)
    assert not any(path.name.startswith(".") for path in runtimes.iterdir())


def test_runtime_builder_uses_stable_absolute_uv_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    release = tmp_path / "release"
    release.mkdir()
    (release / "uv.lock").write_text("lock")
    uv = tmp_path / "uv"
    uv.write_text("binary")
    monkeypatch.setattr(runtime_module, "UV_BINARY", uv)
    command_seen: list[str] = []

    def build(command, *, env, check):
        command_seen.extend(command)
        assert env["UV_PYTHON"] == "/usr/bin/python3"
        assert env["UV_PYTHON_PREFERENCE"] == "only-system"
        assert env["UV_LINK_MODE"] == "copy"
        target = Path(env["UV_PROJECT_ENVIRONMENT"])
        (target / "bin").mkdir()
        (target / "bin" / "python").symlink_to("/usr/bin/python3")

    def version(*args, **kwargs):
        return SimpleNamespace(stdout="Python 3.12.11\n")

    prepare_runtime(
        release,
        tmp_path / "runtimes",
        runner=build,
        version_runner=version,
    )
    assert command_seen[0] == str(uv)


@pytest.mark.parametrize("environment", ["production", "staging"])
def test_legacy_bridge_flag_is_explicit_on_deploy_parser(environment: str):
    parser = deploy_cli.parser_for("pwc-deploy")
    args = parser.parse_args([environment, "a" * 40, "--legacy-bridge"])
    assert args.legacy_bridge is True
    assert args.qualify_only is False


def _contract(emits: int, accepts: int, database: int = 1) -> dict:
    return {
        "chat_runtime": {
            "gateway_contract_version": emits,
            "gateway_compatible_from": accepts,
            "database_contract_version": database,
        }
    }


def test_rolling_contract_requires_forward_and_rollback_compatibility():
    validate_rolling_compatibility(_contract(26, 25), _contract(26, 26))
    with pytest.raises(ValueError, match="rollback"):
        validate_rolling_compatibility(_contract(26, 26), _contract(27, 26))
    with pytest.raises(ValueError, match="database"):
        validate_rolling_compatibility(_contract(26, 26), _contract(26, 26, 2))


def test_active_symlink_switch_keeps_existing_unix_connection(tmp_path: Path):
    slot_a = tmp_path / "blue"
    slot_b = tmp_path / "green"
    slot_a.mkdir()
    slot_b.mkdir()
    socket_a_path = tmp_path / "a.sock"
    socket_b_path = tmp_path / "b.sock"
    (slot_a / "backend.sock").symlink_to(socket_a_path)
    (slot_b / "backend.sock").symlink_to(socket_b_path)
    listener_a = socket.socket(socket.AF_UNIX)
    listener_b = socket.socket(socket.AF_UNIX)
    listener_a.bind(str(socket_a_path))
    listener_b.bind(str(socket_b_path))
    listener_a.listen()
    listener_b.listen()
    try:
        active = tmp_path / "active"
        atomic_symlink(slot_a, active)
        client_a = socket.socket(socket.AF_UNIX)
        client_a.connect(str(active / "backend.sock"))
        server_a, _ = listener_a.accept()
        atomic_symlink(slot_b, active)
        client_b = socket.socket(socket.AF_UNIX)
        client_b.connect(str(active / "backend.sock"))
        server_b, _ = listener_b.accept()
        try:
            server_a.sendall(b"old")
            server_b.sendall(b"new")
            assert client_a.recv(3) == b"old"
            assert client_b.recv(3) == b"new"
        finally:
            client_a.close()
            client_b.close()
            server_a.close()
            server_b.close()
    finally:
        listener_a.close()
        listener_b.close()


def test_remote_store_retries_transient_but_not_permanent_errors():
    store = RemoteSessionStore(
        retry_policy=RetryPolicy(
            total_deadline_seconds=1,
            initial_delay_seconds=0,
            maximum_delay_seconds=0,
        )
    )
    calls = 0

    def ambiguous(_payload):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise urllib.error.HTTPError("http://store", 503, "unavailable", {}, None)
        return {"ok": True}

    store._request_once = ambiguous
    assert store._request({"action": "append"}) == {"ok": True}
    assert calls == 2

    calls = 0

    def permanent(_payload):
        nonlocal calls
        calls += 1
        raise urllib.error.HTTPError("http://store", 403, "forbidden", {}, None)

    store._request_once = permanent
    with pytest.raises(urllib.error.HTTPError):
        store._request({"action": "append"})
    assert calls == 1


def test_ambiguous_append_retry_does_not_refold_or_recount(
    monkeypatch: pytest.MonkeyPatch,
):
    class Result:
        def __init__(self, value=None):
            self.value = value

        def scalar_one_or_none(self):
            return self.value

        def scalar_one(self):
            return self.value

    class Database:
        def __init__(self):
            self.entries: set[str] = set()
            self.summary = SimpleNamespace(
                sdk_session_id=uuid.uuid4(),
                mtime=0,
                data={},
            )

        def execute(self, statement):
            table = getattr(statement, "table", None)
            name = getattr(table, "name", "")
            if name == "chat_sdk_transcript_entries":
                entry_uuid = statement.compile().params["entry_uuid"]
                if entry_uuid in self.entries:
                    return Result(None)
                self.entries.add(entry_uuid)
                return Result(1)
            if name in {"chat_sdk_session_summaries", "chat_sessions"}:
                return Result(None)
            return Result(self.summary)

    database = Database()
    key = {
        "project_key": "project",
        "session_id": str(database.summary.sdk_session_id),
    }
    entry = {"uuid": "entry-1", "type": "assistant", "message": "answer"}
    folds = 0

    def fold(previous, folded_key, inserted):
        nonlocal folds
        folds += 1
        assert previous is None
        assert folded_key == key
        assert inserted == [entry]
        return {"mtime": 0, "data": {"count": 1}}

    monkeypatch.setattr(postgres_store_module, "fold_session_summary", fold)
    first = PostgresSDKSessionStore.append_in_session(database, key, [entry])
    summary_after_first = dict(database.summary.data)
    second = PostgresSDKSessionStore.append_in_session(database, key, [entry])

    assert first > 0
    assert second == 0
    assert folds == 1
    assert database.summary.data == summary_after_first == {"count": 1}


def test_post_result_mirror_failure_carries_bounded_terminal_payload():
    class TerminalAdapter:
        terminal = False

        def feed(self, _message):
            self.terminal = True
            return [
                {
                    "type": "done",
                    "finish_reason": "success",
                    "followups": ["next"],
                }
            ]

    key = {"project_key": "project", "session_id": "session"}

    async def messages():
        yield object()
        yield agent.MirrorErrorMessage(
            subtype="mirror_error",
            data={},
            key=key,
            error="lost",
        )

    async def collect():
        settings = agent.WorkerSettings.from_environment()
        return [
            event
            async for event in agent._adapt_messages(
                messages(),
                request_id="request",
                hooks=agent.WorkerToolHooks(settings),
                adapter=TerminalAdapter(),
            )
        ]

    assert asyncio.run(collect()) == [
        {
            "v": 1,
            "type": "_mirror_error",
            "request_id": "request",
            "key": key,
            "error": "lost",
            "result_available": True,
            "terminal": {
                "v": 1,
                "request_id": "request",
                "type": "done",
                "finish_reason": "success",
                "followups": ["next"],
            },
        }
    ]


def test_checked_in_nginx_uses_matching_active_roots_and_denies_operators():
    root = Path(__file__).resolve().parents[2] / "deploy" / "nginx"
    assert (
        validate_nginx(
            (root / "paperswithcode.co.conf").read_text(),
            (root / "staging.paperswithcode.co.conf").read_text(),
        )
        == []
    )


def test_nginx_transition_smoke_pins_release_and_dedicated_gateway():
    command = nginx_tool_module.smoke_command("staging", "release-staging")

    assert command[0] == "/usr/bin/python3"
    assert command[command.index("--expected-release") + 1] == "release-staging"
    assert command[command.index("--gateway-url") + 1] == (
        "https://chat-gateway-staging.paperswithcode.co/api/internal/chat-gateway"
    )
    production = nginx_tool_module.smoke_command("production", "release-production")
    assert "--gateway-url" not in production


def _activation_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    environments = tmp_path / "environments"
    root = environments / "staging"
    blue = root / "slots" / "blue"
    green = root / "slots" / "green"
    blue.mkdir(parents=True)
    green.mkdir(parents=True)
    old = tmp_path / "old"
    candidate = tmp_path / "candidate"
    older = tmp_path / "older"
    for release in (old, candidate, older):
        release.mkdir()
    atomic_symlink(old, root / "current")
    atomic_symlink(older, root / "previous")
    atomic_symlink(old, blue / "release")
    atomic_symlink(blue, root / "active")
    manifests = {
        release: {
            "release_id": release.name,
            "chat_runtime": {
                "gateway_contract_version": 26,
                "gateway_compatible_from": 26,
                "database_contract_version": 1,
            },
        }
        for release in (old, candidate, older)
    }
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)
    monkeypatch.setattr(
        deploy_cli,
        "validate_manifest",
        lambda release, *_args: manifests[release],
    )
    monkeypatch.setattr(deploy_cli, "_write_journal", lambda *args, **kwargs: None)

    def prepare(_environment, slot, release, _runtime):
        atomic_symlink(release, root / "slots" / slot / "release")
        return {}

    monkeypatch.setattr(deploy_cli, "_prepare_slot", prepare)
    return root, old, candidate, older


def test_live_smoke_failure_restores_complete_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    smokes: list[Path] = []

    def smoke(release, *_args):
        smokes.append(release)
        if release == candidate:
            raise OSError("candidate smoke failed")

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="restored"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older
    assert smokes == [candidate, old]


def test_candidate_failure_leaves_live_activation_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("candidate failed")),
    )

    with pytest.raises(OSError, match="candidate failed"):
        deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_slot_rollback_qualifies_previous_as_one_complete_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)

    result = deploy_cli.activate_slot(older, "staging", tmp_path / "runtime")

    assert result == "success"
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == older
    assert (root / "previous").resolve() == old


def test_draining_previous_slot_is_undrained_and_reused_for_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, _old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    atomic_symlink(candidate, root / "slots" / "green" / "release")
    runtime = tmp_path / "runtime"
    calls: list[tuple[str, str]] = []
    existing = {
        "release_id": "candidate",
        "runtime_id": "runtime",
        "slot": "green",
        "accepting_chat_turns": False,
        "active_http_requests": 1,
    }

    def unix(_environment, _slot, path, *, method="GET", **_kwargs):
        calls.append((method, path))
        return existing

    monkeypatch.setattr(deploy_cli, "_unix_json", unix)
    monkeypatch.setattr(
        deploy_cli,
        "_wait_slot",
        lambda *_args, **_kwargs: {**existing, "accepting_chat_turns": True},
    )
    monkeypatch.setattr(
        deploy_cli,
        "_smoke_slot_candidate",
        lambda *_args, **_kwargs: calls.append(("SMOKE", "candidate")),
    )
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_slot",
        lambda *_args, **_kwargs: pytest.fail("exact rollback slot was restarted"),
    )

    status = deploy_cli._prepare_or_reuse_slot("staging", "green", candidate, runtime)

    assert status["accepting_chat_turns"] is True
    assert calls == [
        ("GET", "/internal/deployment-status"),
        ("POST", "/internal/undrain"),
        ("SMOKE", "candidate"),
    ]


def test_cleanup_retains_every_pointer_and_slot_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    releases = tmp_path / "releases"
    runtimes = tmp_path / "runtimes"
    environments = tmp_path / "environments"
    releases.mkdir()
    runtimes.mkdir()
    protected = {}
    for name in ("current", "previous", "candidate"):
        release = releases / name
        release.mkdir()
        (release / "uv.lock").write_text(f"{name}-lock")
        protected[name] = release
        (runtimes / runtime_id(release)).mkdir()
    stale = releases / "stale"
    stale.mkdir()
    (stale / "uv.lock").write_text("stale-lock")
    stale_runtime = runtimes / runtime_id(stale)
    stale_runtime.mkdir()

    for environment in ("production", "staging"):
        root = environments / environment
        (root / "slots" / "blue").mkdir(parents=True)
        (root / "slots" / "green").mkdir()
        atomic_symlink(protected["current"], root / "current")
        atomic_symlink(protected["previous"], root / "previous")
    atomic_symlink(
        protected["candidate"],
        environments / "staging" / "slots" / "green" / "release",
    )
    monkeypatch.setattr(deploy_cli, "RELEASES", releases)
    monkeypatch.setattr(deploy_cli, "RUNTIMES", runtimes)
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)

    deploy_cli.cleanup_releases()
    runtime_module.cleanup_runtimes(runtimes, deploy_cli.protected_runtime_ids())

    assert {path.name for path in releases.iterdir()} == set(protected)
    assert {path.name for path in runtimes.iterdir()} == {
        runtime_id(release) for release in protected.values()
    }
    assert not stale_runtime.exists()


def test_busy_old_slot_is_retained_after_successful_cutover(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 1,
            "active_chat_streams": 1,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 0)

    result = deploy_cli.activate_slot(candidate, "staging", tmp_path / "runtime")

    assert result == "success-with-draining"
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == candidate
    assert (root / "previous").resolve() == old
    phase, values = journals[-1]
    assert phase == "live-with-old-slot-draining"
    assert values["streams_surviving_cutover"] == {
        "active_http_requests": 1,
        "active_chat_streams": 1,
        "active_gateway_streams": 0,
    }
    assert values["forced_termination_count"] == 0


def test_same_release_finalizes_bridge_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, _older = _activation_fixture(tmp_path, monkeypatch)
    journals: list[tuple[str, dict]] = []
    monkeypatch.setattr(deploy_cli, "_wait_slot", lambda *args, **kwargs: {})
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_write_journal",
        lambda _environment, phase, **values: journals.append((phase, values)),
    )

    result = deploy_cli.activate_slot(old, "staging", tmp_path / "runtime")

    assert result == "success"
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert journals[-1] == (
        "settled",
        {
            "active_slot": "blue",
            "active_release": "old",
            "previous_release": "older",
            "forced_termination_count": 0,
        },
    )


def test_same_release_environment_refresh_restarts_inactive_slot_and_preserves_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    prepared: list[tuple[str, Path]] = []

    def prepare(_environment, slot, release, _runtime):
        prepared.append((slot, release))
        atomic_symlink(release, root / "slots" / slot / "release")
        return {}

    monkeypatch.setattr(deploy_cli, "_prepare_slot", prepare)
    monkeypatch.setattr(
        deploy_cli,
        "_prepare_or_reuse_slot",
        lambda *_args, **_kwargs: pytest.fail("refresh reused a running slot"),
    )
    monkeypatch.setattr(deploy_cli, "smoke_public", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {
            "drain_started_at": "now",
            "active_http_requests": 0,
            "active_chat_streams": 0,
            "active_gateway_streams": 0,
        },
    )
    monkeypatch.setattr(deploy_cli, "_stop_drained_slot", lambda *_args: True)
    monkeypatch.setattr(deploy_cli, "_drain_report_seconds", lambda _environment: 1)

    result = deploy_cli.activate_slot(
        old,
        "staging",
        tmp_path / "runtime",
        refresh_environment=True,
    )

    assert result == "success"
    assert prepared == [("green", old)]
    assert (root / "active").resolve() == (root / "slots" / "green").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_environment_refresh_rejects_a_different_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _root, _old, candidate, _older = _activation_fixture(tmp_path, monkeypatch)

    with pytest.raises(
        deploy_cli.DeployError,
        match="--refresh-environment requires the active release",
    ):
        deploy_cli.activate_slot(
            candidate,
            "staging",
            tmp_path / "runtime",
            refresh_environment=True,
        )


def test_environment_refresh_smoke_failure_restores_active_slot_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, old, _candidate, older = _activation_fixture(tmp_path, monkeypatch)
    smokes = 0

    def smoke(*_args, **_kwargs):
        nonlocal smokes
        smokes += 1
        if smokes == 1:
            raise OSError("refreshed environment failed smoke")

    monkeypatch.setattr(deploy_cli, "smoke_public", smoke)
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )

    with pytest.raises(deploy_cli.DeployError, match="prior activation was restored"):
        deploy_cli.activate_slot(
            old,
            "staging",
            tmp_path / "runtime",
            refresh_environment=True,
        )

    assert smokes == 2
    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older


def test_legacy_service_retires_only_after_nginx_slot_migration(
    monkeypatch: pytest.MonkeyPatch,
):
    commands: list[list[str]] = []
    events: list[tuple] = []
    monkeypatch.setattr(
        deploy_cli, "run", lambda command, **_kwargs: commands.append(command)
    )
    monkeypatch.setattr(
        deploy_cli, "log_event", lambda *args, **kwargs: events.append((args, kwargs))
    )
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: False
    )

    assert not deploy_cli._retire_legacy_service("staging")
    assert commands == []

    states = iter(["active", "inactive"])
    monkeypatch.setattr(
        deploy_cli, "_nginx_uses_active_slot", lambda _environment: True
    )
    monkeypatch.setattr(deploy_cli, "_systemctl_state", lambda _unit: next(states))

    assert deploy_cli._retire_legacy_service("staging")
    assert commands == [["systemctl", "stop", "paperswithcode-backend@staging.service"]]
    assert events == [
        (
            ("legacy-retire", "staging", "success"),
            {"unit": "paperswithcode-backend@staging.service"},
        )
    ]


@pytest.mark.parametrize(
    ("phase", "current_switched", "active_switched"),
    [
        ("previous-update-pending", False, False),
        ("current-update-pending", False, False),
        ("active-switch-pending", True, False),
        ("active-switched-smoke-pending", True, True),
        ("automatic-rollback-in-progress", True, True),
    ],
)
def test_interrupted_cutover_recovers_from_every_mutation_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    current_switched: bool,
    active_switched: bool,
):
    root, old, candidate, older = _activation_fixture(tmp_path, monkeypatch)
    atomic_symlink(candidate, root / "slots" / "green" / "release")
    if current_switched:
        atomic_symlink(candidate, root / "current")
        atomic_symlink(old, root / "previous")
    if active_switched:
        atomic_symlink(root / "slots" / "green", root / "active")
    monkeypatch.setattr(deploy_cli, "RELEASES", tmp_path)
    monkeypatch.setattr(
        deploy_cli,
        "_journal",
        lambda _environment: {
            "phase": phase,
            "old_slot": "blue",
            "old_release": old.name,
            "original_previous": older.name,
        },
    )
    monkeypatch.setattr(
        deploy_cli,
        "_unix_json",
        lambda *args, **kwargs: {"accepting_chat_turns": True},
    )
    smokes: list[Path] = []
    monkeypatch.setattr(
        deploy_cli,
        "smoke_public",
        lambda release, *_args: smokes.append(release),
    )

    deploy_cli._recover_interrupted_activation("staging")

    assert (root / "active").resolve() == (root / "slots" / "blue").resolve()
    assert (root / "current").resolve() == old
    assert (root / "previous").resolve() == older
    assert smokes == [old]
