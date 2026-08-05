"""Apply and verify paper-organization manual attribution columns.

Usage:
  uv run --env-file backend/keys.env \
      python backend/database/migrations/run_add_paper_organization_provenance.py
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager


SQL_FILE = Path(__file__).with_name("add_paper_organization_provenance.sql")


def main() -> None:
    with db_manager.session_local() as session:
        session.execute(text(SQL_FILE.read_text()))
        session.commit()
        count = session.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND table_name = 'paper_organizations' "
                "AND column_name IN "
                "('added_by_hf_subject', 'added_by_hf_username')"
            )
        ).scalar_one()
        if count != 2:
            raise RuntimeError(
                f"paper organization provenance migration found {count}/2 columns"
            )
        print("Paper organization provenance migration applied and verified.")


if __name__ == "__main__":
    main()
