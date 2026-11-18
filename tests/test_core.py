from pathlib import Path

import pytest

from core.config import EngineConfig
from core.local_engine import LocalEngine, LocalEngineError
from core.resource_optimizer import snapshot


class FakeLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "engine response"}}]}


def make_config(model_path: Path) -> EngineConfig:
    return EngineConfig(
        model_path=str(model_path),
        model_context=1024,
        model_threads=2,
        model_batch=64,
        max_tokens=64,
        temperature=0.1,
        max_memory_mb=12288,
        max_cpu_threads=2,
    )


def test_local_engine_lazy_loads_once_and_forces_cpu(tmp_path):
    model = tmp_path / "small.gguf"
    model.write_bytes(b"mock gguf")
    instances = []

    def factory(**kwargs):
        instance = FakeLlama(**kwargs)
        instances.append(instance)
        return instance

    engine = LocalEngine(make_config(model), llama_factory=factory)
    assert engine.is_ready()
    assert engine.complete("first") == "engine response"
    assert engine.complete("second") == "engine response"
    assert len(instances) == 1
    assert instances[0].kwargs["n_gpu_layers"] == 0
    assert instances[0].kwargs["n_threads"] == 2
    assert len(instances[0].calls) == 2


def test_local_engine_fails_closed_without_model(tmp_path):
    engine = LocalEngine(make_config(tmp_path / "missing.gguf"), llama_factory=FakeLlama)
    with pytest.raises(LocalEngineError, match="GGUF model not found"):
        engine.complete("hello")


def test_local_engine_rejects_empty_prompt(tmp_path):
    model = tmp_path / "small.gguf"
    model.write_bytes(b"mock")
    engine = LocalEngine(make_config(model), llama_factory=FakeLlama)
    with pytest.raises(ValueError, match="prompt must not be empty"):
        engine.complete("  ")


def test_resource_snapshot_obeys_cpu_budget():
    settings = make_config(Path("unused.gguf"))
    report = snapshot(settings)
    assert report.cpu_count >= 1
    assert 1 <= report.cpu_threads <= report.cpu_count
    assert report.process_peak_rss_mb >= 0
