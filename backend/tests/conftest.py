from __future__ import annotations

import base64
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import ApiSettings, AppEnvironment
from app.main import create_app


class FakeClock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def now_utc(self) -> datetime:
        return self.current


@pytest.fixture
def settings(tmp_path: Path) -> ApiSettings:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    key = base64.b64encode(bytes(range(32))).decode("ascii")
    return ApiSettings(
        APP_ENV=AppEnvironment.TEST,
        DATABASE_URL="postgresql+psycopg://runtime:secret@localhost:5432/clientops_test",
        CSRF_HMAC_KEY=key,
        RATE_LIMIT_HMAC_KEY=key,
        PUBLIC_BASE_URL="http://localhost:8080",
        TRUSTED_ORIGINS="http://localhost:8080",
        TRUSTED_HOSTS="testserver,localhost",
        TRUSTED_PROXY_CIDRS="172.28.0.2/32",
        PRIVATE_STORAGE_ROOT=str(root),
        LOG_LEVEL="INFO",
    )


@pytest.fixture
def client(settings: ApiSettings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client
