"""Unified command-line entry point for GitHub Actions and local diagnostics."""

from __future__ import annotations

import argparse
import json
import sys

from core.config import config
from core.local_engine import LocalEngine, LocalEngineError
from core.resource_optimizer import apply_thread_limits, as_dict


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engine", description="GitHub-native autonomous engine")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check runner limits and local inference readiness")
    run = commands.add_parser("run", help="run one prompt using a cached local GGUF model")
    run.add_argument("prompt", help="prompt text")
    run.add_argument("--max-tokens", type=int, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    apply_thread_limits()
    if args.command == "doctor":
        engine = LocalEngine()
        report = {
            "status": "ready" if engine.is_ready() and engine.runtime_installed() else "degraded",
            "model_configured": bool(config.model_path),
            "model_file_exists": engine.is_ready(),
            "llama_cpp_installed": engine.runtime_installed(),
            "gpu_layers": 0,
            "resources": as_dict(),
        }
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "ready" else 2

    try:
        answer = LocalEngine().complete(args.prompt, max_tokens=args.max_tokens)
    except (LocalEngineError, ValueError) as exc:
        print(f"engine: {exc}", file=sys.stderr)
        return 2
    print(answer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
