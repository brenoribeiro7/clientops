from __future__ import annotations

from fastapi import Request
from fastapi.testclient import TestClient
from pytest import CaptureFixture

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


def test_logs_include_only_validated_normalized_client_ip(
    settings: ApiSettings, capsys: CaptureFixture[str]
) -> None:
    raw_header = "2001:0db8:0000:0000:0000:0000:0000:0001"
    with TestClient(create_app(settings), client=("172.28.0.2", 50000)) as proxy:
        proxy.get("/api/v1/health/live", headers={"X-Forwarded-For": raw_header})
    logs = capsys.readouterr().err
    assert raw_header not in logs
    assert '"client_ip":"2001:db8::1"' in logs


def test_client_contact_body_and_query_canaries_are_absent_from_logs(
    settings: ApiSettings, capsys: CaptureFixture[str]
) -> None:
    canaries = (
        "PHONE-CANARY-0303",
        "EMAIL-CANARY-0303",
        "ADDRESS-CANARY-0303",
        "NOTES-CANARY-0303",
        "QUERY-CANARY-0303",
    )
    with TestClient(create_app(settings), client=("198.51.100.31", 50000)) as direct:
        direct.get(f"/api/v1/clients?q={canaries[-1]}")
        direct.post(
            "/api/v1/clients",
            json={
                "name": "Client",
                "phone": canaries[0],
                "email": canaries[1],
                "address": canaries[2],
                "notes": canaries[3],
            },
        )
    logs = capsys.readouterr().err
    for canary in canaries:
        assert canary not in logs
