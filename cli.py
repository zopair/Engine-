"""Unified CLI for provider-routed inference and scheduled maintenance."""
from __future__ import annotations

import argparse
import json
import sys
import time

from core.config import config
from core.provider_orchestrator import ProviderOrchestrator, ProviderError
from core.resource_optimizer import apply_thread_limits, as_dict
from memory.database import Database


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description="GitHub-native autonomous engine")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check runner limits and inference provider readiness")
    run = commands.add_parser("run", help="run a task through the provider orchestrator")
    run.add_argument("prompt", help="prompt text")
    run.add_argument("--max-tokens", type=int, default=None)
    run.add_argument("--request-id", default=None)
    commands.add_parser("maintenance", help="initialize and compact persistent engine state")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    apply_thread_limits()
    if args.command == "maintenance":
        database = Database(config.database_path)
        database.initialize()
        with database.connect() as connection:
            connection.execute("DELETE FROM provider_requests WHERE created_at < ?", (time.time() - 30 * 86400,))
            connection.execute("PRAGMA optimize")
        print(json.dumps({"status": "maintenance_complete", "database": config.database_path}))
        return 0
    if args.command == "doctor":
        orchestrator = ProviderOrchestrator()
        providers = [{"name": provider.name, **orchestrator._health_for(provider).__dict__}
                     for provider in orchestrator.providers]
        report = {"status": "ready" if any(item["healthy"] for item in providers) else "degraded",
                  "providers": providers, "gpu_layers": 0, "resources": as_dict()}
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "ready" else 2
    try:
        answer = ProviderOrchestrator().complete(
            args.prompt, max_tokens=args.max_tokens, request_id=args.request_id
        )
    except (ProviderError, ValueError) as exc:
        print(f"engine: {exc}", file=sys.stderr)
        return 2
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
