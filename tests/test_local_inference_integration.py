"""Opt-in real-model integration test; set both paths to run actual inference."""
import os
from dataclasses import replace
from pathlib import Path
import pytest
from core.config import config
from core.local_engine import LocalEngine

@pytest.mark.skipif(
    not os.getenv("ENGINE_INTEGRATION_MODEL_PATH") or not os.getenv("ENGINE_LLAMA_CLI_PATH"),
    reason="real GGUF model and llama.cpp CLI are provisioned only in the explicit integration workflow",
)
def test_real_gguf_model_returns_a_text_completion():
    model=Path(os.environ["ENGINE_INTEGRATION_MODEL_PATH"]).expanduser()
    assert model.is_file() and model.stat().st_size > 10_000_000
    settings=replace(config,model_path=str(model),max_tokens=48,model_context=1024)
    answer=LocalEngine(settings=settings).complete("Reply with exactly the word READY.")
    assert answer.strip()
    assert "READY" in answer.upper()
