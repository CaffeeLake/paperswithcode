from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError
from PyPDF2 import PdfWriter
from sqlalchemy import create_engine, event, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.config import Settings
from backend.models.chat import DISPLAY_BLOCKS_ADAPTER
from backend.models.database import (
    Base,
    ChatArtifact,
    ChatArtifactVersion,
    ChatMessageRecord,
    ChatSession,
    ChatShare,
    ChatSharedArtifact,
)
from backend.services.chat_artifact_service import (
    ArtifactError,
    ChatArtifactService,
    LocalArtifactStorage,
    PosterPaperProvenance,
    normalize_public_https_url,
)
from backend.services.chat_session_service import ChatOwner
from backend.services.chat_share_service import ChatShareService


def _paper_provenance() -> PosterPaperProvenance:
    return PosterPaperProvenance(
        route_id="1706.03762",
        paper_id="1",
        arxiv_id="1706.03762v7",
        paper_version="v7",
        content_sha256="a" * 64,
        source_available=True,
    )


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kwargs):
    return "JSON"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _sqlite_jsonb_typeof(connection, _record):
        connection.create_function(
            "jsonb_typeof",
            1,
            lambda value: "array" if isinstance(json.loads(value), list) else "object",
        )

    Base.metadata.create_all(
        engine,
        tables=[
            ChatSession.__table__,
            ChatMessageRecord.__table__,
            ChatArtifact.__table__,
            ChatArtifactVersion.__table__,
            ChatShare.__table__,
            ChatSharedArtifact.__table__,
        ],
    )
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX idx_chat_messages_current_revision")
    with Session(engine) as session:
        yield session


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        chat_artifacts_enabled=True,
        chat_posterly_enabled=True,
        chat_artifact_shared_preview_enabled=True,
        chat_artifact_storage_backend="local",
        chat_artifact_local_dir=str(tmp_path / "storage"),
    )


def _active_session(
    db: Session, *, owner: str = "owner-1"
) -> tuple[uuid.UUID, uuid.UUID]:
    session_id = uuid.uuid4()
    turn_id = uuid.uuid4()
    db.add(
        ChatSession(
            id=session_id,
            hf_user_id=owner,
            hf_username="owner",
            selected_model="model",
            execution_backend="modal_cli",
            active_turn_id=turn_id,
        )
    )
    db.flush()
    return session_id, turn_id


def _bundle(
    directory: Path,
    *,
    identifier: str = "attention-poster",
    gate_status: str = "passed",
    remote_image: bool = False,
) -> Path:
    source = directory / "source"
    source.mkdir(parents=True)
    image = Image.new("RGB", (600, 360), "white")
    image.save(source / "poster_preview.png", format="PNG")
    html = """
<!doctype html><style>@page { size: 60in 36in; margin: 0; }</style>
<main class="poster">Poster</main>
"""
    if remote_image:
        html += '<img src="https://example.com/tracker.png">'
    (source / "poster.html").write_text(html, encoding="utf-8")
    (source / "GATE_REPORT.json").write_text(
        json.dumps({"gate_status": gate_status}), encoding="utf-8"
    )
    downloads = []
    if gate_status != "failed":
        writer = PdfWriter()
        writer.add_blank_page(width=60 * 72, height=36 * 72)
        with (source / "poster_preview.pdf").open("wb") as output:
            writer.write(output)
        downloads = [{"path": "poster_preview.pdf", "label": "Print PDF"}]
    manifest = {
        "schema_version": 1,
        "identifier": identifier,
        "kind": "posterly",
        "title": "Attention Is All You Need",
        "canvas": {
            "width": 60.0,
            "height": 36.0,
            "unit": "in",
            "orientation": "landscape",
        },
        "qr_destination": None,
        "entrypoint": "poster.html",
        "preview": "poster_preview.png",
        "downloads": downloads,
        "source_files": ["poster.html", "GATE_REPORT.json"],
        "gate_report": "GATE_REPORT.json",
        "gate_status": gate_status,
        "gate_summary": [],
        "paper": {
            "route_id": "1706.03762",
            "paper_id": "1",
            "arxiv_id": "1706.03762v7",
            "paper_version": "v7",
            "content_sha256": "a" * 64,
            "source_available": True,
        },
        "direction": "evidence board",
        "canvas_defaulted": True,
        "omitted_branding": ["logo", "qr"],
    }
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    archive = directory / "poster.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in source.iterdir():
            bundle.write(path, path.name)
    return archive


def test_artifact_display_block_keeps_bytes_out_of_projection():
    block = DISPLAY_BLOCKS_ADAPTER.validate_python(
        [
            {
                "kind": "artifact",
                "schema_version": 1,
                "scope": "owner",
                "artifact_id": str(uuid.uuid4()),
                "version_id": str(uuid.uuid4()),
                "identifier": "attention-poster",
                "version": 1,
                "artifact_kind": "posterly",
                "title": "Attention poster",
                "status": "ready",
                "preview_mime": "image/png",
                "source_language": "html",
                "gate_status": "passed",
                "total_bytes": 1234,
            }
        ]
    )[0]
    assert block.status == "ready"
    assert "html" not in block.model_dump(mode="json")


def test_public_block_rejects_private_ids():
    with pytest.raises(ValidationError):
        DISPLAY_BLOCKS_ADAPTER.validate_python(
            [
                {
                    "kind": "artifact",
                    "scope": "public",
                    "artifact_id": str(uuid.uuid4()),
                    "public_capability": str(uuid.uuid4()),
                    "identifier": "attention-poster",
                    "version": 1,
                    "title": "Attention poster",
                    "status": "ready",
                    "preview_mime": "image/png",
                    "gate_status": "passed",
                    "total_bytes": 1234,
                }
            ]
        )


def test_publish_read_and_idempotent_digest(db, settings, tmp_path):
    session_id, turn_id = _active_session(db)
    archive = _bundle(tmp_path / "bundle")
    service = ChatArtifactService(
        db,
        settings,
        LocalArtifactStorage(Path(settings.chat_artifact_local_dir)),
    )

    first = service.publish_zip(
        owner_id="owner-1",
        session_id=session_id,
        turn_id=turn_id,
        publication_id="publication-1",
        archive=archive,
        expected_paper=_paper_provenance(),
    )
    second = service.publish_zip(
        owner_id="owner-1",
        session_id=session_id,
        turn_id=turn_id,
        publication_id="publication-2",
        archive=archive,
        expected_paper=_paper_provenance(),
    )

    assert first.id == second.id
    assert first.version == 1
    assert first.state == "ready"
    assert first.byte_count > 0
    preview = service.read_version_file(
        "owner-1", first.artifact_id, first.id, first.preview_path, role="preview"
    )
    assert preview.data.startswith(b"\x89PNG\r\n\x1a\n")
    with pytest.raises(ArtifactError, match="not found"):
        service.get_version("another-owner", first.artifact_id, first.id)


def test_failed_gate_draft_has_no_pdf(db, settings, tmp_path):
    session_id, turn_id = _active_session(db)
    archive = _bundle(tmp_path / "draft", gate_status="failed")
    version = ChatArtifactService(db, settings).publish_zip(
        owner_id="owner-1",
        session_id=session_id,
        turn_id=turn_id,
        publication_id="publication-1",
        archive=archive,
        expected_paper=_paper_provenance(),
    )
    assert version.gate_status == "failed"
    assert version.manifest["downloads"] == []


def test_remote_subresource_is_rejected(db, settings, tmp_path):
    session_id, turn_id = _active_session(db)
    archive = _bundle(tmp_path / "remote", remote_image=True)
    with pytest.raises(ArtifactError, match="remote subresource"):
        ChatArtifactService(db, settings).publish_zip(
            owner_id="owner-1",
            session_id=session_id,
            turn_id=turn_id,
            publication_id="publication-1",
            archive=archive,
            expected_paper=_paper_provenance(),
        )


def test_publish_rejects_paper_provenance_drift(db, settings, tmp_path):
    session_id, turn_id = _active_session(db)
    archive = _bundle(tmp_path / "provenance")
    expected = _paper_provenance().model_copy(update={"content_sha256": "b" * 64})

    with pytest.raises(ArtifactError, match="prepared input"):
        ChatArtifactService(db, settings).publish_zip(
            owner_id="owner-1",
            session_id=session_id,
            turn_id=turn_id,
            publication_id="publication-1",
            archive=archive,
            expected_paper=expected,
        )


def test_share_materializes_an_independent_public_snapshot(db, settings, tmp_path):
    session_id, turn_id = _active_session(db)
    version = ChatArtifactService(db, settings).publish_zip(
        owner_id="owner-1",
        session_id=session_id,
        turn_id=turn_id,
        publication_id="publication-1",
        archive=_bundle(tmp_path / "shared"),
        expected_paper=_paper_provenance(),
    )
    db.add_all(
        [
            ChatMessageRecord(
                id=uuid.uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                sequence=1,
                role="user",
                content="Make a poster",
                status="complete",
            ),
            ChatMessageRecord(
                id=uuid.uuid4(),
                session_id=session_id,
                turn_id=turn_id,
                sequence=2,
                role="assistant",
                content="Poster ready",
                status="complete",
                display_blocks=[
                    {
                        "kind": "artifact",
                        "schema_version": 1,
                        "scope": "owner",
                        "artifact_id": str(version.artifact_id),
                        "version_id": str(version.id),
                        "identifier": "attention-poster",
                        "version": 1,
                        "artifact_kind": "posterly",
                        "title": "Attention Is All You Need",
                        "status": "ready",
                        "preview_mime": "image/png",
                        "source_language": "html",
                        "gate_status": "passed",
                        "total_bytes": version.byte_count,
                    }
                ],
            ),
        ]
    )
    session = db.get(ChatSession, session_id)
    session.active_turn_id = None
    db.flush()

    share = ChatShareService(db, settings).create_or_refresh(
        ChatOwner(hf_user_id="owner-1", hf_username="owner"), session_id
    )
    public_block = share.messages[1]["display_blocks"][0]
    assert public_block["scope"] == "public"
    assert "artifact_id" not in public_block
    assert "version_id" not in public_block
    snapshot = db.scalar(
        select(ChatSharedArtifact).where(ChatSharedArtifact.share_id == share.id)
    )
    assert snapshot.storage_key != version.storage_key
    file = ChatShareService(db, settings).read_public_artifact(
        str(share.id), str(snapshot.capability_id), role="preview"
    )
    assert file.media_type == "image/png"
    assert file.data.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "https://user:password@example.com",
        "https://localhost/path",
        "https://127.0.0.1/path",
        "https://10.0.0.2/path",
        "https://example.com/path#fragment",
        "https://example.com:8443/path",
    ],
)
def test_qr_destination_rejects_non_public_https(url):
    with pytest.raises(ValueError):
        normalize_public_https_url(url)


def test_qr_destination_normalizes_public_https():
    assert normalize_public_https_url(" HTTPS://Example.COM/paper?q=1 ") == (
        "https://example.com/paper?q=1"
    )
