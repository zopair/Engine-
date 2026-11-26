"""Create and restore SQLite snapshots for GitHub Actions artifact persistence."""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

# Direct script execution sets sys.path[0] to scripts/, not the repository root.
# Add the project root so sibling top-level packages (memory/) resolve in Actions.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from memory.database import Database

MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024


def create_snapshot(database_path: str, output_path: str) -> Path:
    source = Path(database_path)
    if not source.is_file():
        Database(str(source)).initialize()
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".engine-state-", suffix=".sqlite", dir=target.parent)
    os.close(fd)
    try:
        Database(str(source)).backup_to(temporary)
        size = Path(temporary).stat().st_size
        if size > MAX_SNAPSHOT_BYTES:
            raise ValueError(f"SQLite snapshot exceeds {MAX_SNAPSHOT_BYTES} bytes")
        with sqlite3.connect(temporary) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError("SQLite snapshot failed integrity_check")
        os.replace(temporary, target)
        return target
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore_snapshot(snapshot_path: str, database_path: str) -> bool:
    source, target = Path(snapshot_path), Path(database_path)
    if not source.is_file():
        return False
    if source.stat().st_size > MAX_SNAPSHOT_BYTES:
        raise ValueError("SQLite artifact exceeds the configured size limit")
    with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise ValueError("SQLite artifact failed integrity_check")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        required = {"conversations", "user_facts", "workflow_runs", "workflow_steps"}
        if not required.issubset(tables):
            raise ValueError("SQLite artifact is not an ENGINE database")
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".engine-restore-", suffix=".sqlite", dir=target.parent)
    os.close(fd)
    try:
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as src, sqlite3.connect(temporary) as dst:
            src.backup(dst)
        os.replace(temporary, target)
        return True
    finally:
        Path(temporary).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("create")
    create.add_argument("--database", default=os.getenv("ENGINE_DATABASE_PATH", "./data/engine.db"))
    create.add_argument("--output", default="./artifacts/engine-state.sqlite")
    restore = sub.add_parser("restore")
    restore.add_argument("--snapshot", default="./artifacts/engine-state.sqlite")
    restore.add_argument("--database", default=os.getenv("ENGINE_DATABASE_PATH", "./data/engine.db"))
    args = parser.parse_args()
    if args.action == "create":
        print(f"Created validated SQLite snapshot: {create_snapshot(args.database, args.output)}")
    else:
        restored = restore_snapshot(args.snapshot, args.database)
        print("Previous artifact state restored." if restored else "No previous artifact snapshot found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
