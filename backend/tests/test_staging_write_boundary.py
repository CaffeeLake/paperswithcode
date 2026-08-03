import pytest

from backend.main import _is_staging_catalog_mutation_path


def test_bucket_copy_is_not_a_catalog_mutation() -> None:
    assert not _is_staging_catalog_mutation_path("/api/v1/papers/98695/copy-to-bucket")


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/papers/98695",
        "/api/v1/papers/98695/copy-to-bucket/extra",
        "/api/v1/papers/copy-to-bucket",
        "/api/v1/tasks/42",
        "/api/v1/evaluations/42",
    ],
)
def test_catalog_mutations_remain_blocked(path: str) -> None:
    assert _is_staging_catalog_mutation_path(path)
