"""Private immutable LaTeX-paper versions and their compiler hand-off."""

from __future__ import annotations

import hashlib
import uuid
import zipfile
from collections.abc import Mapping
from io import BytesIO
from pathlib import PurePosixPath

import httpx
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import (
    LatexPaperArtifactDescriptor,
    LatexPaperDisplayMetadata,
    LatexPaperFile,
    LatexPaperManifest,
    LatexPaperVersionDescriptor,
)
from backend.models.database import ChatArtifact, ChatLatexPaperVersion, ChatSession
from backend.services.chat_artifact_service import (
    ArtifactError,
    ArtifactStorage,
    StoredArtifactFile,
    artifact_storage_from_settings,
)
from backend.services.latex_compiler_service import (
    LatexCompilerTransport,
    compiler_client_from_settings,
)
from latex_compiler_contract import CompilerJobState, CompilerResult, EnvelopeError

_PAPER_IDENTIFIER = "latex-paper"
_SOURCE_ARCHIVE = "source.zip"
_PREVIEW_PDF = "preview.pdf"


def _neutral_scaffold(title: str) -> dict[str, bytes]:
    safe_title = " ".join(title.split()) or "Untitled Research Draft"
    return {
        "main.tex": f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{natbib}}
\\title{{{safe_title}}}
\\author{{TODO: Author name}}
\\date{{}}
\\begin{{document}}
\\maketitle
\\begin{{abstract}}
TODO: Summarize the research question, evidence, and conclusions.
\\end{{abstract}}
\\section{{Introduction}}
TODO: State the problem and the evidence needed to support this draft.
\\bibliographystyle{{plainnat}}
\\bibliography{{references}}
\\end{{document}}
""".encode(),
        "references.bib": b"@comment{TODO: Add verified bibliography entries.}\n",
    }


def _media_type(path: str) -> str:
    return {
        ".tex": "text/x-tex",
        ".bib": "application/x-bibtex",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".pdf": "application/pdf",
    }[PurePosixPath(path).suffix.lower()]


def _deterministic_zip(files: Mapping[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            entry = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return output.getvalue()


def _paper_descriptor(artifact: ChatArtifact) -> LatexPaperArtifactDescriptor:
    versions = {item.id: item for item in artifact.paper_versions}

    def descriptor(version_id: uuid.UUID | None) -> LatexPaperVersionDescriptor | None:
        if version_id is None or (version := versions.get(version_id)) is None:
            return None
        return LatexPaperVersionDescriptor(
            version_id=version.id,
            version=version.version,
            source_digest=version.source_digest,
            compile_status=version.compile_status,
            parent_version_id=version.parent_version_id,
            preview_head_version_id=artifact.preview_head_version_id,
            display_metadata=LatexPaperDisplayMetadata.model_validate(
                version.display_metadata
            ),
        )

    return LatexPaperArtifactDescriptor(
        artifact_id=artifact.id,
        title=artifact.title,
        source_head=descriptor(artifact.source_head_version_id),
        preview_head=descriptor(artifact.preview_head_version_id),
    )


class LatexPaperService:
    """Owns the first paper slice; Posterly keeps its existing service unchanged."""

    def __init__(
        self,
        db: Session,
        settings: Settings,
        *,
        storage: ArtifactStorage | None = None,
        compiler: LatexCompilerTransport | None = None,
    ) -> None:
        self.db = db
        self.settings = settings
        self._storage = storage
        self.compiler = compiler

    @property
    def storage(self) -> ArtifactStorage:
        if self._storage is None:
            self._storage = artifact_storage_from_settings(self.settings)
        return self._storage

    def create_neutral_scaffold(
        self,
        *,
        owner_id: str,
        session_id: uuid.UUID,
        title: str = "Untitled Research Draft",
    ) -> LatexPaperArtifactDescriptor:
        if (
            not self.settings.chat_artifacts_enabled
            or not self.settings.chat_latex_paper_enabled
        ):
            raise ArtifactError("artifacts_disabled", "Paper creation is disabled")
        if not self.settings.chat_latex_compiler_jobs_enabled:
            raise ArtifactError("compiler_disabled", "Paper compilation is disabled")
        session_row = self.db.execute(
            select(ChatSession.id, ChatSession.primary_paper_id).where(
                ChatSession.id == session_id, ChatSession.hf_user_id == owner_id
            )
        ).one_or_none()
        if session_row is None:
            raise ArtifactError("artifact_not_found", "Paper chat not found")
        if session_row.primary_paper_id is not None:
            raise ArtifactError(
                "artifact_invalid", "Papers are available only in general chat"
            )
        if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
            self.db.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:session))"),
                {"session": f"chat-latex-paper:{session_id}"},
            )
        existing = self.db.scalar(
            select(ChatArtifact).where(
                ChatArtifact.session_id == session_row.id,
                ChatArtifact.kind == "latex_paper",
            )
        )
        if existing is not None:
            raise ArtifactError("paper_exists", "This chat already has a paper")

        files = _neutral_scaffold(title)
        source_bytes = sum(len(data) for data in files.values())
        if source_bytes > self.settings.chat_artifact_max_version_bytes:
            raise ArtifactError(
                "artifact_too_large", "Paper scaffold exceeds the version limit"
            )
        manifest = LatexPaperManifest(
            title=" ".join(title.split()) or "Untitled Research Draft",
            root_document="main.tex",
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(files.items())
            ],
            display_metadata=LatexPaperDisplayMetadata(unresolved_todo_count=3),
        )
        bundle = _deterministic_zip(files)
        source_digest = hashlib.sha256(bundle).hexdigest()
        artifact = ChatArtifact(
            id=uuid.uuid4(),
            session_id=session_row.id,
            identifier=_PAPER_IDENTIFIER,
            kind="latex_paper",
            title=manifest.title,
            latest_version=1,
        )
        self.db.add(artifact)
        self.db.flush()
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            version=1,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(session_row.id, artifact.id),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=manifest.display_metadata.model_dump(mode="json"),
            actor_type="human",
        )
        artifact.source_head_version_id = version.id
        self.db.add(version)
        self.db.flush()
        try:
            for path, data in files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
            self.storage.write_file(
                f"{version.storage_key}/{_SOURCE_ARCHIVE}", BytesIO(bundle)
            )
        except Exception as error:
            version.storage_state = "failed"
            self.storage.delete_prefix(version.storage_key)
            raise ArtifactError(
                "artifact_storage_failed", "Paper source storage failed"
            ) from error
        version.storage_state = "ready"
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return _paper_descriptor(artifact)

    def get_descriptor(
        self, owner_id: str, session_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor | None:
        artifact = self.db.scalar(
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.session_id == session_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if artifact is None:
            session_exists = self.db.scalar(
                select(ChatSession.id).where(
                    ChatSession.id == session_id, ChatSession.hf_user_id == owner_id
                )
            )
            if session_exists is None:
                raise ArtifactError("artifact_not_found", "Paper chat not found")
            return None
        return _paper_descriptor(artifact)

    def get_artifact_descriptor(
        self, owner_id: str, artifact_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor:
        artifact = self._artifact(owner_id, artifact_id)
        return _paper_descriptor(artifact)

    def get_manifest(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> LatexPaperManifest:
        return LatexPaperManifest.model_validate(
            self._version(owner_id, artifact_id, version_id).source_manifest
        )

    def read_source_file(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID, path: str
    ) -> StoredArtifactFile:
        version = self._version(owner_id, artifact_id, version_id)
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        file = next((item for item in manifest.files if item.path == path), None)
        if file is None or file.media_type not in {
            "text/x-tex",
            "application/x-bibtex",
        }:
            raise ArtifactError("artifact_not_found", "Paper source file not found")
        data = self.storage.read_file(
            f"{version.storage_key}/{file.path}", max_bytes=file.bytes
        )
        if hashlib.sha256(data).hexdigest() != file.sha256:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        return StoredArtifactFile(
            data=data,
            media_type="text/plain; charset=utf-8",
            filename=PurePosixPath(path).name,
        )

    def read_preview_pdf(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> StoredArtifactFile:
        version = self._version(owner_id, artifact_id, version_id)
        if version.compile_status != "succeeded" or version.compiled_pdf_path is None:
            raise ArtifactError("artifact_not_found", "Paper preview not found")
        data = self.storage.read_file(
            f"{version.storage_key}/{version.compiled_pdf_path}",
            max_bytes=self.settings.chat_artifact_max_pdf_bytes,
        )
        expected_digest = (version.compile_diagnostics or {}).get("pdf_sha256")
        if (
            not data.startswith(b"%PDF-")
            or not isinstance(expected_digest, str)
            or hashlib.sha256(data).hexdigest() != expected_digest
        ):
            raise ArtifactError("artifact_corrupt", "Paper preview is invalid")
        return StoredArtifactFile(
            data=data, media_type="application/pdf", filename="paper.pdf"
        )

    def _compile(
        self, version: ChatLatexPaperVersion, bundle: bytes, entrypoint: str
    ) -> None:
        compiler = self.compiler or compiler_client_from_settings(self.settings)
        job_id = str(uuid.uuid4())
        try:
            status = compiler.submit(
                job_id=job_id, bundle=bundle, entrypoint=entrypoint
            )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
            }:
                status = compiler.status(job_id)
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
            }:
                version.compile_status = (
                    "compiling"
                    if status.state == CompilerJobState.COMPILING
                    else "queued"
                )
                version.compile_diagnostics = {"job_id": job_id}
                return
            result = compiler.result(job_id)
        except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "errors": [
                    {"severity": "error", "message": "Compiler submission failed"}
                ]
            }
            return
        self._store_compile_result(version, result)

    def _store_compile_result(
        self, version: ChatLatexPaperVersion, result: CompilerResult
    ) -> None:
        diagnostics = [item.model_dump(mode="json") for item in result.diagnostics]
        version.compile_diagnostics = {
            "diagnostics": diagnostics,
            "job_id": result.job_id,
            "pdf_sha256": result.pdf_digest,
        }
        if result.state != CompilerJobState.SUCCEEDED or result.pdf is None:
            version.compile_status = "failed"
            return
        if result.source_digest != version.source_digest:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "errors": [
                    {"severity": "error", "message": "Compiler source digest mismatch"}
                ]
            }
            return
        try:
            self.storage.write_file(
                f"{version.storage_key}/{_PREVIEW_PDF}", BytesIO(result.pdf)
            )
        except Exception as error:
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "errors": [{"severity": "error", "message": "Preview storage failed"}]
            }
            raise ArtifactError(
                "artifact_storage_failed", "Paper preview storage failed"
            ) from error
        version.compile_status = "succeeded"
        version.compiled_pdf_path = _PREVIEW_PDF
        version.artifact.preview_head_version_id = version.id

    def _artifact(self, owner_id: str, artifact_id: uuid.UUID) -> ChatArtifact:
        artifact = self.db.scalar(
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if artifact is None:
            raise ArtifactError("artifact_not_found", "Paper not found")
        return artifact

    def _version(
        self, owner_id: str, artifact_id: uuid.UUID, version_id: uuid.UUID
    ) -> ChatLatexPaperVersion:
        self._artifact(owner_id, artifact_id)
        version = self.db.scalar(
            select(ChatLatexPaperVersion).where(
                ChatLatexPaperVersion.id == version_id,
                ChatLatexPaperVersion.artifact_id == artifact_id,
                ChatLatexPaperVersion.storage_state == "ready",
            )
        )
        if version is None:
            raise ArtifactError("artifact_not_found", "Paper version not found")
        return version

    def _storage_prefix(self, session_id: uuid.UUID, artifact_id: uuid.UUID) -> str:
        return "/".join(
            [
                self.settings.chat_artifact_hf_bucket_prefix.strip("/"),
                str(session_id),
                str(artifact_id),
                "1",
            ]
        )
