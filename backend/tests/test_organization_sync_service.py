"""Strict-allowlist and idempotency tests for daily HF organization links."""

from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from backend.models.database import Base, Organization, Paper, PaperOrganization
from backend.services.organization_sync_service import link_daily_paper_organizations


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_element, _compiler, **_kw):
    return "INTEGER"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Paper.__table__,
            Organization.__table__,
            PaperOrganization.__table__,
        ],
    )
    session = Session(engine)
    session.add(
        Paper(
            id=1,
            title="Paper",
            abstract="Abstract",
            arxiv_id="2501.00001",
            source="arxiv",
            version="v1",
            is_latest_version=True,
        )
    )
    session.commit()
    return session


def test_daily_payload_links_object_and_is_idempotent():
    session = _session()
    payload = {"name": "Qwen", "fullname": "Qwen", "avatar": "https://example"}
    first = link_daily_paper_organizations(session, 1, payload)
    second = link_daily_paper_organizations(session, 1, [payload])
    assert first["linked"] == 1
    assert second["already_linked"] == 1
    assert session.query(Organization).one().slug == "qwen"
    assert session.query(PaperOrganization).one().source == "hf_org_papers"


def test_unknown_payload_creates_no_rows_or_links():
    session = _session()
    result = link_daily_paper_organizations(
        session, 1, {"name": "not-in-the-launch-manifest"}
    )
    assert result["unknown_organizations_seen"] == 1
    assert session.query(Organization).count() == 0
    assert session.query(PaperOrganization).count() == 0


def test_hf_provenance_replaces_lower_confidence_existing_source():
    session = _session()
    organization = Organization(
        id=1,
        name="OpenAI",
        slug="openai",
        hf_slug="openai",
        is_featured=True,
        display_order=18,
    )
    session.add(organization)
    session.add(
        PaperOrganization(
            paper_id=1,
            organization_id=1,
            source="manual",
            added_by_hf_subject="hf-user-123",
            added_by_hf_username="curator",
        )
    )
    session.commit()
    link_daily_paper_organizations(session, 1, {"name": "openai"})
    link = session.query(PaperOrganization).one()
    assert link.source == "hf_org_papers"
    assert link.added_by_hf_subject is None
    assert link.added_by_hf_username is None
