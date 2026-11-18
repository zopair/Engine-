import sqlite3

import pytest

from memory.database import Database
from scripts.artifact_state import create_snapshot, restore_snapshot


def test_artifact_snapshot_round_trip_restores_engine_rows(tmp_path):
    original = tmp_path / "original.db"
    database = Database(str(original))
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            "INSERT INTO user_facts(user_id, fact, source) VALUES (?, ?, ?)",
            ("engine", "artifact persistence", "test"),
        )

    artifact = tmp_path / "artifact.sqlite"
    assert create_snapshot(str(original), str(artifact)) == artifact
    restored = tmp_path / "restored.db"
    assert restore_snapshot(str(artifact), str(restored)) is True
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT fact FROM user_facts").fetchone() == ("artifact persistence",)


def test_artifact_restore_rejects_non_engine_sqlite(tmp_path):
    invalid = tmp_path / "invalid.sqlite"
    with sqlite3.connect(invalid) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")
    with pytest.raises(ValueError, match="not an ENGINE database"):
        restore_snapshot(str(invalid), str(tmp_path / "target.db"))


def test_artifact_restore_missing_file_is_noop(tmp_path):
    assert restore_snapshot(str(tmp_path / "missing.sqlite"), str(tmp_path / "target.db")) is False
