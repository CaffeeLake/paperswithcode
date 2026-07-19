import pytest
from fastapi import HTTPException

from backend.routers.thumbnails import serve_custom_thumbnail, serve_thumbnail


class MissingThumbnailService:
    def get_existing_custom_thumbnail_path(self, _filename):
        return None

    def get_local_thumbnail_path(self, _filename):
        return None


@pytest.mark.parametrize(
    "endpoint",
    [serve_thumbnail, serve_custom_thumbnail],
)
def test_missing_thumbnail_is_not_browser_cached(endpoint):
    with pytest.raises(HTTPException) as exc_info:
        endpoint("missing.jpg", MissingThumbnailService())

    assert exc_info.value.status_code == 404
    assert exc_info.value.headers == {"Cache-Control": "no-store"}
