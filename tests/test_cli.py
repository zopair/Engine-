import json
from dataclasses import replace

import cli


class UnreadyEngine:
    def __init__(self):
        pass

    def is_ready(self):
        return False

    @staticmethod
    def runtime_installed():
        return False


class NoProviders:
    providers = []


def test_doctor_emits_machine_readable_report(capsys, monkeypatch):
    monkeypatch.setattr(cli, "LocalEngine", UnreadyEngine)
    monkeypatch.setattr(cli, "ProviderOrchestrator", NoProviders)
    monkeypatch.setattr(cli, "config", replace(cli.config, model_path=""))
    result = cli.main(["doctor"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["gpu_layers"] == 0
    assert payload["model_configured"] is False
    assert payload["status"] == "degraded"
