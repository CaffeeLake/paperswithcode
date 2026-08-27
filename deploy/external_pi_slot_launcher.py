#!/usr/bin/env python3
"""Exec one staging slot's external Pi worker from recorded runtimes only."""

from __future__ import annotations

import os
import sys
import uuid

try:
    from deploy.external_pi_slot_lifecycle import (
        node_environment,
        resolve_external_pi_slot,
        supervisor_environment,
    )
    from deploy.slot_launcher import resolve_slot
except ModuleNotFoundError:
    from external_pi_slot_lifecycle import (  # type: ignore[no-redef]
        node_environment,
        resolve_external_pi_slot,
        supervisor_environment,
    )
    from slot_launcher import resolve_slot  # type: ignore[no-redef]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: external_pi_slot_launcher.py staging SLOT")
    environment, slot = sys.argv[1:]
    release, python_runtime, manifest = resolve_slot(environment, slot)
    resolved = resolve_external_pi_slot(environment, slot)
    if resolved.release != release or resolved.release_id != manifest["release_id"]:
        raise ValueError("external Pi and backend slot releases disagree")
    protected = dict(os.environ)
    child_env = supervisor_environment(resolved, protected)
    child_env.update(
        node_environment(resolved, protected, instance_id=str(uuid.uuid4()))
    )
    child_env.update(
        {
            "PWC_EXTERNAL_PI_NODE": str(resolved.node),
            "PWC_EXTERNAL_PI_ENTRY_POINT": str(resolved.entry_point),
        }
    )
    python = python_runtime / "bin/python"
    os.chdir(release)
    os.execve(
        str(python),
        [str(python), "-m", "backend.scripts.run_external_pi_slot"],
        child_env,
    )


if __name__ == "__main__":
    main()
