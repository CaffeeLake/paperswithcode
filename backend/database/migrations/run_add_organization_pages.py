"""Apply the organization-pages schema migration.

Usage:
  uv run --env-file backend/keys.env \
      python backend/database/migrations/run_add_organization_pages.py
"""

from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = Path("backend/database/migrations/add_organization_pages.sql")


def main() -> None:
    session = db_manager.session_local()
    try:
        session.execute(text(SQL_FILE.read_text()))
        session.commit()
        count = session.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_name = 'organizations' "
                "AND column_name IN "
                "('hf_slug', 'is_featured', 'display_order', 'last_hf_synced_at', "
                "'logo_data', 'logo_mime_type', 'hf_paper_count', "
                "'trending_score', 'trending_score_updated_at')"
            )
        ).scalar_one()
        if count != 9:
            raise RuntimeError(
                f"organization migration verification found {count}/9 columns"
            )
        print("Organization pages migration applied and verified.")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
