from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import deploy.cli as deploy_cli
import deploy.external_pi_runtime as runtime_module
from deploy.external_pi_runtime import (
    cleanup_external_pi_runtimes,
    external_pi_runtime_id,
    external_pi_runtime_manifest,
    prepare_external_pi_runtime,
)
from deploy.release import atomic_symlink


PROMPT_INPUTS = (
    "backend/__init__.py",
    "backend/chat_execution_policy.py",
    "backend/chat_sandbox_worker/__init__.py",
    "backend/chat_sandbox_worker/render_pi_prompt_asset.py",
    "backend/chat_sandbox_worker/prompt.py",
    "backend/chat_sandbox_worker/PAPER_AUTHORING_PROMPT.md",
    "backend/chat_sandbox_worker/PAPER_AUTHORING.md",
    "backend/chat_sandbox_worker/PWC_CLI_SKILL.md",
    "backend/chat_sandbox_worker/HF_CLI_SKILL.md",
    "backend/chat_sandbox_worker/S2_CLI_SKILL.md",
    "backend/chat_sandbox_worker/TASK_CATALOG.md",
    "backend/chat_sandbox_worker/METHOD_CATALOG.md",
)


def release_fixture(root: Path, name: str = "release-a") -> Path:
    release = root / name
    worker = release / "backend/chat_sandbox_worker/pi_worker"
    (worker / "src").mkdir(parents=True)
    (worker / "package.json").write_text(
        json.dumps({"engines": {"node": "22.19.0"}}), encoding="utf-8"
    )
    (worker / "package-lock.json").write_text("locked\n", encoding="utf-8")
    (worker / "tsconfig.json").write_text("{}\n", encoding="utf-8")
    (worker / "src/external_http_main.ts").write_text(
        "export const worker = true;\n", encoding="utf-8"
    )
    (worker / "test").mkdir()
    (worker / "test/external_http_main.test.ts").write_text(
        "export const testWorker = true;\n", encoding="utf-8"
    )
    for relative in PROMPT_INPUTS:
        path = release / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{relative}\n", encoding="utf-8")
    (release / "release.json").write_text(
        json.dumps({"release_id": name}), encoding="utf-8"
    )
    return release


@pytest.fixture
def pinned_node_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    archive = tmp_path / "node.tar.xz"
    prefix = "node-v22.19.0-linux-x64"
    with tarfile.open(archive, "w:xz") as bundle:
        for relative, content, mode in (
            ("bin/node", b"pinned node executable\n", 0o755),
            ("lib/node_modules/npm/bin/npm-cli.js", b"npm cli\n", 0o644),
        ):
            info = tarfile.TarInfo(f"{prefix}/{relative}")
            info.size = len(content)
            info.mode = mode
            bundle.addfile(info, io.BytesIO(content))
    monkeypatch.setattr(
        runtime_module,
        "PI_NODE_SHA256",
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )
    return archive


class PackageRunner:
    def __init__(self, *, fail_build: bool = False) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail_build = fail_build

    def __call__(self, command, **kwargs):
        self.calls.append(tuple(str(value) for value in command))
        if command[-1] == "--version":
            return SimpleNamespace(stdout="v22.19.0\n")
        cwd = Path(kwargs.get("cwd", "."))
        if "ci" in command:
            dependency = cwd / "node_modules/example/index.js"
            dependency.parent.mkdir(parents=True)
            dependency.write_text("export default 1;\n", encoding="utf-8")
        elif command[-2:] == ["run", "build"]:
            if self.fail_build:
                raise RuntimeError("build failed")
            output = cwd / "dist/src/external_http_main.js"
            output.parent.mkdir(parents=True)
            output.write_text("export const worker = true;\n", encoding="utf-8")
        elif "prune" in command:
            pass
        else:
            Path(command[-1]).write_text("canonical prompt\n", encoding="utf-8")
        return SimpleNamespace(stdout="")


def test_external_pi_identity_is_stable_and_changes_with_every_input(tmp_path: Path):
    release = release_fixture(tmp_path)
    expected = external_pi_runtime_id(release)

    assert external_pi_runtime_id(release) == expected
    for relative in (
        "backend/chat_sandbox_worker/pi_worker/package.json",
        "backend/chat_sandbox_worker/pi_worker/package-lock.json",
        "backend/chat_sandbox_worker/pi_worker/tsconfig.json",
        "backend/chat_sandbox_worker/pi_worker/src/external_http_main.ts",
        "backend/chat_sandbox_worker/pi_worker/test/external_http_main.test.ts",
        "backend/chat_sandbox_worker/PWC_CLI_SKILL.md",
    ):
        path = release / relative
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "changed\n", encoding="utf-8")
        assert external_pi_runtime_id(release) != expected
        path.write_text(original, encoding="utf-8")


def test_failed_build_is_atomic_and_leaves_no_runtime(
    tmp_path: Path, pinned_node_archive: Path
):
    release = release_fixture(tmp_path)
    runtimes = tmp_path / "runtimes"

    with pytest.raises(RuntimeError, match="build failed"):
        prepare_external_pi_runtime(
            release,
            runtimes,
            runner=PackageRunner(fail_build=True),
            node_archive=pinned_node_archive,
            python_binary=tmp_path / "python",
        )

    assert not (runtimes / external_pi_runtime_id(release)).exists()
    assert not list(runtimes.glob(".*.new-*"))


def test_runtime_is_strictly_validated_and_reused(
    tmp_path: Path, pinned_node_archive: Path
):
    release = release_fixture(tmp_path)
    runtimes = tmp_path / "runtimes"
    runner = PackageRunner()
    runtime, created = prepare_external_pi_runtime(
        release,
        runtimes,
        runner=runner,
        node_archive=pinned_node_archive,
        python_binary=tmp_path / "python",
    )

    assert created is True
    manifest = external_pi_runtime_manifest(runtime)
    assert manifest["contract"] == "external-pi-v1"
    assert manifest["entry_point"] == "app/dist/src/external_http_main.js"
    assert manifest["node"]["version"] == "22.19.0"
    assert manifest["source_release"] == "release-a"
    assert runtime.stat().st_mode & 0o222 == 0
    assert all(
        "--ignore-scripts" in call
        for call in runner.calls
        if "ci" in call or "prune" in call
    )

    reused, created = prepare_external_pi_runtime(
        release,
        runtimes,
        runner=runner,
        node_archive=tmp_path / "unused-node-archive",
        python_binary=tmp_path / "unused-python",
    )
    assert reused == runtime
    assert created is False
    assert sum(call[-1] == "--version" for call in runner.calls) == 1


def test_runtime_rejects_a_node_archive_outside_the_pinned_contract(
    tmp_path: Path, pinned_node_archive: Path
):
    pinned_node_archive.write_bytes(pinned_node_archive.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="archive digest"):
        prepare_external_pi_runtime(
            release_fixture(tmp_path),
            tmp_path / "runtimes",
            runner=PackageRunner(),
            node_archive=pinned_node_archive,
            python_binary=tmp_path / "python",
        )


@pytest.mark.parametrize("mutation", ["digest", "mutable", "extra", "missing"])
def test_runtime_validation_rejects_changed_executable_inputs(
    tmp_path: Path, pinned_node_archive: Path, mutation: str
):
    release = release_fixture(tmp_path)
    runtime, _ = prepare_external_pi_runtime(
        release,
        tmp_path / "runtimes",
        runner=PackageRunner(),
        node_archive=pinned_node_archive,
        python_binary=tmp_path / "python",
    )
    entry = runtime / "app/dist/src/external_http_main.js"
    runtime.chmod(0o755)
    entry.parent.chmod(0o755)
    if mutation == "digest":
        entry.chmod(0o644)
        entry.write_text("changed\n", encoding="utf-8")
        entry.chmod(0o444)
    elif mutation == "mutable":
        entry.chmod(0o644)
    elif mutation == "extra":
        extra = entry.parent / "extra.js"
        extra.write_text("extra\n", encoding="utf-8")
        extra.chmod(0o444)
    else:
        entry.unlink()
    entry.parent.chmod(0o555)
    runtime.chmod(0o555)

    with pytest.raises(ValueError):
        external_pi_runtime_manifest(runtime)


def test_cleanup_removes_only_unprotected_external_pi_runtimes(tmp_path: Path):
    runtimes = tmp_path / "external-pi"
    for name in ("active", "previous", "prepared", "stale"):
        (runtimes / name).mkdir(parents=True)
    (runtimes / ".incomplete").mkdir()

    removed = cleanup_external_pi_runtimes(runtimes, {"active", "previous", "prepared"})

    assert removed == ["stale"]
    assert {path.name for path in runtimes.iterdir()} == {
        "active",
        "previous",
        "prepared",
        ".incomplete",
    }


def test_cleanup_protection_includes_current_previous_and_prepared_releases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    environments = tmp_path / "environments"
    releases = {
        name: release_fixture(tmp_path, name)
        for name in ("active", "previous", "prepared")
    }
    root = environments / "staging"
    (root / "slots/blue").mkdir(parents=True)
    (root / "slots/green").mkdir()
    atomic_symlink(releases["active"], root / "current")
    atomic_symlink(releases["previous"], root / "previous")
    atomic_symlink(releases["prepared"], root / "slots/green/release")
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS", ("staging",))
    monkeypatch.setattr(deploy_cli, "ENVIRONMENTS_ROOT", environments)

    assert deploy_cli.protected_external_pi_runtime_ids() == {
        external_pi_runtime_id(release) for release in releases.values()
    }
