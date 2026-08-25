from __future__ import annotations

import pytest

from scripts.deploy_latex_compiler_space import _assemble, _validate_space_id


def test_private_space_assembly_includes_the_shared_contract(tmp_path) -> None:
    _assemble(tmp_path)

    assert (tmp_path / "Dockerfile").is_file()
    assert (tmp_path / "latex_compiler_space" / "app.py").is_file()
    assert (tmp_path / "latex_compiler_contract" / "__init__.py").is_file()


@pytest.mark.parametrize(
    "space_id",
    [
        "namespace/compiler",
        "namespace/compiler-production",
        "namespace//compiler-staging",
    ],
)
def test_private_space_deploy_refuses_non_staging_ids(space_id: str) -> None:
    with pytest.raises(ValueError):
        _validate_space_id(space_id)
