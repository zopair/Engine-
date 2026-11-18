import pytest

from core.inference import InferenceEngine


class UnavailableLocal:
    def is_available(self):
        return False


class UnavailableRemote:
    def is_available(self):
        return False


@pytest.mark.asyncio
async def test_engine_starts_without_provider_keys_and_reports_no_backend():
    engine = InferenceEngine(
        local_backend=UnavailableLocal(),
        remote_backend=UnavailableRemote(),
    )

    with pytest.raises(RuntimeError, match="No inference backend"):
        await engine.acompletion([{"role": "user", "content": "hello"}])


class AvailableLocal:
    def is_available(self):
        return True

    async def acompletion(self, messages, **kwargs):
        return {"backend": "local", "messages": messages}


class ForbiddenRemote:
    def is_available(self):
        return True

    async def acompletion(self, *args, **kwargs):
        raise AssertionError("remote backend must not be called when local GGUF exists")


@pytest.mark.asyncio
async def test_engine_prefers_available_local_backend():
    engine = InferenceEngine(
        local_backend=AvailableLocal(),
        remote_backend=ForbiddenRemote(),
    )

    result = await engine.acompletion([{"role": "user", "content": "hello"}])

    assert result["backend"] == "local"
