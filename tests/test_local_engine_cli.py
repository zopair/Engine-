import os
from dataclasses import replace
from pathlib import Path

from core.config import config
from core.local_engine import LocalEngine


def test_local_engine_executes_real_cli_boundary_without_numpy(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"small test fixture")
    executable = tmp_path / "llama-cli"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "assert '--no-display-prompt' in sys.argv\n"
        "assert '-m' in sys.argv and '-p' in sys.argv\n"
        "print('deterministic local model response')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("ENGINE_LLAMA_CLI_PATH", str(executable))
    settings = replace(config, model_path=str(model), max_memory_mb=4096)
    engine = LocalEngine(settings=settings)
    assert engine.is_ready()
    assert engine.runtime_installed()
    assert engine.complete("say hello") == "deterministic local model response"


def test_local_engine_rejects_missing_model_before_running_cli(tmp_path, monkeypatch):
    executable = tmp_path / "llama-cli"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    monkeypatch.setenv("ENGINE_LLAMA_CLI_PATH", str(executable))
    settings = replace(config, model_path=str(tmp_path / "missing.gguf"))
    engine = LocalEngine(settings=settings)
    try:
        engine.complete("hello")
    except Exception as exc:
        assert "GGUF model not found" in str(exc)
    else:
        raise AssertionError("missing model must fail closed")
