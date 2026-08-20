#!/usr/bin/env python3
"""Narrow Posterly preparation and publication client for the local broker."""

from __future__ import annotations

import argparse
import http.client
import json
import shutil
import stat
import sys
import urllib.error
import urllib.request
import uuid
import zipfile
from pathlib import Path

BROKER = "http://127.0.0.1:8765"
WORKSPACE = Path("/workspace")
INPUTS = WORKSPACE / "inputs"
ARTIFACTS = WORKSPACE / "artifacts"
MAX_RESPONSE = 2 * 1024 * 1024
MAX_ARCHIVE = 32 * 1024 * 1024
EVENT_PREFIX = "@@PWC_ARTIFACT@@"


def _request(path: str, body: bytes, content_type: str) -> bytes:
    request = urllib.request.Request(
        f"{BROKER}{path}", body, {"Content-Type": content_type}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=620) as response:
            data = response.read(MAX_RESPONSE + 1)
            if len(data) > MAX_RESPONSE:
                raise RuntimeError("Artifact response exceeded its bound")
            return data
    except urllib.error.HTTPError as error:
        detail = error.read(8 * 1024).decode(errors="replace")
        raise RuntimeError(
            detail or f"Artifact request failed ({error.code})"
        ) from None


def _request_file(path: str, source: Path) -> bytes:
    size = source.stat().st_size
    if not 0 < size <= MAX_ARCHIVE:
        raise RuntimeError("Poster bundle exceeds the upload limit")
    connection = http.client.HTTPConnection("127.0.0.1", 8765, timeout=620)
    try:
        with source.open("rb") as body:
            connection.request(
                "POST",
                path,
                body=body,
                headers={
                    "Content-Type": "application/zip",
                    "Content-Length": str(size),
                },
            )
            response = connection.getresponse()
            data = response.read(MAX_RESPONSE + 1)
        if len(data) > MAX_RESPONSE:
            raise RuntimeError("Artifact response exceeded its bound")
        if response.status >= 400:
            raise RuntimeError(
                data.decode(errors="replace")
                or f"Artifact request failed ({response.status})"
            )
        return data
    finally:
        connection.close()


def _safe_name(value: str) -> str:
    if (
        not value
        or len(value) > 200
        or any(part in value for part in ("/", "\\", ".."))
    ):
        raise RuntimeError("Invalid paper route ID")
    return "".join(
        character if character.isalnum() or character in ".-_" else "-"
        for character in value
    )


def prepare(route_id: str) -> int:
    result = json.loads(
        _request(
            "/artifact-prepare",
            json.dumps({"paper_route_id": route_id}, separators=(",", ":")).encode(),
            "application/json",
        )
    )
    directory = INPUTS / _safe_name(result["paper_id"])
    if directory.exists():
        shutil.rmtree(directory)
    directory.mkdir(parents=True, mode=0o700)
    metadata = {key: value for key, value in result.items() if key != "paper_markdown"}
    (directory / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "paper.md").write_text(result["paper_markdown"], encoding="utf-8")
    for path in directory.iterdir():
        path.chmod(0o400)
    metadata["input_path"] = str(directory)
    print(json.dumps(metadata, ensure_ascii=False, separators=(",", ":")))
    return 0


def _archive(directory: Path, target: Path) -> None:
    root = directory.resolve(strict=True)
    if not root.is_relative_to(ARTIFACTS.resolve(strict=False)):
        raise RuntimeError("Poster bundle must be below /workspace/artifacts")
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files or len(files) > 101:
        raise RuntimeError("Poster bundle file count is invalid")
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as output:
        for path in files:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink():
                raise RuntimeError("Poster bundle contains an unsafe file")
            output.write(path, path.relative_to(root).as_posix())
            if target.stat().st_size > MAX_ARCHIVE:
                raise RuntimeError("Poster bundle exceeds the upload limit")


def publish(directory: str, publication_id: str | None) -> int:
    publication_id = publication_id or uuid.uuid4().hex
    source = Path(directory)
    temporary = WORKSPACE / f".poster-publish-{uuid.uuid4().hex}.zip"
    try:
        _archive(source, temporary)
        result = json.loads(
            _request_file(
                f"/artifact-publish?publication_id={publication_id}",
                temporary,
            )
        )
    finally:
        temporary.unlink(missing_ok=True)
    print(EVENT_PREFIX + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="pwc-artifact")
    commands = parser.add_subparsers(dest="command", required=True)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("paper_route_id")
    publish_parser = commands.add_parser("publish")
    publish_parser.add_argument("directory")
    publish_parser.add_argument("--publication-id")
    args = parser.parse_args()
    try:
        return (
            prepare(args.paper_route_id)
            if args.command == "prepare"
            else publish(args.directory, args.publication_id)
        )
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
