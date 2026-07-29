"""Apply the additive catalog mutation audit migration."""

from pathlib import Path

from sqlalchemy import text

from backend.database.connection import db_manager


def main() -> None:
    sql = Path(__file__).with_name("add_catalog_mutation_audit.sql").read_text()
    with db_manager.session_local() as session:
        session.execute(text(sql))
        session.commit()


if __name__ == "__main__":
    main()
