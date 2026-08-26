import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.models.database import ChatExternalWorker
from backend.services.chat_external_worker_registry import (
    ChatExternalWorkerRegistry,
    ChatExternalWorkerRepository,
    StaleWorkerClaim,
    WorkerLeaseUnavailable,
)


def test_worker_restart_can_replace_only_an_expired_instance_lease():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, first = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.register(
            row,
            worker_id="worker-1",
            instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
            release_id="release-a",
            contract_version="external-pi-v1",
            maximum_sessions=8,
            now=now + timedelta(seconds=14),
            lease_seconds=15,
        )

    row, replacement = registry.register(
        row,
        worker_id="worker-1",
        instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        release_id="release-b",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    assert first.generation == 1
    assert replacement.generation == 2
    assert row.instance_id == replacement.instance_id
    assert row.release_id == "release-b"
    assert row.state == "ready"
    assert row.lease_expires_at == now + timedelta(seconds=30)


def test_heartbeat_and_drain_require_the_current_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, stale = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    row, current = registry.register(
        row,
        worker_id="worker-1",
        instance_id=uuid.UUID("20000000-0000-4000-8000-000000000001"),
        release_id="release-b",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    with pytest.raises(StaleWorkerClaim):
        registry.heartbeat(
            row,
            claim=stale,
            active_sessions=1,
            now=now + timedelta(seconds=16),
            lease_seconds=15,
        )

    registry.heartbeat(
        row,
        claim=current,
        active_sessions=3,
        now=now + timedelta(seconds=16),
        lease_seconds=15,
    )
    registry.begin_drain(
        row,
        claim=current,
        now=now + timedelta(seconds=17),
        drain_seconds=20,
    )

    assert row.active_sessions == 3
    assert row.state == "draining"
    assert row.lease_expires_at == now + timedelta(seconds=37)
    registry.heartbeat(
        row,
        claim=current,
        active_sessions=2,
        now=now + timedelta(seconds=18),
        lease_seconds=15,
    )
    assert row.active_sessions == 2
    assert row.lease_expires_at == now + timedelta(seconds=37)

    with pytest.raises(WorkerLeaseUnavailable):
        registry.heartbeat(
            row,
            claim=current,
            active_sessions=3,
            now=now + timedelta(seconds=19),
            lease_seconds=15,
        )


def test_live_registration_retry_preserves_capacity_and_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row, first = registry.register(
        None,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    registry.heartbeat(
        row,
        claim=first,
        active_sessions=3,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )

    row, retried = registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=2),
        lease_seconds=15,
    )

    assert retried == first
    assert row.active_sessions == 3
    assert row.lease_expires_at == now + timedelta(seconds=17)


def test_expired_same_instance_id_is_fenced_with_a_new_generation():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row, stale = registry.register(
        None,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    row, current = registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=15),
        lease_seconds=15,
    )

    assert current.generation == stale.generation + 1
    with pytest.raises(StaleWorkerClaim):
        registry.begin_drain(
            row,
            claim=stale,
            now=now + timedelta(seconds=16),
            drain_seconds=20,
        )


def test_expired_claim_cannot_start_or_finish_a_drain():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, claim = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.begin_drain(
            row,
            claim=claim,
            now=now + timedelta(seconds=15),
            drain_seconds=20,
        )

    row.state = "draining"
    with pytest.raises(WorkerLeaseUnavailable):
        registry.mark_offline(
            row,
            claim=claim,
            now=now + timedelta(seconds=15),
        )


def test_drained_worker_can_go_offline_only_after_sessions_finish():
    registry = ChatExternalWorkerRegistry(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    row, claim = registry.register(
        None,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )
    registry.heartbeat(
        row,
        claim=claim,
        active_sessions=1,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )
    registry.begin_drain(
        row,
        claim=claim,
        now=now + timedelta(seconds=2),
        drain_seconds=20,
    )

    with pytest.raises(WorkerLeaseUnavailable):
        registry.mark_offline(row, claim=claim, now=now + timedelta(seconds=3))

    registry.heartbeat(
        row,
        claim=claim,
        active_sessions=0,
        now=now + timedelta(seconds=4),
        lease_seconds=15,
    )
    registry.mark_offline(row, claim=claim, now=now + timedelta(seconds=5))

    assert row.state == "offline"
    assert row.lease_expires_at == now + timedelta(seconds=5)


def test_repository_serializes_and_persists_registration(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    db = Mock()
    monkeypatch.setattr(repository, "load", Mock(return_value=None))
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)

    claim = repository.register(
        db,
        worker_id="worker-1",
        instance_id=uuid.UUID("10000000-0000-4000-8000-000000000001"),
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now,
        lease_seconds=15,
    )

    added = db.add.call_args.args[0]
    assert isinstance(added, ChatExternalWorker)
    assert added.worker_id == claim.worker_id
    assert added.instance_id == claim.instance_id
    assert added.generation == claim.generation == 1
    assert added.active_sessions == 0
    assert db.execute.call_count == 1
    db.flush.assert_called_once_with()


def test_repository_persists_heartbeat_and_graceful_drain(monkeypatch):
    repository = ChatExternalWorkerRepository(environment="staging")
    now = datetime(2026, 8, 26, 12, tzinfo=UTC)
    instance_id = uuid.UUID("10000000-0000-4000-8000-000000000001")
    row = ChatExternalWorker(
        worker_id="worker-1",
        instance_id=instance_id,
        environment="staging",
        release_id="release-a",
        contract_version="external-pi-v1",
        generation=4,
        state="ready",
        maximum_sessions=8,
        active_sessions=1,
        heartbeat_at=now,
        lease_expires_at=now + timedelta(seconds=15),
        created_at=now,
        updated_at=now,
    )
    claim = repository.registry.register(
        row,
        worker_id="worker-1",
        instance_id=instance_id,
        release_id="release-a",
        contract_version="external-pi-v1",
        maximum_sessions=8,
        now=now + timedelta(seconds=1),
        lease_seconds=15,
    )[1]
    monkeypatch.setattr(repository, "load", Mock(return_value=row))
    db = Mock()

    repository.heartbeat(
        db,
        claim=claim,
        active_sessions=1,
        now=now + timedelta(seconds=2),
        lease_seconds=15,
    )
    repository.begin_drain(
        db,
        claim=claim,
        now=now + timedelta(seconds=3),
        drain_seconds=20,
    )
    repository.heartbeat(
        db,
        claim=claim,
        active_sessions=0,
        now=now + timedelta(seconds=4),
        lease_seconds=15,
    )
    repository.mark_offline(
        db,
        claim=claim,
        now=now + timedelta(seconds=5),
    )

    assert row.state == "offline"
    assert row.active_sessions == 0
    assert row.lease_expires_at == now + timedelta(seconds=5)
    assert db.flush.call_count == 4


def test_worker_registry_migration_is_additive_and_environment_scoped():
    migration = (
        Path(__file__).parents[1]
        / "database/migrations/add_chat_external_worker_registry.sql"
    ).read_text()

    assert "CREATE TABLE IF NOT EXISTS chat_external_workers" in migration
    assert "current_schema() NOT IN ('staging', 'public')" in migration
    assert "PRIMARY KEY" in migration
    assert "instance_id UUID NOT NULL UNIQUE" in migration
    assert "generation BIGINT NOT NULL" in migration
    assert "state IN ('ready', 'draining', 'offline')" in migration
    assert "REVOKE ALL ON chat_external_workers FROM paperswithcode_user" in migration
