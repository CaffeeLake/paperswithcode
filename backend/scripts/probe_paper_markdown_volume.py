"""Bounded read/write capability probe for the paper-Markdown bucket mount."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path


def _within(root: Path, value: Path) -> Path:
    root = root.resolve()
    resolved = value.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError("probe path escapes the mounted content root")
    return resolved


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_probe(*, content_root: Path, manifest_path: Path, result_path: Path) -> dict:
    root = content_root.resolve()
    manifest_path = _within(root, manifest_path)
    result_path = _within(root, result_path)
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("invalid capability probe manifest")
    probe_id = str(manifest.get("probe_id") or "")
    nonce = str(manifest.get("nonce") or "")
    if not probe_id.startswith("probe-") or len(nonce) != 32:
        raise ValueError("invalid capability probe identity")

    probe_object = _within(
        root,
        root / "_jobs" / "capabilities" / f"{probe_id}.{uuid.uuid4().hex}.probe",
    )
    payload = f"{probe_id}:{nonce}".encode()
    try:
        atomic_write(probe_object, payload)
        if probe_object.read_bytes() != payload:
            raise ValueError("capability probe verification failed")
    finally:
        probe_object.unlink(missing_ok=True)

    evidence = {
        "schema_version": 1,
        "status": "succeeded",
        "probe_id": probe_id,
        "bucket_id": manifest.get("bucket_id"),
        "namespace": manifest.get("namespace"),
        "mount_path": manifest.get("mount_path"),
        "read_only": manifest.get("read_only"),
        "manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        "temporary_object_cleaned": not probe_object.exists(),
        "verified_at": datetime.now(UTC).isoformat(),
    }
    atomic_write(result_path, json.dumps(evidence, sort_keys=True, indent=2).encode())
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    result = run_probe(
        content_root=args.content_root,
        manifest_path=args.manifest,
        result_path=args.result,
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "probe_id": result["probe_id"],
                "temporary_object_cleaned": result["temporary_object_cleaned"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
