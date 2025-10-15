from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ.setdefault("ARCADIA_DATABASE_URL", "sqlite://")

from app.main import app  # noqa: E402
from app.db.session import dispose_engine  # noqa: E402


def teardown_module() -> None:  # pragma: no cover - test cleanup
    dispose_engine()


def test_database_health_endpoint_success() -> None:
    client = TestClient(app)
    response = client.get("/healthz/database")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "pool" in payload
    assert "persistence_mode" in payload


def test_database_health_endpoint_failure(monkeypatch) -> None:
    client = TestClient(app)

    def raise_runtime_error():
        raise RuntimeError("missing database url")

    monkeypatch.setattr("app.main.get_engine", raise_runtime_error)
    response = client.get("/healthz/database")
    assert response.status_code == 503
    assert response.json()["detail"] == "missing database url"
