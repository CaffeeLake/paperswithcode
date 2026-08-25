from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatLatexPaperVersion,
    ChatSession,
)
from backend.services.chat_artifact_service import LocalArtifactStorage
from backend.services.latex_paper_service import LatexPaperService
from latex_compiler_contract import (
    CompileLimits,
    CompilerDiagnostic,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_jsonb_typeof(connection, _record):
        connection.create_function("jsonb_typeof", 1, lambda _value: "array")

    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatArtifact.__table__,
            ChatLatexPaperVersion.__table__,
        ],
    )
    with Session(engine) as session:
        yield session


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_artifacts_enabled=True,
        chat_latex_paper_enabled=True,
        chat_latex_compiler_jobs_enabled=True,
        chat_artifact_storage_backend="local",
        chat_artifact_local_dir=str(tmp_path / "storage"),
    )


def _session(
    db: Session, *, owner: str = "owner-1", paper_reader: bool = False
) -> uuid.UUID:
    session_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
            primary_paper_id=1 if paper_reader else None,
        )
    )
    db.flush()
    return session_id


class _Compiler:
    def __init__(self, state: CompilerJobState = CompilerJobState.SUCCEEDED):
        self.state = state
        self.submitted: tuple[str, bytes, str] | None = None

    def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
        self.submitted = (job_id, bundle, entrypoint)
        return CompilerStatus(job_id=job_id, state=self.state)

    def status(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=self.state)

    def result(self, job_id: str):
        assert self.submitted is not None
        _, bundle, entrypoint = self.submitted
        envelope = CompilerEnvelope(
            job_id=job_id,
            source_digest=hashlib.sha256(bundle).hexdigest(),
            source_bytes=len(bundle),
            entrypoint=entrypoint,
            limits=CompileLimits(),
            expires_at=1,
        )
        if self.state == CompilerJobState.SUCCEEDED:
            return CompilerResult.succeeded(
                envelope,
                pdf=b"%PDF-1.7\nscaffold\n",
                log_tail="",
                compiler_image="test-image",
                engine_version="pdfTeX",
            )
        return CompilerResult.failed(
            envelope,
            diagnostics=[
                CompilerDiagnostic(
                    severity="error",
                    file="main.tex",
                    line=7,
                    message="Undefined control sequence",
                )
            ],
            log_tail="bad TeX",
            compiler_image="test-image",
            engine_version="pdfTeX",
            elapsed_ms=1,
        )

    def cancel(self, job_id: str):
        return CompilerStatus(job_id=job_id, state=CompilerJobState.CANCELED)


def test_create_scaffold_persists_immutable_source_and_preview(db, settings):
    session_id = _session(db)
    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)

    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id, title="Careful Draft"
    )

    assert descriptor.title == "Careful Draft"
    assert descriptor.source_head is not None
    assert descriptor.preview_head is not None
    assert descriptor.source_head.version == 1
    assert descriptor.source_head.compile_status == "succeeded"
    assert descriptor.source_head.version_id == descriptor.preview_head.version_id
    artifact = db.get(ChatArtifact, descriptor.artifact_id)
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert artifact is not None and version is not None
    assert artifact.source_head_version_id == version.id
    assert artifact.preview_head_version_id == version.id
    assert storage.read_file(
        f"{version.storage_key}/main.tex", max_bytes=100_000
    ).startswith(b"\\documentclass")
    assert storage.read_file(
        f"{version.storage_key}/source.zip", max_bytes=100_000
    ).startswith(b"PK")
    assert storage.read_file(
        f"{version.storage_key}/preview.pdf", max_bytes=100_000
    ).startswith(b"%PDF")
    assert service.read_source_file(
        "owner-1", descriptor.artifact_id, version.id, "main.tex"
    ).data.startswith(b"\\documentclass")
    with pytest.raises(Exception, match="not found"):
        service.read_preview_pdf("another-owner", descriptor.artifact_id, version.id)
    storage.write_file(f"{version.storage_key}/preview.pdf", BytesIO(b"%PDF-tampered"))
    with pytest.raises(Exception, match="invalid"):
        service.read_preview_pdf("owner-1", descriptor.artifact_id, version.id)


def test_failed_compile_keeps_source_head_without_preview(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(CompilerJobState.FAILED),
    )

    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id, title="Broken Draft"
    )

    assert descriptor.source_head is not None
    assert descriptor.source_head.compile_status == "failed"
    assert descriptor.preview_head is None


def test_failed_human_save_keeps_last_good_preview_and_exposes_diagnostics(
    db, settings
):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED

    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )

    assert failed.source_head is not None and failed.preview_head is not None
    assert failed.source_head.compile_status == "failed"
    assert failed.source_head.parent_version_id == initial.source_head.version_id
    assert failed.preview_head.version_id == initial.preview_head.version_id
    assert [item.model_dump() for item in failed.source_head.compile_diagnostics] == [
        {
            "severity": "error",
            "phase": "compiler_error",
            "file": "main.tex",
            "line": 7,
            "message": "Undefined control sequence",
        }
    ]
    assert failed.source_head.repair_attempts_remaining == 3


def test_failed_ai_repairs_are_ephemeral_until_a_successful_candidate(db, settings):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    attempt = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\stillbad"},
        provenance={"model": "selected-model", "repair": True},
    )

    assert attempt.repaired is False
    assert attempt.exhausted is False
    assert attempt.descriptor.source_head is not None
    assert attempt.descriptor.source_head.version_id == failed.source_head.version_id
    assert attempt.descriptor.source_head.repair_attempts_remaining == 2
    assert (
        db.scalar(
            select(func.count())
            .select_from(ChatLatexPaperVersion)
            .where(ChatLatexPaperVersion.artifact_id == initial.artifact_id)
        )
        == 2
    )

    compiler.state = CompilerJobState.SUCCEEDED
    repaired = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"model": "selected-model", "repair": True},
    )

    assert repaired.repaired is True
    assert repaired.exhausted is False
    assert repaired.descriptor.source_head is not None
    assert repaired.descriptor.source_head.compile_status == "succeeded"
    assert (
        repaired.descriptor.source_head.parent_version_id
        == failed.source_head.version_id
    )
    assert repaired.descriptor.source_head.generation_provenance == {
        "model": "selected-model",
        "repair": True,
    }


def test_async_repair_waits_for_terminal_sandbox_result(db, settings, monkeypatch):
    class AsyncCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.status_calls = 0
            self.canceled = False

        def status(self, job_id: str):
            self.status_calls += 1
            self.state = CompilerJobState.SUCCEEDED
            return super().status(job_id)

        def cancel(self, job_id: str):
            self.canceled = True
            return super().cancel(job_id)

    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    async_compiler = AsyncCompiler()
    service.compiler = async_compiler
    monkeypatch.setattr(
        "backend.services.latex_paper_service.time.sleep", lambda _: None
    )
    repaired = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"selected_model": "test-model", "repair": True},
    )

    assert repaired.repaired is True
    assert async_compiler.status_calls == 1
    assert async_compiler.canceled is False
    assert repaired.descriptor.source_head is not None
    assert repaired.descriptor.source_head.provenance.action == "ai_repair"
    assert repaired.descriptor.source_head.provenance.model_identity == "test-model"


def test_async_repair_cancels_when_sandbox_polling_fails(db, settings, monkeypatch):
    class PollingFailureCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.canceled = False

        def status(self, job_id: str):
            raise RuntimeError("Sandbox connection lost")

        def cancel(self, job_id: str):
            self.canceled = True
            return super().cancel(job_id)

    compiler = _Compiler()
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=compiler)
    initial = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=_session(db)
    )
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    failing_compiler = PollingFailureCompiler()
    service.compiler = failing_compiler
    monkeypatch.setattr(
        "backend.services.latex_paper_service.time.sleep", lambda _: None
    )
    outcome = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"selected_model": "test-model", "repair": True},
    )

    assert outcome.repaired is False
    assert failing_compiler.canceled is True
    assert outcome.descriptor.source_head is not None
    assert outcome.descriptor.source_head.version_id == failed.source_head.version_id


def test_repair_budget_leaves_the_failed_human_source_intact_after_three_attempts(
    db, settings
):
    session_id = _session(db)
    compiler = _Compiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    compiler.state = CompilerJobState.FAILED
    failed = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={"main.tex": b"\\documentclass{article}\\badcommand"},
    )
    assert failed.source_head is not None

    for _ in range(3):
        outcome = service.repair_failed_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=failed.source_head.version_id,
            files={"main.tex": b"\\documentclass{article}\\stillbad"},
            provenance={"model": "selected-model", "repair": True},
        )
    assert outcome.exhausted is True
    compiler.state = CompilerJobState.SUCCEEDED

    exhausted = service.repair_failed_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=failed.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Fixed\\end{document}"
        },
        provenance={"model": "selected-model", "repair": True},
    )

    assert exhausted.repaired is False
    assert exhausted.exhausted is True
    assert exhausted.descriptor.source_head is not None
    assert exhausted.descriptor.source_head.version_id == failed.source_head.version_id
    assert exhausted.descriptor.preview_head is not None
    assert (
        exhausted.descriptor.preview_head.version_id == initial.preview_head.version_id
    )


def test_restart_reconciliation_resubmits_the_durable_version_job_id(db, settings):
    session_id = _session(db)
    first_compiler = _Compiler(CompilerJobState.COMPILING)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    service = LatexPaperService(db, settings, storage=storage, compiler=first_compiler)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert first_compiler.submitted is not None
    assert first_compiler.submitted[0] == str(version.id)

    restarted = _Compiler(CompilerJobState.SUCCEEDED)
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.submitted is not None
    assert restarted.submitted[0] == str(version.id)
    assert version.compile_status == "succeeded"


def test_restart_reconciliation_reattaches_the_saved_sandbox_job(db, settings):
    class SandboxCompiler(_Compiler):
        provider_job_id = "opaque-sandbox-job"

        def __init__(self, *, resumed: bool = False):
            super().__init__(CompilerJobState.COMPILING)
            self.resumed = resumed
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=self.provider_job_id,
            )

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.COMPILING,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    original = SandboxCompiler()
    service = LatexPaperService(db, settings, storage=storage, compiler=original)
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    version = db.get(ChatLatexPaperVersion, descriptor.source_head.version_id)
    assert version is not None
    assert version.compile_diagnostics["provider_job_id"] == "opaque-sandbox-job"

    restarted = SandboxCompiler(resumed=True)
    recovery = LatexPaperService(db, settings, storage=storage, compiler=restarted)
    assert recovery.reconcile_pending_compiles(limit=1) == 1

    assert restarted.resume_calls == [(str(version.id), "opaque-sandbox-job")]
    assert restarted.submitted is None


def test_paper_is_private_general_chat_only_and_unique(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    with pytest.raises(Exception, match="already has a paper"):
        service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    with pytest.raises(Exception, match="not found"):
        service.get_descriptor("another-owner", session_id)

    reader_id = _session(db, paper_reader=True)
    with pytest.raises(Exception, match="general chat"):
        service.create_neutral_scaffold(owner_id="owner-1", session_id=reader_id)


def test_human_save_creates_a_child_and_advances_both_heads(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Edited\\end{document}",
            "references.bib": b"@comment{Edited}\n",
        },
    )

    assert saved.source_head is not None and saved.preview_head is not None
    assert saved.source_head.version == 2
    assert saved.editing_enabled is True
    assert saved.source_head.parent_version_id == initial.source_head.version_id
    assert saved.source_head.version_id == saved.preview_head.version_id
    version = db.get(ChatLatexPaperVersion, saved.source_head.version_id)
    assert version is not None and version.actor_type == "human"
    assert db.get(ChatArtifact, saved.artifact_id).latest_version == 2
    assert service.read_source_file(
        "owner-1", saved.artifact_id, version.id, "main.tex"
    ).data.endswith(b"\\end{document}")


def test_human_save_rejects_a_stale_parent_without_overwriting(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    saved = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}One\\end{document}"
        },
    )

    with pytest.raises(Exception, match="updated elsewhere"):
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files={
                "main.tex": b"\\documentclass{article}\\begin{document}Two\\end{document}"
            },
        )
    assert (
        db.get(ChatArtifact, initial.artifact_id).source_head_version_id
        == saved.source_head.version_id
    )


def test_history_is_paginated_and_exposes_only_bounded_version_audit_data(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(
        owner_id="owner-1",
        session_id=session_id,
        actor_type="ai",
        model_identity="gpt-test",
    )
    assert initial.source_head is not None
    human = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Human\\end{document}"
        },
    )
    assert human.source_head is not None
    repaired = service.save_ai_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=human.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Repair\\end{document}"
        },
        model_identity="gpt-test",
        change_summary="Fixed the compilation error.",
        changed_files=["main.tex"],
        reference_changes=["Added one verified reference."],
        is_repair=True,
    )
    assert repaired.source_head is not None

    first = service.list_history(
        owner_id="owner-1", artifact_id=initial.artifact_id, limit=2
    )
    assert [item.version for item in first.items] == [3, 2]
    assert first.next_cursor == "2"
    assert first.items[0].actor_type == "ai"
    assert first.items[0].created_at is not None
    assert first.items[0].provenance.action == "ai_repair"
    assert first.items[0].provenance.model_identity == "gpt-test"
    assert first.items[0].provenance.changed_files == ["main.tex"]
    assert first.items[0].provenance.reference_changes == [
        "Added one verified reference."
    ]
    assert first.items[1].actor_type == "human"
    assert first.items[1].provenance.action == "human_save"
    assert not hasattr(first.items[0], "files")

    second = service.list_history(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        limit=2,
        cursor=first.next_cursor,
    )
    assert [item.version for item in second.items] == [1]
    assert second.next_cursor is None
    assert second.items[0].provenance.action == "ai_draft"


def test_restore_creates_a_new_head_and_retains_the_last_good_preview_on_failure(
    db, settings
):
    session_id = _session(db)
    storage = LocalArtifactStorage(Path(settings.chat_artifact_local_dir))
    initial_service = LatexPaperService(
        db, settings, storage=storage, compiler=_Compiler()
    )
    initial = initial_service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )
    assert initial.source_head is not None
    edited = initial_service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}New head\\end{document}"
        },
    )
    assert edited.source_head is not None and edited.preview_head is not None

    restoring = LatexPaperService(
        db, settings, storage=storage, compiler=_Compiler(CompilerJobState.FAILED)
    )
    restored = restoring.restore_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        source_version_id=initial.source_head.version_id,
        expected_parent_version_id=edited.source_head.version_id,
    )

    assert restored.source_head is not None and restored.preview_head is not None
    assert restored.source_head.version == 3
    assert restored.source_head.parent_version_id == edited.source_head.version_id
    assert restored.source_head.compile_status == "failed"
    assert restored.source_head.provenance.action == "restore"
    assert restored.preview_head.version_id == edited.preview_head.version_id
    restored_row = db.get(ChatLatexPaperVersion, restored.source_head.version_id)
    original_row = db.get(ChatLatexPaperVersion, initial.source_head.version_id)
    assert restored_row is not None and original_row is not None
    assert restored_row.source_digest == original_row.source_digest
    assert restored_row.id != original_row.id
    assert restored.source_head.provenance.restored_from_version_id == original_row.id
    assert (
        initial_service.read_source_file(
            "owner-1", initial.artifact_id, restored_row.id, "main.tex"
        ).data
        == initial_service.read_source_file(
            "owner-1", initial.artifact_id, original_row.id, "main.tex"
        ).data
    )

    with pytest.raises(Exception, match="updated elsewhere"):
        restoring.restore_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            source_version_id=initial.source_head.version_id,
            expected_parent_version_id=edited.source_head.version_id,
        )


def test_restore_rejects_the_current_head(db, settings):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None

    with pytest.raises(Exception, match="historical version"):
        service.restore_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            source_version_id=initial.source_head.version_id,
            expected_parent_version_id=initial.source_head.version_id,
        )


def test_pending_human_save_advances_preview_when_polled(db, settings):
    class DelayedCompiler(_Compiler):
        def __init__(self):
            super().__init__(CompilerJobState.QUEUED)
            self.calls = 0

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.calls += 1
            self.submitted = (job_id, bundle, entrypoint)
            self.state = (
                CompilerJobState.QUEUED
                if self.calls == 2
                else CompilerJobState.SUCCEEDED
            )
            return CompilerStatus(job_id=job_id, state=self.state)

    session_id = _session(db)
    compiler = DelayedCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    pending = service.save_human_version(
        owner_id="owner-1",
        artifact_id=initial.artifact_id,
        expected_parent_version_id=initial.source_head.version_id,
        files={
            "main.tex": b"\\documentclass{article}\\begin{document}Queued\\end{document}"
        },
    )
    assert pending.source_head is not None
    assert pending.source_head.compile_status == "queued"
    assert pending.preview_head is not None
    assert pending.preview_head.version_id == initial.preview_head.version_id

    completed = service.refresh_compile(
        owner_id="owner-1", artifact_id=initial.artifact_id
    )
    assert completed.source_head is not None and completed.preview_head is not None
    assert completed.source_head.compile_status == "succeeded"
    assert completed.preview_head.version_id == completed.source_head.version_id


def test_owner_poll_reattaches_a_pending_sandbox_instead_of_submitting_again(
    db, settings
):
    class ResumeCompiler(_Compiler):
        def __init__(self) -> None:
            super().__init__(CompilerJobState.QUEUED)
            self.submit_calls = 0
            self.resume_calls: list[tuple[str, str]] = []

        def submit(self, *, job_id: str, bundle: bytes, entrypoint: str, limits=None):
            self.submit_calls += 1
            if self.submit_calls > 1:
                raise AssertionError("owner poll must not create another Sandbox")
            self.submitted = (job_id, bundle, entrypoint)
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id="opaque-sandbox-job",
            )

        def resume(
            self, *, job_id: str, provider_job_id: str, bundle: bytes, entrypoint: str
        ):
            self.resume_calls.append((job_id, provider_job_id))
            return CompilerStatus(
                job_id=job_id,
                state=CompilerJobState.QUEUED,
                provider_job_id=provider_job_id,
            )

    session_id = _session(db)
    compiler = ResumeCompiler()
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=compiler,
    )
    descriptor = service.create_neutral_scaffold(
        owner_id="owner-1", session_id=session_id
    )

    service.refresh_compile(owner_id="owner-1", artifact_id=descriptor.artifact_id)

    assert compiler.submit_calls == 1
    assert compiler.resume_calls == [
        (str(descriptor.source_head.version_id), "opaque-sandbox-job")
    ]


@pytest.mark.parametrize(
    "files, message",
    [
        ({"main.tex": b"x", "unsafe.sty": b"x"}, "supported TeX or BibTeX"),
        ({"main.tex": b"x", "../outside.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "dir//outside.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "nul\x00.tex": b"x"}, "safe relative path"),
        ({"main.tex": b"x", "folder\\outside.tex": b"x"}, "safe relative path"),
        ({"references.bib": b"x"}, "root document"),
    ],
)
def test_human_save_rejects_invalid_file_sets(db, settings, files, message):
    session_id = _session(db)
    service = LatexPaperService(
        db,
        settings,
        storage=LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
        compiler=_Compiler(),
    )
    initial = service.create_neutral_scaffold(owner_id="owner-1", session_id=session_id)
    assert initial.source_head is not None
    with pytest.raises(Exception, match=message):
        service.save_human_version(
            owner_id="owner-1",
            artifact_id=initial.artifact_id,
            expected_parent_version_id=initial.source_head.version_id,
            files=files,
        )


def test_database_rejects_a_second_paper_even_if_service_is_bypassed(db):
    session_id = _session(db)
    db.add_all(
        [
            ChatArtifact(
                id=uuid.uuid4(),
                session_id=session_id,
                identifier="one",
                kind="latex_paper",
                title="One",
            ),
            ChatArtifact(
                id=uuid.uuid4(),
                session_id=session_id,
                identifier="two",
                kind="latex_paper",
                title="Two",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        db.flush()
