"""PwC-owned authenticated transport for the private LaTeX compiler Space."""

from __future__ import annotations

import base64
import hashlib
import time
from typing import Protocol

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.config import Settings
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerResult,
    CompilerStatus,
    CompileSubmission,
    EnvelopeError,
    sign_envelope,
    validate_result,
)


class LatexCompilerTransport(Protocol):
    def submit(
        self,
        *,
        job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus: ...

    def status(self, job_id: str) -> CompilerStatus: ...

    def result(self, job_id: str) -> CompilerResult: ...

    def cancel(self, job_id: str) -> CompilerStatus: ...


class LatexCompilerClient:
    """Signs calls locally; the Space receives no durable PwC credential."""

    def __init__(
        self,
        base_url: str,
        *,
        private_key: Ed25519PrivateKey,
        hf_token: str = "",
        http_client: httpx.Client | None = None,
        clock=time.time,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.private_key = private_key
        self.clock = clock
        self.http_client = http_client or httpx.Client(timeout=15.0)
        self.headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
        self._submitted: dict[str, CompilerEnvelope] = {}

    def submit(
        self,
        *,
        job_id: str,
        bundle: bytes,
        entrypoint: str,
        limits: CompileLimits | None = None,
    ) -> CompilerStatus:
        selected_limits = limits or CompileLimits()
        envelope = CompilerEnvelope(
            job_id=job_id,
            source_digest=hashlib.sha256(bundle).hexdigest(),
            source_bytes=len(bundle),
            entrypoint=entrypoint,
            limits=selected_limits,
            expires_at=int(self.clock()) + 5 * 60,
        )
        submission = CompileSubmission(
            envelope=envelope,
            signature=sign_envelope(envelope, self.private_key),
            bundle_base64=base64.b64encode(bundle).decode("ascii"),
        )
        response = self.http_client.post(
            f"{self.base_url}/v1/jobs",
            headers=self.headers,
            json=submission.model_dump(mode="json"),
        )
        response.raise_for_status()
        status = _status(response, job_id)
        self._submitted[job_id] = envelope
        return status

    def status(self, job_id: str) -> CompilerStatus:
        response = self.http_client.get(
            f"{self.base_url}/v1/jobs/{job_id}", headers=self.headers
        )
        response.raise_for_status()
        return _status(response, job_id)

    def result(self, job_id: str) -> CompilerResult:
        response = self.http_client.get(
            f"{self.base_url}/v1/jobs/{job_id}/result", headers=self.headers
        )
        response.raise_for_status()
        result = CompilerResult.model_validate_json(response.content)
        expected = self._submitted.get(job_id)
        if expected is None:
            raise EnvelopeError("Compiler result has no locally submitted envelope")
        validate_result(result, expected=expected)
        return result

    def cancel(self, job_id: str) -> CompilerStatus:
        response = self.http_client.delete(
            f"{self.base_url}/v1/jobs/{job_id}", headers=self.headers
        )
        response.raise_for_status()
        return _status(response, job_id)


def compiler_client_from_settings(settings: Settings) -> LatexCompilerClient:
    """Build the disabled-by-default client without exposing key parsing to callers."""
    key = settings.chat_latex_compiler_signing_private_key
    if not key:
        raise RuntimeError("LaTeX compiler signing key is not configured")
    try:
        raw = base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))
        private_key = Ed25519PrivateKey.from_private_bytes(raw)
    except ValueError as error:
        raise RuntimeError("LaTeX compiler signing key is invalid") from error
    url = settings.chat_latex_compiler_url
    if not url:
        raise RuntimeError("LaTeX compiler URL is not configured")
    return LatexCompilerClient(
        url,
        private_key=private_key,
        hf_token=settings.chat_latex_compiler_hf_token,
    )


def _status(response: httpx.Response, expected_job_id: str) -> CompilerStatus:
    status = CompilerStatus.model_validate_json(response.content)
    if status.job_id != expected_job_id:
        raise EnvelopeError("Compiler response does not match the requested job")
    return status
