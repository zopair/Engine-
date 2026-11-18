from pathlib import Path

from core.provider_orchestrator import ProviderOrchestrator
from memory.database import Database


class Provider:
    def __init__(self, name, response=None, error=None, healthy=True):
        self.name = name
        self.response = response
        self.error = error
        self.healthy = healthy
        self.calls = 0

    def health_check(self):
        return {"healthy": self.healthy, "latency_ms": 1.0}

    def complete(self, prompt, max_tokens=None):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


def test_orchestrator_falls_back_and_records_provider_metrics(tmp_path: Path):
    database = Database(str(tmp_path / "metrics.db"))
    first = Provider("primary", error=RuntimeError("offline"))
    second = Provider("fallback", response="answer")
    orchestrator = ProviderOrchestrator(database=database, providers=[first, second])

    assert orchestrator.complete("question", request_id="request-1") == "answer"
    assert first.calls == 1
    assert second.calls == 1
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT provider, successes, failures FROM provider_metrics ORDER BY provider"
        ).fetchall()
    assert [(row["provider"], row["successes"], row["failures"]) for row in rows] == [
        ("fallback", 1, 0), ("primary", 0, 1)
    ]


def test_orchestrator_idempotency_key_prevents_duplicate_provider_calls(tmp_path: Path):
    provider = Provider("local", response="once")
    orchestrator = ProviderOrchestrator(
        database=Database(str(tmp_path / "idempotency.db")), providers=[provider]
    )
    assert orchestrator.complete("task", request_id="stable-id") == "once"
    assert orchestrator.complete("task", request_id="stable-id") == "once"
    assert provider.calls == 1


def test_orchestrator_skips_unhealthy_provider(tmp_path: Path):
    unhealthy = Provider("unhealthy", response="bad", healthy=False)
    healthy = Provider("healthy", response="good")
    orchestrator = ProviderOrchestrator(
        database=Database(str(tmp_path / "health.db")), providers=[unhealthy, healthy]
    )
    assert orchestrator.complete("prompt") == "good"
    assert unhealthy.calls == 0
