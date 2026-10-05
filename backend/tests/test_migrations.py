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
def test_cl03_schema_contains_exactly_the_phase_tables() -> None:
    engine = create_engine(_required_url("MIGRATION_DATABASE_URL"))
    try:
        assert set(inspect(engine).get_table_names(schema="public")) == {
            "alembic_version",
            "business_profiles",
            "clients",
            "equipment",
            "rate_limit_buckets",
            "sessions",
            "timeline_events",
            "users",
        }
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                == "0003_clients_equipment"
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
                == "0003_clients_equipment"
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
            connection.execute(
                text("UPDATE alembic_version SET version_num='0003_clients_equipment'")
            )
        with TestClient(create_app(settings)) as client:
            assert client.get("/api/v1/health/ready").status_code == 200
    finally:
        with migration_engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num='0003_clients_equipment'")
            )
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


@pytest.mark.postgres
def test_runtime_grants_are_least_privilege() -> None:
    engine = create_engine(_required_url("DATABASE_URL"))
    try:
        with engine.begin() as connection:
            grants = {
                (row.table_name, row.privilege_type)
                for row in connection.execute(
                    text(
                        "SELECT table_name, privilege_type "
                        "FROM information_schema.role_table_grants "
                        "WHERE grantee = current_user AND table_schema = 'public'"
                    )
                )
            }
        assert {privilege for table, privilege in grants if table == "business_profiles"} == {
            "SELECT",
            "UPDATE",
        }
        assert {privilege for table, privilege in grants if table == "timeline_events"} == {
            "SELECT",
            "INSERT",
        }
        assert {privilege for table, privilege in grants if table == "clients"} == {
            "SELECT",
            "INSERT",
        }
        assert {privilege for table, privilege in grants if table == "equipment"} == {
            "SELECT",
            "INSERT",
        }
        assert all(privilege not in {"TRUNCATE", "DELETE"} for _, privilege in grants)
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_runtime_update_grants_exclude_immutable_columns() -> None:
    engine = create_engine(_required_url("DATABASE_URL"))
    migration = create_engine(_required_url("MIGRATION_DATABASE_URL"))
    client_id = "00000000-0000-4000-8000-0000000000c3"
    equipment_id = "00000000-0000-4000-8000-0000000000e3"
    try:
        with migration.begin() as connection:
            connection.execute(text("DELETE FROM equipment WHERE id=:id"), {"id": equipment_id})
            connection.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
            connection.execute(
                text(
                    "INSERT INTO clients "
                    "(id,name,status,created_at,updated_at,version) "
                    "VALUES (:id,'Grant Client','ACTIVE',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                ),
                {"id": client_id},
            )
            connection.execute(
                text(
                    "INSERT INTO equipment "
                    "(id,client_id,name,status,created_at,updated_at,version) "
                    "VALUES (:id,:client_id,'Grant Equipment','ACTIVE',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                ),
                {"id": equipment_id, "client_id": client_id},
            )
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE equipment SET name='Allowed' WHERE id=:id"), {"id": equipment_id}
            )
            with pytest.raises(DBAPIError):
                connection.execute(
                    text("UPDATE equipment SET client_id=:client_id WHERE id=:id"),
                    {"client_id": client_id, "id": equipment_id},
                )
        with migration.begin() as connection:
            update_columns = {
                (row.table_name, row.column_name)
                for row in connection.execute(
                    text(
                        "SELECT table_name,column_name FROM information_schema.column_privileges "
                        "WHERE grantee='clientops_runtime' AND privilege_type='UPDATE' "
                        "AND table_schema='public'"
                    )
                )
            }
        assert ("equipment", "client_id") not in update_columns
        assert ("equipment", "name") in update_columns
        assert ("clients", "created_at") not in update_columns
        assert ("clients", "name") in update_columns
    finally:
        with migration.begin() as connection:
            connection.execute(text("DELETE FROM equipment WHERE id=:id"), {"id": equipment_id})
            connection.execute(text("DELETE FROM clients WHERE id=:id"), {"id": client_id})
        engine.dispose()
        migration.dispose()
