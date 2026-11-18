from memory.database import Database


def test_database_uses_wal_and_initializes_required_tables(tmp_path):
    database = Database(str(tmp_path / "engine.db"))
    database.initialize()

    with database.connect() as connection:
        journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

    assert journal_mode == "wal"
    assert {"conversations", "user_facts", "semantic_cache_entries"} <= tables
