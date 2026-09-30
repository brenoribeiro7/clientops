from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import ApiSettings
from app.main import create_app


def test_valid_request_id_is_echoed(client: TestClient) -> None:
    request_id = "cdb40b6f-b9f7-4f53-8d31-41f08798ac4f"
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": request_id})
    assert response.headers["x-request-id"] == request_id


def test_invalid_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"X-Request-ID": "not-a-uuid"})
    assert response.headers["x-request-id"] != "not-a-uuid"
    assert len(response.headers["x-request-id"]) == 36


def test_forwarded_proto_is_ignored_from_untrusted_client(settings: ApiSettings) -> None:
    app = create_app(settings)

    @app.get("/_test/scheme")
    def scheme(request: Request) -> dict[str, str]:
        return {"scheme": request.url.scheme}

    with TestClient(app, client=("198.51.100.10", 50000)) as direct:
        response = direct.get("/_test/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json() == {"scheme": "http"}


def test_forwarded_proto_is_accepted_from_expected_proxy(settings: ApiSettings) -> None:
    app = create_app(settings)

    @app.get("/_test/scheme")
    def scheme(request: Request) -> dict[str, str]:
        return {"scheme": request.url.scheme}

    with TestClient(app, client=("172.28.0.2", 50000)) as proxy:
        response = proxy.get("/_test/scheme", headers={"X-Forwarded-Proto": "https"})
    assert response.json() == {"scheme": "https"}
