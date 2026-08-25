"""Stateless, serialized compiler API for the private Hugging Face Space."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import signal
import stat
import subprocess
import tempfile
import time
import zipfile
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath

from fastapi import FastAPI, HTTPException, Response, status

from latex_compiler_contract import (
    MAX_SOURCE_BYTES,
    CompilerDiagnostic,
    CompilerEnvelope,
    CompilerJobState,
    CompilerResult,
    CompilerStatus,
    CompileSubmission,
    EnvelopeError,
    validate_public_key,
    validate_result,
    verify_envelope,
)

logger = logging.getLogger(__name__)
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,299}$")
_ALLOWED_SUFFIXES = {".tex", ".bib", ".png", ".jpg", ".jpeg", ".pdf"}
_ERROR = re.compile(r"^! (?P<message>.+)$", re.MULTILINE)
_LINE = re.compile(r"^l\.(?P<line>\d+)\s*(?P<message>.*)$", re.MULTILINE)
_WARNING = re.compile(r"^LaTeX Warning: (?P<message>.+)$", re.MULTILINE)
COMPILER_IMAGE = os.environ.get("PWC_LATEX_COMPILER_IMAGE", "unqualified-image")
ENGINE_VERSION = os.environ.get("PWC_LATEX_COMPILER_ENGINE", "pdfLaTeX")


class BundleError(ValueError):
    pass


Compiler = Callable[[CompilerEnvelope, bytes], Awaitable[CompilerResult]]


@dataclass
class _Job:
    envelope: CompilerEnvelope
    bundle: bytes
    state: CompilerJobState = CompilerJobState.QUEUED
    result: CompilerResult | None = None

    def status(self) -> CompilerStatus:
        return CompilerStatus(job_id=self.envelope.job_id, state=self.state)

    def has_same_submission(self, envelope: CompilerEnvelope) -> bool:
        return (
            self.envelope.source_digest == envelope.source_digest
            and self.envelope.source_bytes == envelope.source_bytes
            and self.envelope.entrypoint == envelope.entrypoint
            and self.envelope.limits == envelope.limits
            and self.envelope.contract_version == envelope.contract_version
        )


class JobManager:
    """In-memory queue intentionally keeps a single compiler active at a time."""

    def __init__(self, compiler: Compiler) -> None:
        self.compiler = compiler
        self.jobs: dict[str, _Job] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.worker: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self.worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass

    async def submit(self, envelope: CompilerEnvelope, bundle: bytes) -> CompilerStatus:
        existing = self.jobs.get(envelope.job_id)
        if existing is not None:
            if not existing.has_same_submission(envelope):
                raise BundleError("Job ID conflicts with an existing submission")
            return existing.status()
        job = _Job(envelope=envelope, bundle=bundle)
        self.jobs[envelope.job_id] = job
        self.queue.put_nowait(envelope.job_id)
        logger.info(
            "latex_compiler queued job=%s digest=%s bytes=%d",
            envelope.job_id,
            envelope.source_digest[:12],
            len(bundle),
        )
        return job.status()

    def status(self, job_id: str) -> CompilerStatus | None:
        job = self.jobs.get(job_id)
        return job.status() if job else None

    def result(self, job_id: str) -> CompilerResult | None:
        job = self.jobs.get(job_id)
        return job.result if job else None

    async def cancel(self, job_id: str) -> CompilerStatus | None:
        job = self.jobs.get(job_id)
        if job is None:
            return None
        if job.state in {CompilerJobState.QUEUED, CompilerJobState.COMPILING}:
            job.state = CompilerJobState.CANCELED
            job.result = CompilerResult.canceled(
                job.envelope,
                compiler_image=COMPILER_IMAGE,
                engine_version=ENGINE_VERSION,
            )
            cancel = getattr(self.compiler, "cancel", None)
            if cancel is not None:
                cancel(job_id)
        return job.status()

    async def _work(self) -> None:
        while True:
            job_id = await self.queue.get()
            job = self.jobs[job_id]
            if job.state == CompilerJobState.CANCELED:
                continue
            job.state = CompilerJobState.COMPILING
            try:
                result = await self.compiler(job.envelope, job.bundle)
                validate_result(result, expected=job.envelope)
            except Exception:
                logger.exception("latex_compiler failed job=%s", job.envelope.job_id)
                result = CompilerResult.failed(
                    job.envelope,
                    diagnostics=[
                        CompilerDiagnostic(
                            severity="error", message="The compiler service failed"
                        )
                    ],
                    log_tail="",
                    compiler_image=COMPILER_IMAGE,
                    engine_version=ENGINE_VERSION,
                    elapsed_ms=0,
                )
            if job.state != CompilerJobState.CANCELED:
                job.result = result
                job.state = result.state
                logger.info(
                    "latex_compiler completed job=%s digest=%s state=%s pdf_bytes=%d",
                    job.envelope.job_id,
                    job.envelope.source_digest[:12],
                    job.state,
                    result.pdf_bytes,
                )


class LatexCompilerRunner:
    """Runs a single constrained latexmk process in a freshly extracted root."""

    def __init__(self) -> None:
        self.processes: dict[str, subprocess.Popen[bytes]] = {}

    async def __call__(
        self, envelope: CompilerEnvelope, bundle: bytes
    ) -> CompilerResult:
        return await asyncio.to_thread(self._compile, envelope, bundle)

    def cancel(self, job_id: str) -> None:
        process = self.processes.get(job_id)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)

    def _compile(self, envelope: CompilerEnvelope, bundle: bytes) -> CompilerResult:
        started_at = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="pwc-latex-") as temporary:
                root = Path(temporary)
                _extract_bundle(bundle, root, envelope)
                log_path = root / "compiler.log"
                with log_path.open("xb") as log:
                    process = subprocess.Popen(
                        [
                            "prlimit",
                            "--cpu=120:120",
                            "--as=1073741824:1073741824",
                            "--fsize=26214400:26214400",
                            "--nofile=64:64",
                            "--nproc=16:16",
                            "--",
                            "latexmk",
                            "-norc",
                            "-pdf",
                            "-bibtex",
                            "-interaction=nonstopmode",
                            "-halt-on-error",
                            "-no-shell-escape",
                            envelope.entrypoint,
                        ],
                        cwd=root,
                        stdin=subprocess.DEVNULL,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env=_compiler_environment(root),
                        start_new_session=True,
                    )
                    self.processes[envelope.job_id] = process
                    try:
                        process.wait(timeout=envelope.limits.timeout_seconds)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        return _failed_result(
                            envelope,
                            _read_tail(log_path, envelope.limits.max_log_bytes),
                            started_at,
                            "Compilation exceeded its time limit",
                        )
                    finally:
                        self.processes.pop(envelope.job_id, None)
                output = _read_tail(log_path, envelope.limits.max_log_bytes)
                if process.returncode != 0:
                    return _failed_result(envelope, output, started_at, None)
                pdf_path = root / PurePosixPath(envelope.entrypoint).with_suffix(".pdf")
                if pdf_path.stat().st_size > envelope.limits.max_pdf_bytes:
                    return _failed_result(
                        envelope, output, started_at, "Compiled PDF exceeds its limit"
                    )
                pdf = pdf_path.read_bytes()
                return CompilerResult.succeeded(
                    envelope,
                    pdf=pdf,
                    log_tail=_log_tail(output, envelope.limits.max_log_bytes),
                    compiler_image=COMPILER_IMAGE,
                    engine_version=ENGINE_VERSION,
                    elapsed_ms=_elapsed_ms(started_at),
                    diagnostics=_diagnostics(output),
                )
        except BundleError as error:
            return _failed_result(envelope, b"", started_at, str(error))
        except (OSError, subprocess.SubprocessError):
            return _failed_result(
                envelope, b"", started_at, "Compiler execution failed"
            )


def create_app(*, public_key: str, compiler: Compiler | None = None) -> FastAPI:
    manager = JobManager(compiler or LatexCompilerRunner())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        try:
            validate_public_key(public_key)
        except EnvelopeError as error:
            raise RuntimeError("PWC_LATEX_COMPILER_PUBLIC_KEY is required") from error
        await manager.start()
        yield
        await manager.stop()

    app = FastAPI(
        title="PwC private LaTeX compiler",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @app.post(
        "/v1/jobs", response_model=CompilerStatus, status_code=status.HTTP_202_ACCEPTED
    )
    async def submit(submission: CompileSubmission) -> CompilerStatus:
        try:
            verify_envelope(submission.envelope, submission.signature, public_key)
            bundle = base64.b64decode(submission.bundle_base64, validate=True)
            if len(bundle) != submission.envelope.source_bytes:
                raise BundleError("Source bundle byte count is invalid")
            if len(bundle) > submission.envelope.limits.max_source_bytes:
                raise BundleError("Source bundle exceeds its limit")
            if hashlib.sha256(bundle).hexdigest() != submission.envelope.source_digest:
                raise BundleError("Source bundle digest is invalid")
            response = await manager.submit(submission.envelope, bundle)
            await asyncio.sleep(0)
            return response
        except EnvelopeError as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid compiler request",
            ) from error
        except (ValueError, BundleError) as error:
            code = (
                status.HTTP_409_CONFLICT
                if "conflicts" in str(error)
                else status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            raise HTTPException(
                status_code=code, detail="Invalid compiler bundle"
            ) from error

    @app.get("/v1/jobs/{job_id}", response_model=CompilerStatus)
    async def job_status(job_id: str) -> CompilerStatus:
        response = manager.status(job_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
            )
        return response

    @app.get("/v1/jobs/{job_id}/result", response_model=CompilerResult)
    async def job_result(job_id: str) -> CompilerResult:
        response = manager.result(job_id)
        if response is None:
            if manager.status(job_id) is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
                )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Compiler job is not complete",
            )
        return response

    @app.delete("/v1/jobs/{job_id}", response_model=CompilerStatus)
    async def cancel(job_id: str) -> CompilerStatus:
        response = await manager.cancel(job_id)
        if response is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Unknown compiler job"
            )
        return response

    @app.get("/health", status_code=status.HTTP_204_NO_CONTENT)
    async def health() -> Response:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return app


def _extract_bundle(bundle: bytes, root: Path, envelope: CompilerEnvelope) -> None:
    if len(bundle) > min(envelope.limits.max_source_bytes, MAX_SOURCE_BYTES):
        raise BundleError("Source bundle exceeds its limit")
    try:
        archive = zipfile.ZipFile(BytesIO(bundle))
    except zipfile.BadZipFile as error:
        raise BundleError("Source bundle is not a ZIP archive") from error
    total_bytes = 0
    names: set[str] = set()
    with archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = _safe_member_name(member)
            if name in names:
                raise BundleError("Source bundle has duplicate paths")
            names.add(name)
            if len(names) > envelope.limits.max_files:
                raise BundleError("Source bundle has too many files")
            total_bytes += member.file_size
            if total_bytes > envelope.limits.max_source_bytes:
                raise BundleError("Source bundle expands beyond its limit")
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination.open("xb") as target:
                while chunk := source.read(64 * 1024):
                    target.write(chunk)
            if destination.suffix.lower() in {".tex", ".bib"}:
                try:
                    destination.read_text(encoding="utf-8")
                except UnicodeDecodeError as error:
                    raise BundleError("Source bundle text must be UTF-8") from error
    if envelope.entrypoint not in names:
        raise BundleError("Source bundle does not contain its entrypoint")


def _safe_member_name(member: zipfile.ZipInfo) -> str:
    name = member.filename
    path = PurePosixPath(name)
    if (
        not _SAFE_PATH.fullmatch(name)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.lower() not in _ALLOWED_SUFFIXES
        or stat.S_ISLNK(member.external_attr >> 16)
    ):
        raise BundleError("Source bundle contains an unsafe file")
    return path.as_posix()


def _compiler_environment(root: Path) -> dict[str, str]:
    home = root / ".home"
    home.mkdir()
    return {
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "TEXMFOUTPUT": str(root),
        "openin_any": "p",
        "openout_any": "p",
        "shell_escape": "f",
    }


def _failed_result(
    envelope: CompilerEnvelope, output: bytes, started_at: float, message: str | None
) -> CompilerResult:
    diagnostics = _diagnostics(output)
    if message is not None:
        diagnostics.insert(0, CompilerDiagnostic(severity="error", message=message))
    if not diagnostics:
        diagnostics = [
            CompilerDiagnostic(severity="error", message="Compilation failed")
        ]
    return CompilerResult.failed(
        envelope,
        diagnostics=diagnostics,
        log_tail=_log_tail(output, envelope.limits.max_log_bytes),
        compiler_image=COMPILER_IMAGE,
        engine_version=ENGINE_VERSION,
        elapsed_ms=_elapsed_ms(started_at),
    )


def _diagnostics(output: bytes) -> list[CompilerDiagnostic]:
    text = output.decode("utf-8", errors="replace")
    errors = [
        CompilerDiagnostic(severity="error", message=match.group("message")[:1000])
        for match in _ERROR.finditer(text)
    ]
    warnings = [
        CompilerDiagnostic(severity="warning", message=match.group("message")[:1000])
        for match in _WARNING.finditer(text)
    ]
    line = _LINE.search(text)
    if errors and line:
        errors[0] = errors[0].model_copy(
            update={
                "line": int(line.group("line")),
                "message": line.group("message")[:1000] or errors[0].message,
            }
        )
    return (errors + warnings)[:100]


def _log_tail(output: bytes, maximum: int) -> str:
    return output[-maximum:].decode("utf-8", errors="replace")


def _read_tail(path: Path, maximum: int) -> bytes:
    with path.open("rb") as log:
        log.seek(0, os.SEEK_END)
        log.seek(max(0, log.tell() - maximum))
        return log.read(maximum)


def _elapsed_ms(started_at: float) -> int:
    return min(120_000, int((time.monotonic() - started_at) * 1000))


app = create_app(public_key=os.environ.get("PWC_LATEX_COMPILER_PUBLIC_KEY", ""))
