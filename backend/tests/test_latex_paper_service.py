from __future__ import annotations

import hashlib
import uuid
from io import BytesIO
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
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
            diagnostics=[],
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
