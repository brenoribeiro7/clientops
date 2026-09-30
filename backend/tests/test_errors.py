from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import ApiSettings
from app.core.errors import FoundationError
from app.main import create_app


def test_not_found_uses_sanitized_envelope(client: TestClient) -> None:
    response = client.get("/does-not-exist?secret=never-log-this")
    assert response.status_code == 404
    body = response.json()["error"]
    assert body["code"] == "NOT_FOUND"
    assert body["fields"] == []
    assert body["details"] == {}
    assert body["request_id"] == response.headers["x-request-id"]
    assert "does-not-exist" not in response.text


def test_foundation_error_has_stable_contract(settings: ApiSettings) -> None:
    app: FastAPI = create_app(settings)

    @app.get("/_test/error")
    def fail() -> None:
        raise FoundationError(
            status_code=503,
            code="TEMPORARILY_UNAVAILABLE",
            message="Indisponível.",
        )

    with TestClient(app) as client:
        response = client.get("/_test/error")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TEMPORARILY_UNAVAILABLE"
    assert response.headers["cache-control"] == "no-store"
