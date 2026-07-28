from __future__ import annotations

import asyncio
import builtins

from backend.routers.papers import add_authors_to_paper
from backend.services.author_service import normalize_arxiv_author_name


class _EmptySession:
    def __init__(self) -> None:
        self.committed = False

    def commit(self) -> None:
        self.committed = True


def test_normalize_arxiv_author_name() -> None:
    assert normalize_arxiv_author_name("  Jane   Doe  ") == "Jane Doe"
    assert normalize_arxiv_author_name("(0000-0001) Jane Doe (MIT)") == "Jane Doe"
    assert normalize_arxiv_author_name("  ") == "Unknown Author"


def test_request_time_author_creation_does_not_import_maintenance_script(
    monkeypatch,
) -> None:
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == (
            "backend.database.authors_setup.populate_missing_authors_from_arxiv"
        ):
            raise AssertionError(
                "request path imported a file-logging maintenance script"
            )
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    session = _EmptySession()

    asyncio.run(add_authors_to_paper(session, object(), []))

    assert session.committed
