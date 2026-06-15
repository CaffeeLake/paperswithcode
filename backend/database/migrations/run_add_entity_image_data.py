"""
Run the add_entity_image_data migration and backfill image bytes.

Steps:
  1. Apply `add_entity_image_data.sql` (adds image_data / image_mime_type to
     tasks, methods, conferences).
  2. Read every curated static image under
     `frontend/public/images/<entity>/<slug>.<ext>` and store its bytes on the
     matching row (matched by slug), setting `image_mime_type` accordingly.
  3. Verify every static image mapped to a populated row.

Idempotent: re-running re-reads the files and overwrites the same rows.

Usage:
  uv run --env-file backend/keys.env \
      python backend/database/migrations/run_add_entity_image_data.py
"""

import sys
from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager
from backend.models.database import Conference as DBConference
from backend.models.database import Method as DBMethod
from backend.models.database import Task as DBTask

SQL_FILE = "backend/database/migrations/add_entity_image_data.sql"

# Repo-root-relative static image directories, mapped to their owning model.
IMAGE_ROOT = Path("frontend/public/images")
ENTITY_DIRS = {
    "tasks": DBTask,
    "methods": DBMethod,
    "conferences": DBConference,
}

MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
}


def _apply_sql(session) -> None:
    with open(SQL_FILE, "r") as f:
        session.execute(text(f.read()))
    session.commit()


def _backfill(session) -> tuple[int, list[str]]:
    """Backfill image bytes from static files. Returns (count, unmatched)."""
    updated = 0
    unmatched: list[str] = []

    for dir_name, model in ENTITY_DIRS.items():
        directory = IMAGE_ROOT / dir_name
        if not directory.is_dir():
            print(f"  (skip) directory not found: {directory}")
            continue

        for image_path in sorted(directory.iterdir()):
            if not image_path.is_file():
                continue

            mime = MIME_BY_SUFFIX.get(image_path.suffix.lower())
            if mime is None:
                print(f"  (skip) unsupported file type: {image_path}")
                continue

            slug = image_path.stem
            row = session.query(model).filter(model.slug == slug).first()
            if row is None:
                unmatched.append(f"{dir_name}/{image_path.name}")
                continue

            row.image_data = image_path.read_bytes()
            row.image_mime_type = mime
            updated += 1
            print(f"  stored {dir_name}/{image_path.name} -> {model.__name__}({slug})")

    session.commit()
    return updated, unmatched


def _verify(session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dir_name, model in ENTITY_DIRS.items():
        counts[dir_name] = (
            session.query(model).filter(model.image_mime_type.isnot(None)).count()
        )
    return counts


def main() -> None:
    print("=" * 80)
    print("Running migration: add_entity_image_data")
    print("=" * 80)

    session = db_manager.session_local()
    try:
        print("Applying schema changes...")
        _apply_sql(session)

        print("Backfilling image bytes from static files...")
        updated, unmatched = _backfill(session)
        print(f"Stored {updated} image(s) in the database.")

        if unmatched:
            print()
            print("ERROR: static images without a matching DB row (by slug):")
            for name in unmatched:
                print(f"   - {name}")
            sys.exit(1)

        print()
        print("Verifying populated rows per entity:")
        for entity, count in _verify(session).items():
            print(f"   - {entity}: {count} row(s) with a DB image")

        print()
        print("=" * 80)
        print("Migration completed successfully")

    except Exception as exc:
        print(f"Migration failed: {exc}")
        session.rollback()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
