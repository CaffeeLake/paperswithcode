"""Tests for the Methods API endpoints.

Focused regression coverage for `/api/v1/methods/?q=...` search ranking so
that paper edit pickers surface methods whose name/full_name matches the
query before methods that only mention the term in their description.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.main import create_app
from backend.models.database import (
    Base,
    Method as DBMethod,
)
from backend.database.connection import get_database_session


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_element, _compiler, **_kw):
    return "TEXT"


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_element, _compiler, **_kw):
    return "TEXT"


SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_database_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client():
    Base.metadata.create_all(bind=engine)

    app = create_app()
    app.dependency_overrides[get_database_session] = override_get_database_session

    with TestClient(app) as test_client:
        yield test_client

    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def methods_with_image_keyword():
    """Methods where 'image' appears in different fields.

    Layout:
      - Image GPT: name prefix match
      - Image Transformer: name prefix match
      - DALL-E: full_name contains "image" ("Discrete VAE for image generation")
      - Convolutional Network: description-only match ("operates on images")
      - Transformer: no match at all
    """
    db = TestingSessionLocal()

    methods = [
        DBMethod(
            id=1,
            name="Image GPT",
            slug="image-gpt",
            full_name="Image Generative Pretraining",
            description="Autoregressive pixel modeling.",
        ),
        DBMethod(
            id=2,
            name="Image Transformer",
            slug="image-transformer",
            full_name=None,
            description="Self-attention over pixel grids.",
        ),
        DBMethod(
            id=3,
            name="DALL-E",
            slug="dall-e",
            full_name="Discrete VAE for image generation",
            description="Text-to-art generative model.",
        ),
        DBMethod(
            id=4,
            name="Convolutional Network",
            slug="convolutional-network",
            full_name=None,
            description="Operates on images using shared filters.",
        ),
        DBMethod(
            id=5,
            name="Transformer",
            slug="transformer",
            full_name="Self-Attention Transformer",
            description="Sequence-to-sequence with self-attention.",
        ),
    ]
    db.add_all(methods)
    db.commit()
    db.close()


def test_methods_search_ranks_name_matches_first(client, methods_with_image_keyword):
    """`q=image` returns name matches, then full_name matches, then description."""
    response = client.get("/api/v1/methods/?q=image&page_size=20")

    assert response.status_code == 200
    data = response.json()

    names = [m["name"] for m in data["results"]]

    assert names[:2] == ["Image GPT", "Image Transformer"]

    assert "DALL-E" in names
    assert "Convolutional Network" in names
    assert names.index("DALL-E") < names.index("Convolutional Network")
    assert names.index("Image Transformer") < names.index("DALL-E")

    assert "Transformer" not in names


if __name__ == "__main__":
    pytest.main([__file__])
