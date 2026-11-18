from pathlib import Path

import pytest

from core.local_llm import LocalLlamaBackend


class FakeLlama:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {"choices": [{"message": {"content": "local response"}}]}


def test_local_backend_loads_once_and_forces_cpu(tmp_path: Path):
    model = tmp_path / "tiny.gguf"
    model.write_bytes(b"test-model")
    created = []

    def factory(**kwargs):
        instance = FakeLlama(**kwargs)
        created.append(instance)
        return instance

    backend = LocalLlamaBackend(
        model_path=str(model),
        llama_factory=factory,
        n_ctx=2048,
        n_threads=2,
        n_batch=128,
    )

    first = backend.complete([{"role": "user", "content": "hello"}], max_tokens=12)
    second = backend.complete([{"role": "user", "content": "again"}], max_tokens=12)

    assert first["choices"][0]["message"]["content"] == "local response"
    assert second == first
    assert len(created) == 1
    assert created[0].kwargs["n_gpu_layers"] == 0
    assert created[0].kwargs["n_ctx"] == 2048
    assert created[0].kwargs["n_threads"] == 2
    assert len(created[0].calls) == 2


def test_local_backend_rejects_missing_model(tmp_path: Path):
    backend = LocalLlamaBackend(model_path=str(tmp_path / "missing.gguf"), llama_factory=FakeLlama)

    with pytest.raises(FileNotFoundError, match="GGUF model"):
        backend.complete([{"role": "user", "content": "hello"}])
