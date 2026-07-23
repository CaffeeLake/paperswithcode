#!/usr/bin/env python3
"""Start one backend with identity derived from its immutable manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path


def configure_release_environment(release: Path) -> dict:
    manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
    features = manifest["backend_features"]
    os.environ["PWC_RELEASE_ID"] = manifest["release_id"]
    os.environ["PWC_CHAT_ENABLED"] = "true" if features["chat"] else "false"
    os.environ["PWC_CODEX_ADD_EVALS_ENABLED"] = (
        "true" if features.get("codex_add_evals", False) else "false"
    )
    os.environ["PWC_CODEX_ENRICH_PAPER_ENABLED"] = (
        "true" if features.get("codex_enrich_paper", False) else "false"
    )
    os.environ["PWC_CODEX_JOBS_ENABLED"] = (
        "true"
        if features.get("codex_add_evals", False)
        or features.get("codex_enrich_paper", False)
        else "false"
    )
    expected_dist = (release / manifest["frontend_entrypoint"]).parent
    configured_dist = Path(os.environ["PWC_FRONTEND_DIST_DIR"]).resolve()
    if configured_dist != expected_dist.resolve():
        raise SystemExit(
            "configured frontend distribution does not match current release"
        )
    return manifest


def main() -> None:
    configure_release_environment(Path.cwd())
    python = Path("/srv/paperswithcode/.venv/bin/python")
    os.execv(python, [str(python), "-m", "uvicorn", "backend.main:app"])


if __name__ == "__main__":
    main()
