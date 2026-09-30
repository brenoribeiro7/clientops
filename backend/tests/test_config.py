from __future__ import annotations

import base64

import pytest
from pydantic import ValidationError

from app.core.config import ApiSettings


def test_settings_reject_short_secret_without_echoing_value() -> None:
    marker = "sensitive-marker-that-must-not-appear"
    with pytest.raises(ValidationError) as captured:
        ApiSettings(
            APP_ENV="production",
            DATABASE_URL="postgresql+psycopg://runtime:secret@db/clientops",
            CSRF_HMAC_KEY=marker,
            RATE_LIMIT_HMAC_KEY=base64.b64encode(bytes(32)).decode(),
            PUBLIC_BASE_URL="https://clientops.example",
            TRUSTED_ORIGINS="https://clientops.example",
            TRUSTED_HOSTS="clientops.example",
            TRUSTED_PROXY_CIDRS="172.28.0.2/32",
            PRIVATE_STORAGE_ROOT="/private",
        )
    assert marker not in str(captured.value)


def test_settings_reject_broad_proxy_trust(settings: ApiSettings) -> None:
    data = settings.model_dump()
    data["TRUSTED_PROXY_CIDRS"] = "0.0.0.0/0"
    with pytest.raises(ValidationError, match="toda a Internet"):
        ApiSettings(**data)


def test_production_requires_exact_https_origin(settings: ApiSettings) -> None:
    data = settings.model_dump()
    data.update(APP_ENV="production", PUBLIC_BASE_URL="http://clientops.example")
    with pytest.raises(ValidationError, match="HTTPS"):
        ApiSettings(**data)
