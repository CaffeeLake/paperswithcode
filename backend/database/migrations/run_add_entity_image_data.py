"""
Run the add_entity_image_data migration and backfill image bytes.

Steps:
  1. Apply `add_entity_image_data.sql` (adds image_data / image_mime_type to
     tasks, methods, conferences).
  2. Read every seed image under
     `data/entity_image_seeds/<entity>/<slug>.<ext>` and store its bytes on the
     matching row (matched by slug), setting `image_mime_type` accordingly.
  3. Verify every seed image mapped to a populated row.

Idempotent: re-running re-reads the files and overwrites the same rows.

Usage:
  uv run --env-file backend/keys.env \
      python backend/database/migrations/run_add_entity_image_data.py
"""

import sys

from sqlalchemy import inspect, text

from backend.database.connection import db_manager
from backend.utils.entity_image_import import (
    ENTITY_MODELS,
    IMAGE_SEED_ROOT,
    mime_type_for_path,
    store_entity_image,
)

SQL_FILE = "backend/database/migrations/add_entity_image_data.sql"


def _schema_ready() -> bool:
    insp = inspect(db_manager.engine)
    for table in ENTITY_MODELS:
        cols = {c["name"] for c in insp.get_columns(table)}
        if "image_data" not in cols or "image_mime_type" not in cols:
            return False
    return True


def _apply_sql(session) -> None:
    if _schema_ready():
        print("Schema columns already present; skipping DDL.")
        return
    with open(SQL_FILE, "r") as f:
        session.execute(text(f.read()))
    session.commit()


def _backfill(session) -> tuple[int, list[str]]:
    """Backfill image bytes from seed files. Returns (count, unmatched)."""
    updated = 0
    unmatched: list[str] = []

    for dir_name, model in ENTITY_MODELS.items():
        directory = IMAGE_SEED_ROOT / dir_name
        if not directory.is_dir():
            print(f"  (skip) directory not found: {directory}")
            continue

        for image_path in sorted(directory.iterdir()):
            if not image_path.is_file():
                continue

            if mime_type_for_path(image_path) is None:
                print(f"  (skip) unsupported file type: {image_path}")
                continue

            slug = image_path.stem
            if store_entity_image(session, model, slug, image_path):
                updated += 1
                print(
                    f"  stored {dir_name}/{image_path.name} -> {model.__name__}({slug})"
                )
            else:
                unmatched.append(f"{dir_name}/{image_path.name}")

    session.commit()
    return updated, unmatched


def _verify(session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for dir_name, model in ENTITY_MODELS.items():
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

        print("Backfilling image bytes from seed files...")
        updated, unmatched = _backfill(session)
        print(f"Stored {updated} image(s) in the database.")

        if unmatched:
            print()
            print("ERROR: seed images without a matching DB row (by slug):")
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
