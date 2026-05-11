"""
Validate explicit method source paper links.

Run with:
uv run --env-file backend/keys.env python backend/database/methods_setup/check_method_source_links.py
"""

import re
import sys
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from backend.database.connection import db_manager
from backend.models.database import Method, Paper, PaperMethod


LOCAL_HOSTS = {
    "",
    "localhost",
    "127.0.0.1",
    "167.235.148.241",
    "paperswithcode.co",
    "www.paperswithcode.co",
}
LOCAL_PAPER_PATH_RE = re.compile(r"^/(?:paper|abs|pdf)/([^/?#]+?)(?:\.pdf)?/?$")
VERSION_RE = re.compile(r"v\d+$")


@dataclass(frozen=True)
class SourcePaperRef:
    arxiv_id: str
    version: Optional[str]


def parse_local_source_url(source_url: Optional[str]) -> Optional[SourcePaperRef]:
    if not source_url:
        return None

    parsed = urlparse(source_url)
    host = parsed.hostname or ""
    if parsed.scheme and host not in LOCAL_HOSTS:
        return None

    if parsed.scheme or parsed.netloc:
        path = parsed.path
    else:
        path = source_url.split("?", 1)[0].split("#", 1)[0]
    path = path.rstrip("/")
    match = LOCAL_PAPER_PATH_RE.match(path)
    if not match:
        return None

    source_ref = match.group(1)
    version_match = VERSION_RE.search(source_ref)
    version = version_match.group(0) if version_match else None
    arxiv_id = VERSION_RE.sub("", source_ref)
    return SourcePaperRef(arxiv_id=arxiv_id, version=version)


def validate_method_source_links(db: Session) -> list[str]:
    errors: list[str] = []

    methods = db.query(Method).all()
    paper_methods = {
        (paper_id, method_id)
        for paper_id, method_id in db.query(
            PaperMethod.paper_id,
            PaperMethod.method_id,
        ).all()
    }
    papers_by_id = {paper.id: paper for paper in db.query(Paper).all()}

    for method in methods:
        local_source_ref = parse_local_source_url(method.source_url)

        if method.source_paper_id is not None:
            if (method.source_paper_id, method.id) not in paper_methods:
                errors.append(
                    f"Method {method.id} ({method.name}) has source_paper_id={method.source_paper_id} "
                    "but no matching paper_methods row."
                )

            source_paper = papers_by_id.get(method.source_paper_id)
            if (
                local_source_ref
                and local_source_ref.version is None
                and source_paper
                and not source_paper.is_latest_version
            ):
                errors.append(
                    f"Method {method.id} ({method.name}) source_url omits a version but "
                    f"source_paper_id={method.source_paper_id} points to non-latest paper "
                    f"{source_paper.arxiv_id}{source_paper.version}."
                )

        if local_source_ref and method.source_paper_id is None:
            errors.append(
                f"Method {method.id} ({method.name}) has local source_url={method.source_url!r} "
                "but no source_paper_id."
            )

    return errors


def main() -> int:
    with db_manager.session_local() as db:
        errors = validate_method_source_links(db)

    if errors:
        print("Method source link integrity check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Method source link integrity check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
