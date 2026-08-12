from pathlib import Path


MIGRATION = (
    Path(__file__).parents[1]
    / "database"
    / "migrations"
    / "add_chat_reasoning_effort_production.sql"
)


def test_production_reasoning_effort_migration_is_hf_only_and_isolated():
    sql = MIGRATION.read_text()

    assert "SET LOCAL search_path = public" in sql
    assert "chat_sessions" in sql
    assert "chat_messages" in sql
    assert "chat_turn_capabilities" in sql
    assert "chat_openrouter" not in sql
    assert "OWNER TO paperswithcode_user" in sql
    assert "FROM pwc_staging" in sql
