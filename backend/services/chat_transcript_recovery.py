"""Reconcile bounded local SDK recovery spools after mirror failures."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from backend.config import Settings
from backend.services.postgres_sdk_session_store import PostgresSDKSessionStore


def _read_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("SDK transcript entry must be an object")
                entries.append(value)
    return entries


async def reconcile_spooled_session(
    settings: Settings,
    store: PostgresSDKSessionStore,
    *,
    project_key: str,
    sdk_session_id: uuid.UUID,
) -> bool:
    """Replay and verify one spooled main transcript plus all subpaths."""

    spool = Path(settings.chat_recovery_spool_dir)
    if not spool.is_dir():
        return False
    candidates = sorted(
        spool.glob(f"*/projects/{project_key}/{sdk_session_id}.jsonl"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return False

    main_path = candidates[0]
    recovery_root = main_path.parents[2]
    main_key = {"project_key": project_key, "session_id": str(sdk_session_id)}
    main_entries = _read_jsonl(main_path)
    await store.append(main_key, main_entries)

    session_dir = main_path.with_suffix("")
    if session_dir.is_dir():
        for subpath_file in sorted(session_dir.rglob("*.jsonl")):
            relative = subpath_file.relative_to(session_dir).with_suffix("")
            key = {**main_key, "subpath": relative.as_posix()}
            await store.append(key, _read_jsonl(subpath_file))

    restored = await store.load(main_key)
    if restored != main_entries:
        return False
    if recovery_root.parent == spool:
        shutil.rmtree(recovery_root)
    return True
