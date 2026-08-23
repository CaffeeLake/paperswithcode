"""Apply the mechanical contract changes for a newly published worker image."""

from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

DEFAULT_CONTRACT = Path(__file__).with_name("contract.py")
VERSION_PATTERN = re.compile(
    r'^WORKER_CONTRACT_VERSION = "(?P<value>[0-9]+)"$', re.MULTILINE
)
IMAGE_PATTERN = re.compile(
    r'^MODAL_IMAGE_ID = "(?P<value>im-[A-Za-z0-9]+)"$', re.MULTILINE
)
IMAGE_ID_PATTERN = re.compile(r"^im-[A-Za-z0-9]+$")


def _replace_once(path: Path, pattern: re.Pattern[str], replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, replacements = pattern.subn(replacement, content)
    if replacements != 1:
        raise ValueError(f"expected exactly one worker contract field in {path}")
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(updated)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def bump_version(path: Path = DEFAULT_CONTRACT) -> str:
    """Increment and return the numeric worker contract version."""
    content = path.read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(content)
    if match is None:
        raise ValueError(f"worker contract version is missing from {path}")
    version = str(int(match.group("value")) + 1)
    _replace_once(path, VERSION_PATTERN, f'WORKER_CONTRACT_VERSION = "{version}"')
    return version


def set_image_id(image_id: str, path: Path = DEFAULT_CONTRACT) -> None:
    """Pin the immutable staging image emitted by Modal publication."""
    if not IMAGE_ID_PATTERN.fullmatch(image_id):
        raise ValueError("Modal image ID must be an immutable im-... identifier")
    _replace_once(path, IMAGE_PATTERN, f'MODAL_IMAGE_ID = "{image_id}"')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--bump-version", action="store_true")
    action.add_argument("--set-image-id")
    args = parser.parse_args()
    if args.bump_version:
        print(bump_version(args.contract))
    else:
        set_image_id(args.set_image_id, args.contract)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
