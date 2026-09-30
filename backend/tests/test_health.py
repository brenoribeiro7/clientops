from __future__ import annotations

from unittest.mock import Mock

from fastapi.testclient import TestClient


def test_liveness_is_minimal_and_no_store(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_readiness_is_healthy_when_all_probes_pass(client: TestClient, monkeypatch: object) -> None:
    monkeypatch.setattr("app.health.check_database", Mock())  # type: ignore[attr-defined]
    monkeypatch.setattr("app.health.probe_private_storage", Mock())  # type: ignore[attr-defined]
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_is_sanitized_when_database_fails(
    client: TestClient, monkeypatch: object
) -> None:
    monkeypatch.setattr(  # type: ignore[attr-defined]
        "app.health.check_database", Mock(side_effect=RuntimeError("password=sensitive"))
    )
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"
    assert "sensitive" not in response.text
