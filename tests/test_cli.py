import json

from cli import main


def test_doctor_emits_machine_readable_report(capsys, monkeypatch):
    monkeypatch.setenv("ENGINE_MODEL_PATH", "")
    result = main(["doctor"])
    payload = json.loads(capsys.readouterr().out)
    assert result == 2
    assert payload["gpu_layers"] == 0
    assert payload["model_configured"] is False
    assert payload["status"] == "degraded"
