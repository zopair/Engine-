from __future__ import annotations

import argparse
import os

from memory.state_store import GitHubBranchStateStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Restore or persist encrypted ENGINE SQLite state.")
    parser.add_argument("action", choices=("restore", "save"))
    parser.add_argument("--database", default=os.getenv("ENGINE_DATABASE_PATH", "./data/engine.db"))
    args = parser.parse_args()
    store = GitHubBranchStateStore()
    if args.action == "restore":
        restored = store.load_into(args.database)
        print("Encrypted state restored." if restored else "No previous state snapshot found.")
    else:
        commit = store.save_from(args.database)
        print(f"Encrypted state saved in GitHub data branch ({commit[:12]}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
