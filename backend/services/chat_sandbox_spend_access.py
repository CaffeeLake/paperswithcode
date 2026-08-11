"""Transaction boundaries for sandbox spend admission and status reads."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.config import Settings
from backend.services.chat_sandbox_spend_service import (
    ChatComputeDisabled,
    ChatSandboxSpendService,
)

SessionFactory = Callable[[], Session]
SpendFactory = Callable[[Session], ChatSandboxSpendService]


def assert_chat_sandbox_spend_available(
    settings: Settings,
    *,
    session_factory: SessionFactory,
    spend_factory: SpendFactory | None = None,
) -> None:
    """Commit circuit transitions on both admission and policy rejection."""

    create_spend = spend_factory or (lambda db: ChatSandboxSpendService(db, settings))
    with session_factory() as db:
        try:
            create_spend(db).assert_available()
        except ChatComputeDisabled:
            db.commit()
            raise
        db.commit()


def chat_sandbox_spend_status(
    settings: Settings,
    *,
    session_factory: SessionFactory,
    spend_factory: SpendFactory | None = None,
) -> dict:
    """Read and persist the refreshed spend state in one transaction."""

    create_spend = spend_factory or (lambda db: ChatSandboxSpendService(db, settings))
    with session_factory() as db, db.begin():
        return create_spend(db).status()
