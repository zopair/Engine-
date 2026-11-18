from core.config import EngineConfig
from scripts.provision_model import DEFAULT_MODEL_URL, parse_checksum_sidecar, ModelProvisionError
import pytest


def test_default_model_release_is_internal_and_checksum_is_discovered_from_release():
    settings = EngineConfig.from_env()
    assert settings.model_release_url == DEFAULT_MODEL_URL
    assert settings.model_release_url.endswith("/models-v1/qwen2.5-0.5b-instruct-q4_k_m.gguf")
    assert settings.model_path.endswith("qwen2.5-0.5b-instruct-q4_k_m.gguf")
    assert settings.model_sha256 == ""


def test_checksum_sidecar_accepts_sha256sum_format():
    digest = "a" * 64
    assert parse_checksum_sidecar(f"{digest}  qwen.gguf\n", "qwen.gguf") == digest


def test_checksum_sidecar_rejects_wrong_filename():
    with pytest.raises(ModelProvisionError):
        parse_checksum_sidecar(f"{'a' * 64}  other.gguf", "qwen.gguf")
