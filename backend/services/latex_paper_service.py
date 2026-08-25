"""Private immutable LaTeX-paper versions and their compiler hand-off."""

from __future__ import annotations

import hashlib
import uuid
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import (
    LatexPaperArtifactDescriptor,
    LatexPaperDiagnostic,
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
    compiler_transport_from_settings,
)
from latex_compiler_contract import CompilerJobState, CompilerResult, EnvelopeError

_PAPER_IDENTIFIER = "latex-paper"
_SOURCE_ARCHIVE = "source.zip"
_PREVIEW_PDF = "preview.pdf"
_MAX_REPAIR_ATTEMPTS = 3


@dataclass(frozen=True)
class LatexPaperRepairOutcome:
    descriptor: LatexPaperArtifactDescriptor
    repaired: bool
    exhausted: bool


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
        diagnostics = version.compile_diagnostics or {}
        raw_diagnostics = diagnostics.get("diagnostics", [])
        if not isinstance(raw_diagnostics, list):
            raw_diagnostics = []
        repair_diagnostics = diagnostics.get("last_repair_diagnostics", [])
        if isinstance(repair_diagnostics, list):
            raw_diagnostics = [*raw_diagnostics, *repair_diagnostics]
        errors = diagnostics.get("errors", [])
        if isinstance(errors, list):
            raw_diagnostics.extend(
                {"severity": "error", **item}
                for item in errors
                if isinstance(item, dict)
            )
        normalized_diagnostics = [
            LatexPaperDiagnostic(
                severity=item["severity"],
                phase=diagnostics.get("failure_category"),
                file=item.get("file"),
                line=item.get("line"),
                message=item["message"],
            )
            for item in raw_diagnostics[:20]
            if isinstance(item, dict)
            and item.get("severity") in {"error", "warning"}
            and isinstance(item.get("message"), str)
        ]
        attempts = diagnostics.get("repair_attempts", 0)
        attempts = attempts if isinstance(attempts, int) else 0
        attempts = min(max(attempts, 0), _MAX_REPAIR_ATTEMPTS)
        return LatexPaperVersionDescriptor(
            version_id=version.id,
            version=version.version,
            source_digest=version.source_digest,
            compile_status=version.compile_status,
            parent_version_id=version.parent_version_id,
            preview_head_version_id=artifact.preview_head_version_id,
            compile_diagnostics=normalized_diagnostics,
            repair_attempts_remaining=_MAX_REPAIR_ATTEMPTS - attempts,
            repair_exhausted=attempts >= _MAX_REPAIR_ATTEMPTS,
            generation_provenance=version.generation_provenance,
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
            storage_key=self._storage_prefix(session_row.id, artifact.id, version=1),
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
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def save_human_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        files: Mapping[str, bytes],
    ) -> LatexPaperArtifactDescriptor:
        """Publish one complete human source snapshot and submit it to compilation.

        Browser drafts are deliberately outside this boundary: a call is the explicit
        Save & Compile action, and it must either publish a whole new immutable
        version or leave the current head untouched.
        """
        if (
            not self.settings.chat_artifacts_enabled
            or not self.settings.chat_latex_paper_enabled
        ):
            raise ArtifactError("artifacts_disabled", "Paper editing is disabled")
        if not self.settings.chat_latex_compiler_jobs_enabled:
            raise ArtifactError("compiler_disabled", "Paper compilation is disabled")
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload its latest version before saving.",
            )
        parent = self._version(owner_id, artifact_id, expected_parent_version_id)
        parent_manifest = LatexPaperManifest.model_validate(parent.source_manifest)
        normalized_files = self._validate_human_files(
            files, root_document=parent_manifest.root_document
        )
        source_bytes = sum(len(data) for data in normalized_files.values())
        bundle = _deterministic_zip(normalized_files)
        if len(bundle) > self.settings.chat_artifact_max_version_bytes:
            raise ArtifactError(
                "artifact_too_large", "Paper source exceeds the version limit"
            )
        source_digest = hashlib.sha256(bundle).hexdigest()
        if self.db.scalar(
            select(ChatLatexPaperVersion.id).where(
                ChatLatexPaperVersion.artifact_id == artifact.id,
                ChatLatexPaperVersion.source_digest == source_digest,
            )
        ):
            raise ArtifactError(
                "artifact_invalid", "Paper source has no changes to save"
            )
        version_number = (
            self.db.scalar(
                select(func.max(ChatLatexPaperVersion.version)).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
            or 0
        ) + 1
        manifest = LatexPaperManifest(
            title=artifact.title,
            root_document=parent_manifest.root_document,
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(normalized_files.items())
            ],
            display_metadata=parent_manifest.display_metadata,
        )
        version = ChatLatexPaperVersion(
            id=uuid.uuid4(),
            artifact=artifact,
            parent_version_id=parent.id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=source_bytes,
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=manifest.display_metadata.model_dump(mode="json"),
            actor_type="human",
        )
        self.db.add(version)
        artifact.latest_version = version_number
        self.db.flush()
        try:
            for path, data in normalized_files.items():
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
        # Advance source before compilation so a failed compile remains a durable,
        # repairable human version while the previous PDF remains the preview head.
        artifact.source_head_version_id = version.id
        self._compile(version, bundle, manifest.root_document)
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def _validate_human_files(
        self, files: Mapping[str, bytes], *, root_document: str
    ) -> dict[str, bytes]:
        if not files:
            raise ArtifactError(
                "artifact_invalid", "Paper must contain a root document"
            )
        if len(files) > self.settings.chat_artifact_max_files:
            raise ArtifactError("artifact_too_large", "Paper has too many files")
        normalized: dict[str, bytes] = {}
        for path, data in files.items():
            raw_parts = path.split("/")
            candidate = PurePosixPath(path)
            if (
                not path
                or len(path) > 300
                or "\0" in path
                or "\\" in path
                or candidate.is_absolute()
                or any(part in {"", ".", ".."} for part in raw_parts)
            ):
                raise ArtifactError(
                    "artifact_invalid", "Paper files need safe relative paths"
                )
            if candidate.suffix.lower() not in {".tex", ".bib"}:
                raise ArtifactError(
                    "artifact_invalid",
                    "Paper files must be supported TeX or BibTeX files",
                )
            try:
                data.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ArtifactError(
                    "artifact_invalid", "Paper text must be valid UTF-8"
                ) from error
            normalized[path] = data
        if root_document not in normalized:
            raise ArtifactError(
                "artifact_invalid", "The configured root document cannot be deleted"
            )
        total_text_bytes = sum(len(data) for data in normalized.values())
        if total_text_bytes > self.settings.chat_artifact_max_text_bytes:
            raise ArtifactError(
                "artifact_too_large", "Paper text exceeds the editing limit"
            )
        return normalized

    def repair_failed_version(
        self,
        *,
        owner_id: str,
        artifact_id: uuid.UUID,
        expected_parent_version_id: uuid.UUID,
        files: Mapping[str, bytes],
        provenance: dict,
    ) -> LatexPaperRepairOutcome:
        """Compile one AI repair candidate without persisting failed attempts.

        A candidate has a real compiler job UUID but no durable paper version until
        it succeeds. This keeps mechanical repair attempts out of manuscript
        history while preserving the failed human source as the repair base.
        """
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        if artifact.source_head_version_id != expected_parent_version_id:
            raise ArtifactError(
                "paper_conflict",
                "This paper was updated elsewhere. Reload before repairing.",
            )
        parent = self._version(owner_id, artifact_id, expected_parent_version_id)
        if parent.compile_status != "failed":
            raise ArtifactError(
                "paper_not_failed", "Only a failed source version can be repaired"
            )
        diagnostics = dict(parent.compile_diagnostics or {})
        attempts = diagnostics.get("repair_attempts", 0)
        attempts = attempts if isinstance(attempts, int) else 0
        if attempts >= _MAX_REPAIR_ATTEMPTS:
            return LatexPaperRepairOutcome(
                self._descriptor(artifact), repaired=False, exhausted=True
            )

        parent_manifest = LatexPaperManifest.model_validate(parent.source_manifest)
        normalized_files = self._validate_human_files(
            files, root_document=parent_manifest.root_document
        )
        bundle = _deterministic_zip(normalized_files)
        source_digest = hashlib.sha256(bundle).hexdigest()
        candidate_id = uuid.uuid4()
        compiler = self.compiler or compiler_client_from_settings(self.settings)
        result: CompilerResult | None = None
        try:
            status = compiler.submit(
                job_id=str(candidate_id),
                bundle=bundle,
                entrypoint=parent_manifest.root_document,
            )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
            }:
                status = compiler.status(str(candidate_id))
            if status.state in {CompilerJobState.SUCCEEDED, CompilerJobState.FAILED}:
                result = compiler.result(str(candidate_id))
        except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
            result = None

        if result is None:
            # The compiler is asynchronous. A non-terminal response is neither a
            # failed repair nor a durable candidate, so it must not spend budget.
            return LatexPaperRepairOutcome(
                self._descriptor(artifact), repaired=False, exhausted=False
            )

        if (
            result.state != CompilerJobState.SUCCEEDED
            or result.pdf is None
            or result.source_digest != source_digest
        ):
            diagnostics["repair_attempts"] = attempts + 1
            if result is not None:
                diagnostics["last_repair_diagnostics"] = [
                    item.model_dump(mode="json") for item in result.diagnostics[:20]
                ]
            parent.compile_diagnostics = diagnostics
            self.db.flush()
            return LatexPaperRepairOutcome(
                self._descriptor(artifact),
                repaired=False,
                exhausted=attempts + 1 >= _MAX_REPAIR_ATTEMPTS,
            )

        version_number = (
            self.db.scalar(
                select(func.max(ChatLatexPaperVersion.version)).where(
                    ChatLatexPaperVersion.artifact_id == artifact.id
                )
            )
            or 0
        ) + 1
        manifest = LatexPaperManifest(
            title=artifact.title,
            root_document=parent_manifest.root_document,
            files=[
                LatexPaperFile(
                    path=path,
                    sha256=hashlib.sha256(data).hexdigest(),
                    bytes=len(data),
                    media_type=_media_type(path),
                )
                for path, data in sorted(normalized_files.items())
            ],
            display_metadata=parent_manifest.display_metadata,
        )
        version = ChatLatexPaperVersion(
            id=candidate_id,
            artifact=artifact,
            parent_version_id=parent.id,
            version=version_number,
            source_manifest=manifest.model_dump(mode="json"),
            source_digest=source_digest,
            source_byte_count=sum(len(data) for data in normalized_files.values()),
            storage_key=self._storage_prefix(
                artifact.session_id, artifact.id, version=version_number
            ),
            storage_state="uploading",
            compile_status="queued",
            display_metadata=manifest.display_metadata.model_dump(mode="json"),
            generation_provenance=provenance,
            actor_type="ai",
        )
        self.db.add(version)
        try:
            for path, data in normalized_files.items():
                self.storage.write_file(f"{version.storage_key}/{path}", BytesIO(data))
            self.storage.write_file(
                f"{version.storage_key}/{_SOURCE_ARCHIVE}", BytesIO(bundle)
            )
            version.storage_state = "ready"
            self._store_compile_result(version, result)
        except Exception as error:
            self.storage.delete_prefix(version.storage_key)
            self.db.expunge(version)
            raise ArtifactError(
                "artifact_storage_failed", "Paper repair storage failed"
            ) from error
        artifact.latest_version = version_number
        artifact.source_head_version_id = version.id
        self.db.flush()
        return LatexPaperRepairOutcome(
            self._descriptor(artifact), repaired=True, exhausted=False
        )

    def repair_context(
        self, *, owner_id: str, artifact_id: uuid.UUID
    ) -> tuple[LatexPaperArtifactDescriptor, dict[str, bytes]]:
        """Return the current failed source for the authenticated chat turn."""
        artifact = self._artifact(owner_id, artifact_id)
        if artifact.source_head_version_id is None:
            raise ArtifactError("paper_missing", "This chat has no paper source")
        version = self._version(owner_id, artifact_id, artifact.source_head_version_id)
        if version.compile_status != "failed":
            raise ArtifactError(
                "paper_not_failed", "The current paper source has not failed"
            )
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        files = {
            file.path: self.read_source_file(
                owner_id, artifact_id, version.id, file.path
            ).data
            for file in manifest.files
            if file.media_type in {"text/x-tex", "application/x-bibtex"}
        }
        return self._descriptor(artifact), files

    def _descriptor(self, artifact: ChatArtifact) -> LatexPaperArtifactDescriptor:
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def refresh_compile(
        self, *, owner_id: str, artifact_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor:
        """Idempotently reconcile a submitted compile job on an owner poll."""
        artifact = self._artifact(owner_id, artifact_id, lock=True)
        if artifact.source_head_version_id is None:
            return _paper_descriptor(artifact).model_copy(
                update={"editing_enabled": self._editing_enabled()}
            )
        version = self._version(owner_id, artifact_id, artifact.source_head_version_id)
        if version.compile_status not in {"queued", "compiling"}:
            return _paper_descriptor(artifact).model_copy(
                update={"editing_enabled": self._editing_enabled()}
            )
        job_id = (version.compile_diagnostics or {}).get("job_id")
        if not isinstance(job_id, str):
            raise ArtifactError("artifact_corrupt", "Paper compile job is invalid")
        manifest = LatexPaperManifest.model_validate(version.source_manifest)
        bundle = self.storage.read_file(
            f"{version.storage_key}/{_SOURCE_ARCHIVE}",
            max_bytes=self.settings.chat_artifact_max_version_bytes,
        )
        if hashlib.sha256(bundle).hexdigest() != version.source_digest:
            raise ArtifactError(
                "artifact_corrupt", "Paper source digest verification failed"
            )
        compiler = self.compiler or compiler_transport_from_settings(self.settings)
        try:
            provider_job_id = (version.compile_diagnostics or {}).get("provider_job_id")
            resume = getattr(compiler, "resume", None)
            if isinstance(provider_job_id, str) and callable(resume):
                try:
                    status = resume(
                        job_id=job_id,
                        provider_job_id=provider_job_id,
                        bundle=bundle,
                        entrypoint=manifest.root_document,
                    )
                except RuntimeError:
                    # The dedicated VM ended. A replacement remains safe because
                    # the immutable source-version UUID is the logical key.
                    status = compiler.submit(
                        job_id=job_id, bundle=bundle, entrypoint=manifest.root_document
                    )
            else:
                status = compiler.submit(
                    job_id=job_id, bundle=bundle, entrypoint=manifest.root_document
                )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                version.compile_status = (
                    "compiling"
                    if status.state == CompilerJobState.COMPILING
                    else "queued"
                )
                version.compile_diagnostics = {
                    "job_id": job_id,
                    **(
                        {"provider_job_id": status.provider_job_id}
                        if status.provider_job_id is not None
                        else {}
                    ),
                }
            else:
                self._store_compile_result(version, compiler.result(job_id))
        except (httpx.HTTPError, EnvelopeError, RuntimeError, ValueError):
            # A transient poll failure is not a compile failure. Keep the durable
            # source/job state for the next owner poll or later reconciliation.
            pass
        self.db.flush()
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def _editing_enabled(self) -> bool:
        return (
            self.settings.chat_artifacts_enabled
            and self.settings.chat_latex_paper_enabled
            and self.settings.chat_latex_compiler_jobs_enabled
        )

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
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

    def get_artifact_descriptor(
        self, owner_id: str, artifact_id: uuid.UUID
    ) -> LatexPaperArtifactDescriptor:
        artifact = self._artifact(owner_id, artifact_id)
        return _paper_descriptor(artifact).model_copy(
            update={"editing_enabled": self._editing_enabled()}
        )

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
        compiler = self.compiler or compiler_transport_from_settings(self.settings)
        # The immutable source-version ID is the durable idempotency key. A
        # fresh backend process can submit the same bundle after a Space restart
        # without creating a second logical compile job.
        job_id = str(version.id)
        try:
            previous = version.compile_diagnostics or {}
            provider_job_id = previous.get("provider_job_id")
            resume = getattr(compiler, "resume", None)
            if isinstance(provider_job_id, str) and callable(resume):
                try:
                    status = resume(
                        job_id=job_id,
                        provider_job_id=provider_job_id,
                        bundle=bundle,
                        entrypoint=entrypoint,
                    )
                except RuntimeError:
                    # A completed/lost VM is safe to replace: the immutable
                    # version UUID remains the logical idempotency key.
                    status = compiler.submit(
                        job_id=job_id, bundle=bundle, entrypoint=entrypoint
                    )
            else:
                status = compiler.submit(
                    job_id=job_id, bundle=bundle, entrypoint=entrypoint
                )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                submitted_provider_job_id = status.provider_job_id
                status = compiler.status(job_id)
                if (
                    status.provider_job_id is None
                    and submitted_provider_job_id is not None
                ):
                    status = status.model_copy(
                        update={"provider_job_id": submitted_provider_job_id}
                    )
            if status.state not in {
                CompilerJobState.SUCCEEDED,
                CompilerJobState.FAILED,
                CompilerJobState.CANCELED,
            }:
                version.compile_status = (
                    "compiling"
                    if status.state == CompilerJobState.COMPILING
                    else "queued"
                )
                version.compile_diagnostics = {
                    "job_id": job_id,
                    **(
                        {"provider_job_id": status.provider_job_id}
                        if status.provider_job_id is not None
                        else {}
                    ),
                }
                return
            result = compiler.result(job_id)
        except httpx.HTTPError:
            # The durable version remains eligible for the bounded operator
            # reconciliation instead of being falsely finalized on a network
            # failure or a compiler restart.
            version.compile_status = "queued"
            version.compile_diagnostics = {
                "job_id": job_id,
                "failure_category": "transport_failure",
            }
            return
        except (EnvelopeError, RuntimeError, ValueError):
            version.compile_status = "failed"
            version.compile_diagnostics = {
                "job_id": job_id,
                "failure_category": "service_error",
                "errors": [
                    {"severity": "error", "message": "Compiler submission failed"}
                ],
            }
            return
        self._store_compile_result(version, result)

    def reconcile_pending_compiles(self, *, limit: int = 20) -> int:
        """Resume a bounded set of durable versions after transport/Space loss.

        This intentionally does nothing while the compiler kill switch is off.
        It is called by the operator-only reconciliation command, never from a
        request path, so a Space outage cannot amplify normal chat traffic.
        """
        if limit < 1 or not self.settings.chat_latex_compiler_jobs_enabled:
            return 0
        versions = self.db.scalars(
            select(ChatLatexPaperVersion)
            .where(
                ChatLatexPaperVersion.storage_state == "ready",
                ChatLatexPaperVersion.compile_status.in_(("queued", "compiling")),
            )
            .order_by(ChatLatexPaperVersion.created_at)
            .limit(limit)
        ).all()
        reconciled = 0
        for version in versions:
            manifest = LatexPaperManifest.model_validate(version.source_manifest)
            try:
                bundle = self.storage.read_file(
                    f"{version.storage_key}/{_SOURCE_ARCHIVE}",
                    max_bytes=self.settings.chat_artifact_max_version_bytes,
                )
            except (ArtifactError, httpx.HTTPError, OSError, ValueError):
                version.compile_status = "failed"
                version.compile_diagnostics = {
                    "job_id": str(version.id),
                    "failure_category": "lost",
                    "errors": [
                        {
                            "severity": "error",
                            "message": "Compiler source recovery failed",
                        }
                    ],
                }
                reconciled += 1
                continue
            if hashlib.sha256(bundle).hexdigest() != version.source_digest:
                version.compile_status = "failed"
                version.compile_diagnostics = {
                    "job_id": str(version.id),
                    "failure_category": "lost",
                    "errors": [
                        {
                            "severity": "error",
                            "message": "Compiler source digest mismatch",
                        }
                    ],
                }
                reconciled += 1
                continue
            self._compile(version, bundle, manifest.root_document)
            reconciled += 1
        self.db.flush()
        return reconciled

    def _store_compile_result(
        self, version: ChatLatexPaperVersion, result: CompilerResult
    ) -> None:
        diagnostics = [item.model_dump(mode="json") for item in result.diagnostics]
        version.compile_diagnostics = {
            "diagnostics": diagnostics,
            "job_id": result.job_id,
            "pdf_sha256": result.pdf_digest,
            "failure_category": result.failure_category,
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

    def _artifact(
        self, owner_id: str, artifact_id: uuid.UUID, *, lock: bool = False
    ) -> ChatArtifact:
        statement = (
            select(ChatArtifact)
            .join(ChatSession)
            .where(
                ChatArtifact.id == artifact_id,
                ChatArtifact.kind == "latex_paper",
                ChatSession.hf_user_id == owner_id,
            )
        )
        if lock:
            if self.db.bind is not None and self.db.bind.dialect.name == "postgresql":
                self.db.execute(
                    text("SELECT pg_advisory_xact_lock(hashtext(:artifact))"),
                    {"artifact": f"chat-latex-paper-write:{artifact_id}"},
                )
            statement = statement.with_for_update()
        artifact = self.db.scalar(statement)
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

    def _storage_prefix(
        self, session_id: uuid.UUID, artifact_id: uuid.UUID, *, version: int
    ) -> str:
        return "/".join(
            [
                self.settings.chat_artifact_hf_bucket_prefix.strip("/"),
                str(session_id),
                str(artifact_id),
                str(version),
            ]
        )
