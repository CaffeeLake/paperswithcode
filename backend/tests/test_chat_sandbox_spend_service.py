from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.config import Settings
from backend.models.database import (
    ChatSandboxBudgetState,
    ChatSandboxCircuitEvent,
    ChatSandboxComputeInterval,
)
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
    billing_cycle,
)


def factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    for table in (
        ChatSandboxBudgetState.__table__,
        ChatSandboxComputeInterval.__table__,
        ChatSandboxCircuitEvent.__table__,
    ):
        table.create(engine, checkfirst=True)
    return sessionmaker(engine, expire_on_commit=False)


def settings(**values):
    return Settings(
        **{
            "environment": "staging",
            "release_id": "release",
            "chat_modal_image_version": "im-test",
            "chat_sandbox_spend_enforcement_enabled": True,
            "chat_sandbox_budget_attestation": "attested",
            "chat_sandbox_warning_microusd": 75_000_000,
            "chat_sandbox_application_cap_microusd": 100_000_000,
            "chat_sandbox_environment_cap_microusd": 125_000_000,
            "chat_sandbox_workspace_cap_microusd": 250_000_000,
            "chat_sandbox_cpu": 1,
            "chat_sandbox_cpu_limit": 1,
            "chat_sandbox_memory_mib": 2048,
            "chat_sandbox_memory_limit_mib": 2048,
            **values,
        }
    )


def test_lifecycle_meter_includes_reservation_to_confirmed_termination():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="direct", worker_generation="generation", now=start
        )
        service.provider_created(interval_id, "sb-1", start + timedelta(seconds=5))
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.refresh(start + timedelta(seconds=65))
        assert state.estimated_accrued_microusd == 65 * service.cost_per_second()
        service.terminate(
            "sb-1", "complete", confirmed=True, now=start + timedelta(seconds=70)
        )
        state = service.refresh(start + timedelta(seconds=90))
        assert state.estimated_accrued_microusd == 70 * service.cost_per_second()
        assert state.outstanding_reservation_microusd == 0


def test_claim_preserves_one_continuous_pool_interval():
    sessions = factory()
    start = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        interval_id = service.reserve_interval(
            origin="blank_pool", worker_generation="generation", now=start
        )
        service.provider_created(interval_id, "sb-pool", start)
        import uuid

        session_id = uuid.uuid4()
        service.claim("sb-pool", session_id, start + timedelta(seconds=20))
        service.claim("sb-pool", session_id, start + timedelta(seconds=30))
        rows = list(db.execute(select(ChatSandboxComputeInterval)).scalars())
        assert len(rows) == 1
        assert rows[0].reserved_at.replace(tzinfo=UTC) == start
        assert rows[0].claimed_at.replace(tzinfo=UTC) == start + timedelta(seconds=20)


def test_provider_floor_is_monotonic_and_trips_at_cap():
    sessions = factory()
    now = datetime(2026, 8, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.reconcile_provider_floor(100_000_000, now)
        assert state.provider_floor_microusd == 100_000_000
        assert state.circuit_state == "tripped"
        with pytest.raises(ChatComputeDisabled):
            service.assert_available(now)


def test_reservations_trip_before_aggregate_headroom_is_oversubscribed():
    sessions = factory()
    now = datetime(2026, 8, 1, tzinfo=UTC)
    constrained = settings(
        chat_sandbox_warning_microusd=100_000,
        chat_sandbox_application_cap_microusd=1_500_000,
        chat_sandbox_environment_cap_microusd=2_000_000,
        chat_sandbox_workspace_cap_microusd=3_000_000,
    )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, constrained)
        service.reserve_interval(origin="direct", worker_generation="first", now=now)
        with pytest.raises(ChatComputeDisabled):
            service.reserve_interval(
                origin="direct", worker_generation="second", now=now
            )
        assert service.refresh(now).circuit_state == "tripped"


def test_spend_trip_rearms_once_after_provider_confirms_new_utc_cycle():
    sessions = factory()
    august = datetime(2026, 8, 31, 23, 59, tzinfo=UTC)
    september = datetime(2026, 9, 1, 0, 1, tzinfo=UTC)
    with sessions() as db, db.begin():
        ChatSandboxSpendService(db, settings()).reconcile_provider_floor(
            100_000_000, august
        )
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        state = service.reconcile_provider_floor(0, september)
        assert state.billing_cycle.isoformat() == "2026-09-01"
        assert state.circuit_state == "armed"
        events = list(
            db.execute(
                select(ChatSandboxCircuitEvent).where(
                    ChatSandboxCircuitEvent.budget_state_id == state.id,
                    ChatSandboxCircuitEvent.event_type == "cycle_rearmed",
                )
            ).scalars()
        )
        assert len(events) == 1


def test_tagged_provider_orphan_is_conservatively_added_to_ledger():
    sessions = factory()
    now = datetime(2026, 8, 3, tzinfo=UTC)
    with sessions() as db, db.begin():
        service = ChatSandboxSpendService(db, settings())
        service.terminate(
            "sb-orphan", "termination_uncertain", confirmed=False, now=now
        )
        row = db.execute(
            select(ChatSandboxComputeInterval).where(
                ChatSandboxComputeInterval.modal_sandbox_id == "sb-orphan"
            )
        ).scalar_one()
        assert row.origin == "reconciled_orphan"
        assert row.terminal_at is None
        assert row.reserved_microusd == service.reservation_amount()
        assert row.reconciliation_state == "termination_uncertain"


def test_billing_cycle_is_utc_and_rejects_naive_time():
    assert (
        billing_cycle(datetime(2026, 8, 31, 23, tzinfo=UTC)).isoformat() == "2026-08-01"
    )
    with pytest.raises(ValueError):
        billing_cycle(datetime(2026, 8, 1))  # noqa: DTZ001 - verifies rejection
