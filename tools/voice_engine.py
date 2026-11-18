from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class VoiceEngine:
    def __init__(self) -> None:
        self._whisper: WhisperModel | None = None
        self._load_lock = asyncio.Lock()

    def _load_whisper(self) -> WhisperModel:
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed")
        if self._whisper is None:
            self._whisper = WhisperModel(
                settings.whisper_model,
                device="cpu",
                compute_type="int8",
                cpu_threads=max(1, settings.whisper_cpu_threads),
            )
        return self._whisper

    def _transcribe_sync(self, audio_path: str, language: str | None) -> str:
        model = self._load_whisper()
        segments, _info = model.transcribe(audio_path, language=language, vad_filter=True, beam_size=1)
        return " ".join(segment.text.strip() for segment in segments).strip()

    async def transcribe(self, audio: bytes, filename: str = "audio.bin", language: str | None = None, timeout: float = 180.0) -> str:
        if not audio:
            raise ValueError("Audio data cannot be empty")
        suffix = Path(filename).suffix or ".bin"
        temporary = tempfile.NamedTemporaryFile(prefix="engine-audio-", suffix=suffix, delete=False)
        path = Path(temporary.name)
        try:
            temporary.write(audio)
            temporary.close()
            async with self._load_lock:
                return await asyncio.wait_for(asyncio.to_thread(self._transcribe_sync, str(path), language), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Speech transcription exceeded the configured timeout") from exc
        except Exception as exc:
            logger.exception("Speech transcription failed")
            raise RuntimeError(f"Speech transcription failed: {exc}") from exc
        finally:
            path.unlink(missing_ok=True)

    async def synthesize(self, text: str, timeout: float | None = None) -> bytes:
        text = text.strip()
        if not text:
            raise ValueError("Text cannot be empty")
        model_path = Path(settings.piper_model_path)
        if not model_path.is_file():
            raise FileNotFoundError(f"Piper voice model not found: {model_path}")
        output = tempfile.NamedTemporaryFile(prefix="engine-voice-", suffix=".wav", delete=False)
        output_path = Path(output.name)
        output.close()
        limit = timeout or settings.piper_timeout_seconds
        try:
            process = await asyncio.create_subprocess_exec(
                settings.piper_executable,
                "--model", str(model_path),
                "--output_file", str(output_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _stdout, stderr = await asyncio.wait_for(process.communicate(text.encode("utf-8")), timeout=limit)
            if process.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace")[-1000:]
                raise RuntimeError(f"Piper failed with exit status {process.returncode}: {detail}")
            return await asyncio.to_thread(output_path.read_bytes)
        except asyncio.TimeoutError as exc:
            raise TimeoutError("Piper synthesis exceeded the configured timeout") from exc
        except Exception as exc:
            logger.exception("Speech synthesis failed")
            if isinstance(exc, (FileNotFoundError, RuntimeError)):
                raise
            raise RuntimeError(f"Speech synthesis failed: {exc}") from exc
        finally:
            output_path.unlink(missing_ok=True)


voice_engine = VoiceEngine()
