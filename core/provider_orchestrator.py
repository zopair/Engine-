"""Provider discovery, health-aware routing, fallback and SQLite performance history."""
from __future__ import annotations

import json
import os
import time
import ipaddress
import socket
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.config import config
from core.local_engine import LocalEngine, LocalEngineError
from memory.database import Database


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderHealth:
    healthy: bool
    latency_ms: float


class LocalGGUFProvider:
    name = "local-gguf"

    def __init__(self, engine: LocalEngine | None = None):
        self.engine = engine or LocalEngine()

    def health_check(self) -> dict[str, Any]:
        ready = self.engine.is_ready() and self.engine.runtime_installed()
        return {"healthy": ready, "latency_ms": 0.0}

    def complete(self, prompt: str, max_tokens: int | None = None) -> str:
        return self.engine.complete(prompt, max_tokens=max_tokens)


class OpenAICompatibleProvider:
    """Opt-in HTTPS OpenAI-compatible endpoint; no provider is trusted by discovery alone."""

    def __init__(self, name: str, base_url: str, model: str, token: str = "", timeout: float = 12.0):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("public provider endpoints must be credential-free HTTPS URLs")
        host = parsed.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local")):
            raise ValueError("public provider endpoint cannot target a local host")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("public provider endpoint cannot target a non-public IP")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.token = token
        self.timeout = max(2.0, min(float(timeout), 30.0))

    def _request(self, path: str, payload: dict | None = None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Accept": "application/json", "User-Agent": "ENGINE-provider/1.0"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers)
        try:
            host = urllib.parse.urlsplit(self.base_url).hostname
            addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
                raise ProviderError(f"{self.name}: endpoint resolves to a non-public address")
            class _NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(_NoRedirect())
            with opener.open(request, timeout=self.timeout) as response:
                return json.loads(response.read(2_000_001).decode("utf-8"))
        except (OSError, ValueError, urllib.error.URLError) as exc:
            raise ProviderError(f"{self.name}: provider request failed") from exc

    def health_check(self) -> dict[str, Any]:
        started = time.monotonic()
        try:
            self._request("/models")
            return {"healthy": True, "latency_ms": (time.monotonic() - started) * 1000}
        except ProviderError:
            return {"healthy": False, "latency_ms": (time.monotonic() - started) * 1000}

    def complete(self, prompt: str, max_tokens: int | None = None) -> str:
        result = self._request("/chat/completions", {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens or config.max_tokens,
        })
        try:
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: invalid completion response") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError(f"{self.name}: empty completion response")
        return content.strip()


class ProviderOrchestrator:
    """Discovers configured providers, probes health, routes once per provider and deduplicates."""

    def __init__(
        self,
        database: Database | None = None,
        providers: Iterable[Any] | None = None,
        health_ttl_seconds: float = 30.0,
    ):
        self.database = database or Database()
        self.database.initialize()
        self.health_ttl_seconds = max(0.0, health_ttl_seconds)
        self.providers = list(providers) if providers is not None else self.discover_providers()
        self._health: dict[str, tuple[float, ProviderHealth]] = {}
        with self.database.connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS provider_metrics (
                    provider TEXT PRIMARY KEY,
                    successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    total_latency_ms REAL NOT NULL DEFAULT 0,
                    last_latency_ms REAL,
                    last_error TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS provider_requests (
                    request_id TEXT PRIMARY KEY,
                    prompt_hash TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
            """)

    @staticmethod
    def discover_providers() -> list[Any]:
        providers: list[Any] = []
        local = LocalGGUFProvider()
        if local.health_check()["healthy"]:
            providers.append(local)
        raw = os.getenv("ENGINE_PUBLIC_PROVIDERS", "").strip()
        if raw:
            try:
                entries = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProviderError("ENGINE_PUBLIC_PROVIDERS must be valid JSON") from exc
            if not isinstance(entries, list) or len(entries) > 8:
                raise ProviderError("ENGINE_PUBLIC_PROVIDERS must be a list of at most 8 endpoints")
            for index, item in enumerate(entries):
                if not isinstance(item, dict):
                    raise ProviderError("provider entries must be objects")
                name = str(item.get("name") or f"public-{index + 1}")[:64]
                model = str(item.get("model") or "").strip()
                base_url = str(item.get("base_url") or "").strip()
                token_env = str(item.get("token_env") or "").strip()
                if not model or not base_url:
                    continue
                providers.append(OpenAICompatibleProvider(
                    name, base_url, model, os.getenv(token_env, "") if token_env else ""
                ))
        return providers

    def _health_for(self, provider: Any) -> ProviderHealth:
        now = time.monotonic()
        cached = self._health.get(provider.name)
        if cached and now - cached[0] < self.health_ttl_seconds:
            return cached[1]
        started = time.monotonic()
        try:
            report = provider.health_check()
            health = ProviderHealth(bool(report.get("healthy")), float(report.get("latency_ms", (time.monotonic() - started) * 1000)))
        except Exception:
            health = ProviderHealth(False, (time.monotonic() - started) * 1000)
        self._health[provider.name] = (now, health)
        return health

    def _ranked(self) -> list[Any]:
        candidates = []
        for provider in self.providers:
            health = self._health_for(provider)
            if not health.healthy:
                continue
            with self.database.connect() as connection:
                row = connection.execute(
                    "SELECT successes, failures, total_latency_ms FROM provider_metrics WHERE provider=?",
                    (provider.name,),
                ).fetchone()
            success = row["successes"] if row else 0
            failure = row["failures"] if row else 0
            average = row["total_latency_ms"] / success if success else health.latency_ms
            reliability = (success + 1) / (success + failure + 2)
            candidates.append((-(reliability / max(average, 1.0)), health.latency_ms, provider))
        return [item[2] for item in sorted(candidates, key=lambda item: (item[0], item[1]))]

    def _record(self, provider: str, latency_ms: float, error: str | None):
        with self.database.connect() as connection:
            connection.execute("""
                INSERT INTO provider_metrics(provider, successes, failures, total_latency_ms,
                    last_latency_ms, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    successes=successes+excluded.successes,
                    failures=failures+excluded.failures,
                    total_latency_ms=total_latency_ms+excluded.total_latency_ms,
                    last_latency_ms=excluded.last_latency_ms,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
            """, (provider, 0 if error else 1, 1 if error else 0,
                  0.0 if error else latency_ms, latency_ms, error, time.time()))

    def complete(self, prompt: str, max_tokens: int | None = None, request_id: str | None = None) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must not be empty")
        import hashlib
        prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        if request_id:
            with self.database.connect() as connection:
                cached = connection.execute(
                    "SELECT prompt_hash, answer FROM provider_requests WHERE request_id=?",
                    (request_id,),
                ).fetchone()
            if cached:
                if cached["prompt_hash"] != prompt_hash:
                    raise ProviderError("request_id was already used for a different prompt")
                return cached["answer"]
        errors = []
        for provider in self._ranked():
            started = time.monotonic()
            try:
                answer = provider.complete(prompt, max_tokens=max_tokens)
                if not isinstance(answer, str) or not answer.strip():
                    raise ProviderError("provider returned an empty response")
                latency = (time.monotonic() - started) * 1000
                self._record(provider.name, latency, None)
                if request_id:
                    with self.database.connect() as connection:
                        connection.execute(
                            "INSERT OR IGNORE INTO provider_requests(request_id,prompt_hash,answer,provider,created_at) VALUES (?,?,?,?,?)",
                            (request_id, prompt_hash, answer, provider.name, time.time()),
                        )
                return answer.strip()
            except Exception as exc:
                latency = (time.monotonic() - started) * 1000
                message = f"{type(exc).__name__}: {str(exc)[:240]}"
                self._record(provider.name, latency, message)
                errors.append(f"{provider.name}: {message}")
                self._health.pop(provider.name, None)
        detail = "; ".join(errors) if errors else "no healthy providers are configured"
        raise ProviderError("all inference providers failed: " + detail)
