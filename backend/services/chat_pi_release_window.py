"""Fail-closed qualification gate for admin Pi session assignment."""

from __future__ import annotations

import json
from pathlib import Path

from backend.chat_sandbox_worker.contract import (
    DATABASE_CONTRACT_VERSION,
    GATEWAY_CONTRACT_VERSION,
    MODAL_IMAGE_ID,
    WORKER_CONTRACT_VERSION,
)


class PiReleaseWindowUnavailable(RuntimeError):
    """The active immutable rollback window cannot yet serve Pi sessions."""


def require_pi_release_window(
    environment_root: Path = Path("/srv/paperswithcode/environments/staging"),
) -> None:
    """Require both current and previous releases to serve the exact Pi contract."""

    for pointer in ("current", "previous"):
        manifest_path = environment_root / pointer / "release.json"
        try:
            runtime = json.loads(manifest_path.read_text(encoding="utf-8"))[
                "chat_runtime"
            ]
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise PiReleaseWindowUnavailable(
                "Pi qualification requires two compatible staging releases."
            ) from exc
        expected = {
            "database_contract_version": DATABASE_CONTRACT_VERSION,
            "gateway_contract_version": GATEWAY_CONTRACT_VERSION,
            "modal_image_version": MODAL_IMAGE_ID,
            "worker_contract_version": WORKER_CONTRACT_VERSION,
        }
        if any(
            runtime.get(key) != value for key, value in expected.items()
        ) or runtime.get("supported_agent_harnesses") != ["claude", "pi"]:
            raise PiReleaseWindowUnavailable(
                "Pi qualification requires two compatible staging releases."
            )
