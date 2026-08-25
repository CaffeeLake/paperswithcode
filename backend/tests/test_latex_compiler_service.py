from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.services.latex_compiler_service import LatexCompilerClient
from latex_compiler_contract import (
    CompileLimits,
    CompilerEnvelope,
    CompilerResult,
    EnvelopeError,
)


def test_client_signs_submits_polls_cancels_and_reads_result() -> None:
    private_key = Ed25519PrivateKey.generate()
    source = b"zip bytes"
    observed: list[httpx.Request] = []
    job_id = str(uuid.uuid4())

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            assert (
                payload["envelope"]["source_digest"]
                == hashlib.sha256(source).hexdigest()
            )
            assert payload["bundle_base64"] == base64.b64encode(source).decode()
            return httpx.Response(202, json={"job_id": job_id, "state": "queued"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"job_id": job_id, "state": "canceled"})
        if request.url.path.endswith("/result"):
            result = CompilerResult.succeeded(
                CompilerEnvelope(
                    job_id=job_id,
                    source_digest=hashlib.sha256(source).hexdigest(),
                    source_bytes=len(source),
                    entrypoint="main.tex",
                    limits=CompileLimits(),
                    expires_at=int(time.time()) + 60,
                ),
                pdf=b"%PDF-test",
                log_tail="",
                compiler_image="test-image",
                engine_version="pdfTeX test",
            )
            return httpx.Response(200, json=result.model_dump(mode="json"))
        return httpx.Response(200, json={"job_id": job_id, "state": "compiling"})

    client = LatexCompilerClient(
        "https://compiler.example.invalid",
        private_key=private_key,
        hf_token="space-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    submission = client.submit(job_id=job_id, bundle=source, entrypoint="main.tex")
    assert submission.job_id == job_id
    assert client.status(job_id).state == "compiling"
    assert client.cancel(job_id).state == "canceled"
    assert client.result(job_id).pdf == b"%PDF-test"
    assert observed[0].headers["authorization"] == "Bearer space-token"


def test_client_rejects_a_response_for_another_job() -> None:
    private_key = Ed25519PrivateKey.generate()
    client = LatexCompilerClient(
        "https://compiler.example.invalid",
        private_key=private_key,
        http_client=httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    202, json={"job_id": str(uuid.uuid4()), "state": "queued"}
                )
            )
        ),
    )

    with pytest.raises(EnvelopeError, match="requested job"):
        client.submit(job_id=str(uuid.uuid4()), bundle=b"source", entrypoint="main.tex")
