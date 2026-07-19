"""Deterministic contracts shared by embedding export, workers, and serving."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INPUT_FORMAT_VERSION = "title-abstract-v1"
MANIFEST_SCHEMA_VERSION = "paper-embeddings-v1"
_WHITESPACE = re.compile(r"\s+")


def normalize_embedding_text(value: str | None) -> str:
    """Trim and collapse whitespace while preserving case, punctuation and Unicode."""
    return _WHITESPACE.sub(" ", value or "").strip()


def build_embedding_input(title: str, abstract: str | None) -> str:
    normalized_title = normalize_embedding_text(title)
    normalized_abstract = normalize_embedding_text(abstract)
    return (
        f"{normalized_title}\n\n{normalized_abstract}"
        if normalized_abstract
        else normalized_title
    )


def content_hash(title: str, abstract: str | None) -> str:
    payload = f"{INPUT_FORMAT_VERSION}\0{build_embedding_input(title, abstract)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class ShardManifest:
    path: str
    rows: int
    sha256: str


@dataclass(frozen=True)
class EmbeddingRunManifest:
    schema_version: str
    run_id: str
    created_at: str
    model_name: str
    model_revision: str
    dimensions: int
    input_format_version: str
    corpus_snapshot: str
    row_count: int
    shards: list[ShardManifest]
    normalization: str = "l2"
    query_instruction_version: str = "model-encode-query-v1"

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        model_name: str,
        model_revision: str,
        dimensions: int,
        corpus_snapshot: str,
        row_count: int,
        shards: list[ShardManifest],
    ) -> "EmbeddingRunManifest":
        return cls(
            schema_version=MANIFEST_SCHEMA_VERSION,
            run_id=run_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            model_name=model_name,
            model_revision=model_revision,
            dimensions=dimensions,
            input_format_version=INPUT_FORMAT_VERSION,
            corpus_snapshot=corpus_snapshot,
            row_count=row_count,
            shards=shards,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: Path) -> None:
        path.write_text(
            json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @classmethod
    def read(cls, path: Path) -> "EmbeddingRunManifest":
        data = json.loads(path.read_text(encoding="utf-8"))
        shards = [ShardManifest(**item) for item in data.pop("shards")]
        manifest = cls(shards=shards, **data)
        if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
            raise ValueError(f"Unsupported manifest schema: {manifest.schema_version}")
        if manifest.input_format_version != INPUT_FORMAT_VERSION:
            raise ValueError(
                f"Input contract mismatch: {manifest.input_format_version}"
            )
        return manifest

    def validate_files(self, root: Path) -> None:
        rows = 0
        for shard in self.shards:
            path = root / shard.path
            if not path.is_file():
                raise ValueError(f"Missing shard: {path}")
            if sha256_file(path) != shard.sha256:
                raise ValueError(f"Checksum mismatch: {path}")
            rows += shard.rows
        if rows != self.row_count:
            raise ValueError(f"Manifest row mismatch: {rows} != {self.row_count}")
