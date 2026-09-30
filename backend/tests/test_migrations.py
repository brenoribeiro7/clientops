from __future__ import annotations

import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

from app.core.config import ApiSettings
from app.main import create_app


def _required_url(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        pytest.skip(f"{name} is required")
    return value


@pytest.mark.postgres
def test_empty_foundation_schema_has_only_alembic_version() -> None:
    engine = create_engine(_required_url("MIGRATION_DATABASE_URL"))
    try:
        assert inspect(engine).get_table_names(schema="public") == ["alembic_version"]
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0001_foundation"
            )
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_runtime_role_can_read_revision_but_cannot_execute_ddl() -> None:
    engine = create_engine(_required_url("DATABASE_URL"))
    try:
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0001_foundation"
            )
            with pytest.raises(DBAPIError):
                connection.execute(text("CREATE TABLE forbidden_runtime_ddl (id integer)"))
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_readiness_uses_real_database_and_migration_state() -> None:
    settings = ApiSettings()
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health/ready").status_code == 200


@pytest.mark.postgres
def test_readiness_rejects_and_recovers_from_migration_mismatch() -> None:
    migration_engine = create_engine(_required_url("MIGRATION_DATABASE_URL"))
    settings = ApiSettings()
    try:
        with migration_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='stale_revision'"))
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health/ready").status_code == 503
        with migration_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='0001_foundation'"))
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
    finally:
        with migration_engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num='0001_foundation'"))
        migration_engine.dispose()


@pytest.mark.postgres
def test_concurrent_migrators_finish_consistently() -> None:
    processes = [
        subprocess.Popen(
            ["alembic", "upgrade", "head"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    results = [process.communicate(timeout=30) for process in processes]
    assert [process.returncode for process in processes] == [0, 0], results
