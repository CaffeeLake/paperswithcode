"""Tests for bounded active-generation embedding refreshes."""

from __future__ import annotations

import json

import httpx
import pytest

from backend.services.incremental_paper_embeddings import (
    ActiveEmbeddingGeneration,
    EmbeddingCandidate,
    encode_documents,
    upsert_current_embeddings,
)


def test_encode_documents_uses_document_contract():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        payload = json.loads(request.content)
        assert payload == {
            "inputs": ["Title\n\nAbstract"],
            "dimensions": 2,
            "normalize": True,
            "prompt_name": "document",
        }
        return httpx.Response(200, json=[[1.0, 0.0]])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = encode_documents(
            client,
            endpoint_url="https://endpoint.example",
            token="secret",
            texts=["Title\n\nAbstract"],
            dimensions=2,
        )
    assert vectors == [[1.0, 0.0]]


def test_encode_documents_retries_cold_endpoint(monkeypatch):
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json=[[1.0, 0.0]])

    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        vectors = encode_documents(
            client,
            endpoint_url="https://endpoint.example",
            token="secret",
            texts=["paper"],
            dimensions=2,
        )
    assert vectors == [[1.0, 0.0]]
    assert calls == 2


@pytest.mark.parametrize(
    "payload",
    [
        [[1.0]],
        [[0.5, 0.0]],
        [[float("nan"), 0.0]],
    ],
)
def test_encode_documents_rejects_invalid_vectors(payload):
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=payload))
    with httpx.Client(transport=transport) as client:
        with pytest.raises(ValueError):
            encode_documents(
                client,
                endpoint_url="https://endpoint.example",
                token="secret",
                texts=["paper"],
                dimensions=2,
            )


def test_upsert_discards_source_that_changed_during_inference():
    statements = []

    class Result:
        def mappings(self):
            return self

        def __iter__(self):
            return iter([{"id": 7, "title": "Changed", "abstract": "New abstract"}])

    class FakeDatabase:
        committed = False

        def execute(self, statement, _params=None):
            statements.append(str(statement))
            return Result()

        def commit(self):
            self.committed = True

    candidate = EmbeddingCandidate(
        paper_id=7,
        title="Original",
        abstract="Old abstract",
        content_hash="0" * 64,
    )
    embedded, stale = upsert_current_embeddings(
        FakeDatabase(),
        generation=ActiveEmbeddingGeneration(1, "model", "rev", 2, "input"),
        candidates=[candidate],
        vectors=[[1.0, 0.0]],
    )
    assert (embedded, stale) == (0, 1)
    assert len(statements) == 1
