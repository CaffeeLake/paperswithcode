from __future__ import annotations

import asyncio
import base64
import hashlib
import time
import uuid
import zipfile
from io import BytesIO

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient

from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerResult,
    CompileSubmission,
    EnvelopeError,
    sign_envelope,
    verify_envelope,
)
from latex_compiler_space.app import (
    BundleError,
    _extract_bundle,
    _read_tail,
    create_app,
)


def _keys() -> tuple[Ed25519PrivateKey, str]:
    private_key = Ed25519PrivateKey.generate()
    public_key = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode()
    return private_key, public_key


def _submission(
    private_key: Ed25519PrivateKey,
    *,
    job_id: str | None = None,
    source: bytes = b"source bundle",
    expires_at: int | None = None,
) -> CompileSubmission:
    envelope = CompilerEnvelope(
        job_id=job_id or str(uuid.uuid4()),
        source_digest=hashlib.sha256(source).hexdigest(),
        source_bytes=len(source),
        entrypoint="main.tex",
        limits=CompileLimits(),
        expires_at=expires_at or int(time.time()) + 60,
    )
    return CompileSubmission(
        envelope=envelope,
        signature=sign_envelope(envelope, private_key),
        bundle_base64=base64.b64encode(source).decode(),
    )


def test_envelope_signature_binds_limits_digest_and_expiry() -> None:
    private_key, public_key = _keys()
    submission = _submission(private_key)

    verify_envelope(
        submission.envelope, submission.signature, public_key, now=time.time()
    )

    with pytest.raises(EnvelopeError, match="signature"):
        verify_envelope(
            submission.envelope.model_copy(update={"source_digest": "0" * 64}),
            submission.signature,
            public_key,
            now=time.time(),
        )
    with pytest.raises(EnvelopeError, match="expired"):
        verify_envelope(
            submission.envelope.model_copy(update={"expires_at": 1}),
            submission.signature,
            public_key,
            now=time.time(),
        )


def test_compiler_reuses_same_job_and_rejects_conflicting_submission() -> None:
    private_key, public_key = _keys()
    calls: list[str] = []

    async def compiler(envelope: CompilerEnvelope, source: bytes) -> CompilerResult:
        calls.append(envelope.job_id)
        return CompilerResult.succeeded(
            envelope,
            pdf=b"%PDF-test",
            log_tail="",
            compiler_image="test-image",
            engine_version="pdfTeX test",
        )

    app = create_app(public_key=public_key, compiler=compiler)
    submission = _submission(private_key)
    with TestClient(app) as client:
        first = client.post("/v1/jobs", json=submission.model_dump(mode="json"))
        second = client.post("/v1/jobs", json=submission.model_dump(mode="json"))
        assert first.status_code == 202
        assert second.status_code == 202

        result = client.get(f"/v1/jobs/{submission.envelope.job_id}/result")
        assert result.status_code == 200
        assert result.json()["source_digest"] == submission.envelope.source_digest
        assert len(calls) == 1

        conflicting = _submission(
            private_key,
            job_id=submission.envelope.job_id,
            source=b"different source",
        )
        conflict = client.post("/v1/jobs", json=conflicting.model_dump(mode="json"))
        assert conflict.status_code == 409


def test_compiler_rejects_invalid_signature_and_expired_envelope() -> None:
    private_key, public_key = _keys()
    app = create_app(public_key=public_key)
    with TestClient(app) as client:
        invalid = _submission(private_key).model_copy(
            update={"signature": "not-a-signature"}
        )
        assert (
            client.post("/v1/jobs", json=invalid.model_dump(mode="json")).status_code
            == 401
        )

        expired = _submission(private_key, expires_at=1)
        assert (
            client.post("/v1/jobs", json=expired.model_dump(mode="json")).status_code
            == 401
        )


def test_cancellation_has_a_terminal_result() -> None:
    private_key, public_key = _keys()
    started = asyncio.Event()
    release = asyncio.Event()

    async def compiler(envelope: CompilerEnvelope, source: bytes) -> CompilerResult:
        started.set()
        await release.wait()
        return CompilerResult.succeeded(
            envelope,
            pdf=b"%PDF-test",
            log_tail="",
            compiler_image="test-image",
            engine_version="pdfTeX test",
        )

    app = create_app(public_key=public_key, compiler=compiler)
    submission = _submission(private_key)
    with TestClient(app) as client:
        assert (
            client.post("/v1/jobs", json=submission.model_dump(mode="json")).status_code
            == 202
        )
        canceled = client.delete(f"/v1/jobs/{submission.envelope.job_id}")
        assert canceled.json()["state"] == "canceled"
        result = client.get(f"/v1/jobs/{submission.envelope.job_id}/result")
        assert result.status_code == 200
        assert result.json()["state"] == "canceled"


def test_compiler_rejects_unsafe_or_non_utf8_source_bundle(tmp_path) -> None:
    private_key, _ = _keys()
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../escape.tex", "\\documentclass{article}")
    source = archive.getvalue()
    submission = _submission(private_key, source=source)
    with pytest.raises(BundleError, match="unsafe"):
        _extract_bundle(source, tmp_path, submission.envelope)

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("main.tex", b"\xff")
    source = archive.getvalue()
    submission = _submission(private_key, source=source)
    with pytest.raises(BundleError, match="UTF-8"):
        _extract_bundle(source, tmp_path, submission.envelope)


def test_compiler_reads_only_a_bounded_log_tail(tmp_path) -> None:
    path = tmp_path / "compiler.log"
    path.write_bytes(b"prefix" + b"x" * 100 + b"tail")

    assert _read_tail(path, 4) == b"tail"
