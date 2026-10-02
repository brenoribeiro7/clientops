from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier, Event

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.core.config import ApiSettings, AppEnvironment
from app.core.errors import FoundationError
from app.core.middleware import TrustedProxyMiddleware
from app.core.security import cookie_policy, csrf_token, require_trusted_origin, validate_csrf
from app.main import create_app
from app.modules.business.models import BusinessProfile
from app.modules.business.service import FIELDS, serialize
from app.modules.identity.email import InvalidIdentityEmail, normalize_identity_email
from app.modules.identity.passwords import (
    PASSWORD_HASHER,
    argon_slot,
    hash_password,
    needs_rehash,
    validate_permanent_password,
    verify_password,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" User.Name+tag@EXAMPLE.com ", "user.name+tag@example.com"),
        ("A@café.example", "a@xn--caf-dma.example"),
    ],
)
def test_identity_email_normalization(raw: str, expected: str) -> None:
    assert normalize_identity_email(raw) == expected


@pytest.mark.parametrize("raw", ["tést@example.com", "missing-at", "a@localhost"])
def test_identity_email_rejects_non_contract_values(raw: str) -> None:
    with pytest.raises(InvalidIdentityEmail):
        normalize_identity_email(raw)


def test_password_policy_preserves_unicode_and_whitespace() -> None:
    password = "  Senha longa 🔐 segura  "
    validate_permanent_password(password)
    encoded = hash_password(password)
    assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
    assert verify_password(encoded, password)
    assert not verify_password(encoded, password.strip())
    assert not needs_rehash(encoded)
    assert PASSWORD_HASHER.hash_len == 32
    assert PASSWORD_HASHER.salt_len == 16


@pytest.mark.parametrize(
    "password",
    ["short", "passwordpassword", "x" * 129, "🔐" * 129],
)
def test_password_policy_rejects_invalid_or_blocklisted(password: str) -> None:
    with pytest.raises(ValueError):
        validate_permanent_password(password)


def test_argon_slot_rejects_a_third_concurrent_operation() -> None:
    entered = Barrier(3)
    release = Event()

    def hold() -> None:
        with argon_slot():
            entered.wait(timeout=5)
            release.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hold)
        second = pool.submit(hold)
        entered.wait(timeout=5)
        with pytest.raises(FoundationError) as captured, argon_slot():
            pass
        assert captured.value.status_code == 429
        assert captured.value.headers == {"Retry-After": "1"}
        release.set()
        first.result(timeout=5)
        second.result(timeout=5)


def test_csrf_is_deterministic_urlsafe_and_constant_time_checked(
    settings: ApiSettings,
) -> None:
    raw = base64.urlsafe_b64encode(bytes(range(32))).rstrip(b"=").decode("ascii")
    token = csrf_token(settings, raw)
    assert len(token) == 43
    assert token == csrf_token(settings, raw)
    validate_csrf(settings, raw, token)
    with pytest.raises(FoundationError) as captured:
        validate_csrf(settings, raw, token[:-1] + "x")
    assert captured.value.code == "CSRF_FAILED"


def test_development_cookie_policy(settings: ApiSettings) -> None:
    policy = cookie_policy(settings)
    assert policy.name == "clientops_session_dev"
    assert policy.secure is False


def _ip_app(settings: ApiSettings) -> FastAPI:
    app = FastAPI()

    @app.get("/")
    def inspect_request(request: Request) -> dict[str, object]:
        return {
            "client_ip": request.state.client_ip,
            "forwarded": request.headers.get("x-forwarded-for"),
        }

    app.add_middleware(TrustedProxyMiddleware, settings=settings)
    return app


def test_untrusted_peer_cannot_forge_client_ip(settings: ApiSettings) -> None:
    with TestClient(_ip_app(settings), client=("198.51.100.20", 50000)) as client:
        response = client.get("/", headers={"X-Forwarded-For": "203.0.113.9"})
    assert response.json() == {"client_ip": "198.51.100.20", "forwarded": None}


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [("203.0.113.9", "203.0.113.9"), ("2001:0db8::1", "2001:db8::1")],
)
def test_trusted_proxy_accepts_one_normalized_ip(
    settings: ApiSettings, forwarded: str, expected: str
) -> None:
    with TestClient(_ip_app(settings), client=("172.28.0.2", 50000)) as client:
        response = client.get("/", headers={"X-Forwarded-For": forwarded})
    assert response.json()["client_ip"] == expected


@pytest.mark.parametrize("forwarded", ["203.0.113.1, 198.51.100.2", "not-an-ip", ""])
def test_trusted_proxy_rejects_malformed_or_chained_xff(
    settings: ApiSettings, forwarded: str
) -> None:
    with TestClient(_ip_app(settings), client=("172.28.0.2", 50000)) as client:
        response = client.get("/", headers={"X-Forwarded-For": forwarded})
    assert response.json()["client_ip"] is None


def test_origin_policy_is_fail_closed_and_never_falls_back_from_bad_origin(
    settings: ApiSettings,
) -> None:
    development = settings.model_copy(update={"APP_ENV": AppEnvironment.DEVELOPMENT})
    app = create_app(development)

    @app.post("/_test/origin")
    def origin(request: Request) -> dict[str, bool]:
        require_trusted_origin(request)
        return {"accepted": True}

    with TestClient(app, client=("198.51.100.2", 50000)) as client:
        assert client.post("/_test/origin").status_code == 403
        assert client.post("/_test/origin", headers={"Origin": "null"}).status_code == 403
        assert (
            client.post(
                "/_test/origin",
                headers={
                    "Origin": "https://evil.example",
                    "Referer": f"{settings.PUBLIC_BASE_URL}/safe",
                },
            ).status_code
            == 403
        )
        assert (
            client.post("/_test/origin", headers={"Origin": settings.PUBLIC_BASE_URL}).status_code
            == 200
        )
        assert (
            client.post(
                "/_test/origin", headers={"Referer": f"{settings.PUBLIC_BASE_URL}/safe"}
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/_test/origin",
                headers={"Origin": settings.PUBLIC_BASE_URL, "Sec-Fetch-Site": "cross-site"},
            ).status_code
            == 403
        )


@pytest.mark.parametrize("missing", FIELDS[:-1])
def test_business_profile_completeness_is_independent_from_available_civil_time(
    missing: str,
) -> None:
    values: dict[str, str | None] = {
        "trade_name": "ClientOps",
        "phone": "+55 71 3000-0000",
        "email": "contact@example.com",
        "address": "Salvador, BA",
        "timezone": "America/Bahia",
    }
    values[missing] = None
    profile = BusinessProfile(
        id=1,
        **values,
        created_at=datetime(2026, 6, 2, 1, 0, tzinfo=UTC),
        updated_at=datetime(2026, 6, 2, 1, 0, tzinfo=UTC),
        version=1,
    )
    data = serialize(profile, datetime(2026, 6, 2, 1, 0, tzinfo=UTC))
    assert not data.is_complete
    assert data.missing_fields == [missing]
    assert data.business_timezone == "America/Bahia"
    assert data.business_today is not None
    assert data.business_today.isoformat() == "2026-06-01"
