from fastapi.testclient import TestClient

from api.main import app
from memory.database import database


def test_health_endpoint(monkeypatch):
    monkeypatch.setattr(database, "initialize", lambda: None)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
