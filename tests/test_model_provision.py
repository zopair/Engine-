import hashlib
import io

import pytest

from scripts.provision_model import ModelProvisionError, download_model


class FakeResponse:
    def __init__(self, data, final_url):
        self.stream = io.BytesIO(data)
        self.final_url = final_url
    def __enter__(self): return self
    def __exit__(self, *args): self.stream.close()
    def read(self, size=-1): return self.stream.read(size)
    def geturl(self): return self.final_url


def test_model_download_requires_pinned_sha_and_github_release(tmp_path):
    payload = b"fake-gguf"
    digest = hashlib.sha256(payload).hexdigest()
    url = "https://github.com/owner/repo/releases/download/v1/model.gguf"
    destination = tmp_path / "model.gguf"
    result = download_model(url, digest, destination,
        opener=lambda request, timeout: FakeResponse(payload, url))
    assert result == destination
    assert destination.read_bytes() == payload


def test_model_download_rejects_non_github_sources(tmp_path):
    with pytest.raises(ModelProvisionError, match="GitHub Releases"):
        download_model("https://huggingface.co/model.gguf", "a" * 64, tmp_path / "m.gguf")


def test_model_download_rejects_checksum_mismatch(tmp_path):
    url = "https://github.com/owner/repo/releases/download/v1/model.gguf"
    with pytest.raises(ModelProvisionError, match="SHA-256"):
        download_model(url, "0" * 64, tmp_path / "m.gguf",
            opener=lambda request, timeout: FakeResponse(b"bad", url))
