#!/usr/bin/env python3
"""Start one backend with identity derived from its immutable manifest."""

from __future__ import annotations

import json
import os
from pathlib import Path

release = Path.cwd()
manifest = json.loads((release / "release.json").read_text(encoding="utf-8"))
os.environ["PWC_RELEASE_ID"] = manifest["release_id"]
expected_dist = (release / manifest["frontend_entrypoint"]).parent
configured_dist = Path(os.environ["PWC_FRONTEND_DIST_DIR"]).resolve()
if configured_dist != expected_dist.resolve():
    raise SystemExit("configured frontend distribution does not match current release")
python = Path("/srv/paperswithcode/.venv/bin/python")
os.execv(python, [str(python), "-m", "uvicorn", "backend.main:app"])
