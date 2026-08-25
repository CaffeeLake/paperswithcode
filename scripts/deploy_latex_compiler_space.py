"""Assemble and deploy the private staging LaTeX compiler Space explicitly."""

from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi, SpaceHardware

ROOT = Path(__file__).resolve().parents[1]
SPACE_SOURCE = ROOT / "latex_compiler_space"
CONTRACT_SOURCE = ROOT / "latex_compiler_contract"
CONFIRMATION = "DEPLOY_PRIVATE_LATEX_COMPILER_SPACE"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", required=True, help="Private staging Space repo ID")
    parser.add_argument("--confirm", required=True)
    return parser.parse_args()


def _validate_space_id(space_id: str) -> str:
    if "/" not in space_id or any(
        part in {"", ".", ".."} for part in space_id.split("/")
    ):
        raise ValueError("Space ID must be namespace/name")
    if "production" in space_id.lower():
        raise ValueError(
            "This staging-only deploy command refuses production Space IDs"
        )
    if not space_id.endswith("-staging"):
        raise ValueError(
            "This staging-only deploy command requires a -staging Space ID"
        )
    return space_id


def _assemble(destination: Path) -> None:
    for name in ("Dockerfile", "README.md", "requirements.txt"):
        shutil.copy2(SPACE_SOURCE / name, destination / name)
    ignored = shutil.ignore_patterns("__pycache__", "*.pyc")
    shutil.copytree(SPACE_SOURCE, destination / "latex_compiler_space", ignore=ignored)
    shutil.copytree(
        CONTRACT_SOURCE, destination / "latex_compiler_contract", ignore=ignored
    )


def main() -> None:
    args = _parse_args()
    if args.confirm != CONFIRMATION:
        raise SystemExit(f"Pass --confirm {CONFIRMATION} to deploy the private Space")
    space_id = _validate_space_id(args.space)
    api = HfApi()
    api.create_repo(
        repo_id=space_id,
        repo_type="space",
        space_sdk="docker",
        private=True,
        exist_ok=True,
    )
    api.update_repo_settings(repo_id=space_id, repo_type="space", private=True)
    api.request_space_hardware(
        repo_id=space_id,
        hardware=SpaceHardware.CPU_UPGRADE,
        sleep_time=0,
    )
    with tempfile.TemporaryDirectory(prefix="pwc-latex-space-") as temporary:
        assembled = Path(temporary)
        _assemble(assembled)
        api.upload_folder(
            repo_id=space_id,
            repo_type="space",
            folder_path=assembled,
            commit_message="Deploy private PwC LaTeX compiler",
        )
    print(
        f"Uploaded private compiler source to {space_id}; set its public-key secret in the Space settings."
    )


if __name__ == "__main__":
    main()
