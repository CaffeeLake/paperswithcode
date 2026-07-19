"""Bounded protected-HF-endpoint query encoder with immediate fallback semantics."""

from __future__ import annotations

import hashlib
import logging
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache

import httpx


logger = logging.getLogger("backend.embedding_query")
logger.setLevel(logging.INFO)


class QueryEmbeddingUnavailable(RuntimeError):
    """The semantic branch should be skipped without failing search."""


@dataclass(frozen=True)
class QueryEmbeddingContract:
    generation_id: int
    model_name: str
    model_revision: str
    dimensions: int
    instruction_version: str


class QueryEmbeddingClient:
    def __init__(
        self,
        *,
        endpoint_url: str,
        token: str,
        timeout_ms: int = 500,
        max_concurrency: int = 4,
        failure_threshold: int = 3,
        recovery_seconds: float = 30.0,
        cache_ttl_seconds: float = 300.0,
        cache_size: int = 256,
        transport: httpx.BaseTransport | None = None,
    ):
        self.endpoint_url = endpoint_url
        self.token = token
        self.timeout = timeout_ms / 1000
        self.semaphore = threading.BoundedSemaphore(max_concurrency)
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self.cache_size = cache_size
        self.failures = 0
        self.opened_at = 0.0
        self.cache: OrderedDict[str, tuple[float, list[float]]] = OrderedDict()
        self.http = httpx.Client(transport=transport, timeout=self.timeout)

    def _cache_key(self, query: str, contract: QueryEmbeddingContract) -> str:
        payload = (
            f"{contract.generation_id}:{contract.model_revision}:"
            f"{contract.instruction_version}:{query}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def _validate(self, payload: object, dimensions: int) -> list[float]:
        if isinstance(payload, dict):
            payload = payload.get("embeddings")
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            payload = payload[0]
        if not isinstance(payload, list) or len(payload) != dimensions:
            raise QueryEmbeddingUnavailable("malformed_dimensions")
        vector = [float(value) for value in payload]
        if not all(math.isfinite(value) for value in vector):
            raise QueryEmbeddingUnavailable("non_finite_vector")
        norm = math.sqrt(sum(value * value for value in vector))
        if not 0.98 <= norm <= 1.02:
            raise QueryEmbeddingUnavailable("non_normalized_vector")
        return vector

    def encode(self, query: str, contract: QueryEmbeddingContract) -> list[float]:
        now = time.monotonic()
        if (
            self.failures >= self.failure_threshold
            and now - self.opened_at < self.recovery_seconds
        ):
            raise QueryEmbeddingUnavailable("circuit_open")
        key = self._cache_key(query, contract)
        cached = self.cache.get(key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            self.cache.move_to_end(key)
            return cached[1]
        if not self.endpoint_url or not self.token:
            raise QueryEmbeddingUnavailable("endpoint_not_configured")
        if not self.semaphore.acquire(blocking=False):
            raise QueryEmbeddingUnavailable("concurrency_limit")
        started = time.perf_counter()
        try:
            response = self.http.post(
                self.endpoint_url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={
                    "inputs": [query],
                    "dimensions": contract.dimensions,
                    "normalize": True,
                    "prompt_name": "query",
                },
            )
            response.raise_for_status()
            vector = self._validate(response.json(), contract.dimensions)
            self.failures = 0
            self.cache[key] = (now, vector)
            self.cache.move_to_end(key)
            while len(self.cache) > self.cache_size:
                self.cache.popitem(last=False)
            logger.info(
                "query_embedding success generation=%s latency_ms=%.1f",
                contract.generation_id,
                (time.perf_counter() - started) * 1000,
            )
            return vector
        except (httpx.HTTPError, ValueError, QueryEmbeddingUnavailable) as error:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()
            reason = str(error)[:120]
            logger.warning(
                "query_embedding fallback generation=%s reason=%s latency_ms=%.1f",
                contract.generation_id,
                reason,
                (time.perf_counter() - started) * 1000,
            )
            raise QueryEmbeddingUnavailable(reason) from error
        finally:
            self.semaphore.release()


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(format(value, ".8g") for value in vector) + "]"


@lru_cache(maxsize=4)
def get_query_embedding_client(
    endpoint_url: str,
    token: str,
    timeout_ms: int,
    max_concurrency: int,
) -> QueryEmbeddingClient:
    """Share cache, concurrency, and circuit state within each API process."""
    return QueryEmbeddingClient(
        endpoint_url=endpoint_url,
        token=token,
        timeout_ms=timeout_ms,
        max_concurrency=max_concurrency,
    )
