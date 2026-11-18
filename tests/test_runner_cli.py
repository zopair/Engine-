import json
from pathlib import Path

from cli import main


def test_cli_run_uses_default_orchestrator(monkeypatch, capsys, tmp_path):
    from core.provider_orchestrator import ProviderOrchestrator
    class FakeProvider:
        name = "test"
        def health_check(self): return {"healthy": True, "latency_ms": 0.1}
        def complete(self, prompt, max_tokens=None): return "real routed result"
    monkeypatch.setattr(
        "core.provider_orchestrator.ProviderOrchestrator",
        lambda: ProviderOrchestrator(providers=[FakeProvider()]),
    )
    assert main(["run", "execute task"]) == 0
    assert capsys.readouterr().out.strip() == "real routed result"


def test_cli_maintenance_initializes_database(monkeypatch, tmp_path):
    monkeypatch.setenv("ENGINE_DATABASE_PATH", str(tmp_path / "engine.db"))
    assert main(["maintenance"]) == 0
    assert (tmp_path / "engine.db").exists()
