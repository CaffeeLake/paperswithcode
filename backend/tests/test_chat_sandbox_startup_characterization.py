from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest

from backend.services import chat_sandbox_service
from backend.services.chat_sandbox_service import SandboxError, SandboxSessionManager


class _Transaction:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class _DB(_Transaction):
    def begin(self):
        return _Transaction()


def test_sandbox_provider_startup_timeout_marks_claim_and_uses_stable_error_code(
    monkeypatch,
):
    async def scenario():
        manager = SandboxSessionManager.__new__(SandboxSessionManager)
        manager.settings = SimpleNamespace(
            chat_sandbox_spend_enforcement_enabled=False,
            chat_blank_pool_enabled=False,
            chat_sandbox_admission_enabled=True,
            chat_sandbox_ready_timeout_seconds=0.01,
            chat_persistent_worker_enabled=False,
            chat_workspace_snapshots_enabled=False,
            release_id="release-test",
            chat_modal_image_version="im-test",
            chat_worker_contract_version="worker-v1",
        )
        manager.session_factory = _DB
        manager._lock_start_claim = lambda *_args: None
        lease = SimpleNamespace(
            state="terminated",
            modal_sandbox_id=None,
            image_version="im-test",
            worker_contract_version="worker-v1",
            worker_generation="old-generation",
            workspace_snapshot_id=None,
            snapshot_image_version=None,
            snapshot_updated_at=None,
            lease_token_hash=None,
            lease_expires_at=None,
            failure_code=None,
            updated_at=None,
        )
        manager._lease = lambda *_args, **_kwargs: lease

        async def enforce_warm_cap():
            return 0

        manager.enforce_warm_cap = enforce_warm_cap
        failures = []
        manager._mark_start_failed = lambda *args: failures.append(args) or True
        provider_calls = []

        async def never_finishes(*_args, **kwargs):
            provider_calls.append(kwargs)
            await asyncio.Future()

        monkeypatch.setattr(
            chat_sandbox_service,
            "create_isolated_sandbox",
            never_finishes,
        )
        session_id = uuid.uuid4()

        with pytest.raises(SandboxError) as exc_info:
            await manager.ensure_ready(session_id)

        assert exc_info.value.code == "sandbox_timeout"
        assert str(exc_info.value) == "Secure workspace startup timed out"
        assert exc_info.value.uncertain is False
        assert len(provider_calls) == 1
        assert failures == [(session_id, lease.lease_token_hash, "sandbox_timeout")]

    asyncio.run(scenario())
