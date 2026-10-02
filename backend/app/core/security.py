from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import Request, Response

from app.core.config import ApiSettings, AppEnvironment
from app.core.errors import FoundationError


def _decoded_key(value: str) -> bytes:
    return base64.b64decode(value, validate=True)


def csrf_token(settings: ApiSettings, raw_bearer: str) -> str:
    digest = hmac.new(
        _decoded_key(settings.CSRF_HMAC_KEY.get_secret_value()),
        raw_bearer.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def validate_csrf(settings: ApiSettings, raw_bearer: str, supplied: str | None) -> None:
    if supplied is None or not hmac.compare_digest(csrf_token(settings, raw_bearer), supplied):
        raise FoundationError(status_code=403, code="CSRF_FAILED", message="Token CSRF inválido.")


def _origin(value: str) -> str | None:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return None
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{parsed.hostname.lower()}{port}"


def require_trusted_origin(request: Request) -> None:
    settings: ApiSettings = request.app.state.settings
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise FoundationError(status_code=403, code="ORIGIN_REJECTED", message="Origem rejeitada.")
    origin = request.headers.get("origin")
    if origin is not None:
        candidate = _origin(origin) if origin != "null" else None
    else:
        referer = request.headers.get("referer")
        candidate = _origin(referer) if referer else None
        if (
            candidate
            and candidate.startswith("http://")
            and settings.APP_ENV != AppEnvironment.DEVELOPMENT
        ):
            candidate = None
    if candidate is None or candidate not in settings.trusted_origins:
        raise FoundationError(status_code=403, code="ORIGIN_REJECTED", message="Origem rejeitada.")


@dataclass(frozen=True)
class CookiePolicy:
    name: str
    secure: bool


def cookie_policy(settings: ApiSettings) -> CookiePolicy:
    production = settings.APP_ENV in {AppEnvironment.PRODUCTION, AppEnvironment.DEMO}
    if production:
        return CookiePolicy("__Host-clientops_session", True)
    parsed = urlsplit(settings.PUBLIC_BASE_URL)
    if (
        settings.APP_ENV == AppEnvironment.DEVELOPMENT
        and parsed.scheme == "http"
        and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("cookie HTTP de desenvolvimento exige localhost")
    return CookiePolicy("clientops_session_dev", parsed.scheme == "https")


def set_session_cookie(response: Response, settings: ApiSettings, bearer: str) -> None:
    policy = cookie_policy(settings)
    response.set_cookie(
        policy.name,
        bearer,
        max_age=settings.SESSION_ABSOLUTE_SECONDS,
        httponly=True,
        secure=policy.secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: ApiSettings) -> None:
    policy = cookie_policy(settings)
    response.delete_cookie(
        policy.name,
        httponly=True,
        secure=policy.secure,
        samesite="lax",
        path="/",
    )


def raw_session_cookie(request: Request) -> str | None:
    policy = cookie_policy(request.app.state.settings)
    return request.cookies.get(policy.name)
