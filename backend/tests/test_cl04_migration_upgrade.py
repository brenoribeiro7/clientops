from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.postgres
def test_upgrade_from_cl03_preserves_timeline_and_accepts_cl04_events() -> None:
    if os.environ.get("CL04_UPGRADE_TEST") != "1":
        pytest.skip("run explicitly with CL04_UPGRADE_TEST=1 at the CL-03 revision")
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("MIGRATION_DATABASE_URL is required")
    engine = create_engine(url)
    actor_id = "00000000-0000-4000-8000-000000000042"
    client_id = "00000000-0000-4000-8000-000000000043"
    old_event_id = "00000000-0000-4000-8000-000000000044"
    try:
        with engine.begin() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0003_clients_equipment")
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,name,email_normalized,password_hash,role,status,must_change_password,"
                    "temporary_password_expires_at,password_changed_at,created_at,updated_at,"
                    "version) "
                    "VALUES (:id,'Migration Actor','cl04.migration@example.com','$argon2id$probe',"
                    "'ADMIN','ACTIVE',false,NULL,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,"
                    "CURRENT_TIMESTAMP,1)"
                ),
                {"id": actor_id},
            )
            connection.execute(
                text(
                    "INSERT INTO clients (id,name,status,created_at,updated_at,version) "
                    "VALUES (:id,'Migration Client','ACTIVE',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                ),
                {"id": client_id},
            )
            connection.execute(
                text(
                    "INSERT INTO timeline_events "
                    "(id,event_type,actor_type,actor_user_id,client_id,payload,occurred_at) "
                    "VALUES (:id,'client.created','USER',:actor,:client,'{}',CURRENT_TIMESTAMP)"
                ),
                {"id": old_event_id, "actor": actor_id, "client": client_id},
            )
        subprocess.run(["alembic", "upgrade", "head"], check=True, timeout=30)
        with engine.begin() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0004_quotes")
            old = connection.execute(
                text(
                    "SELECT event_type,quote_id,actor_public_access_id FROM timeline_events "
                    "WHERE id=:id"
                ),
                {"id": old_event_id},
            ).one()
            assert tuple(old) == ("client.created", None, None)
            quote_id = "00000000-0000-4000-8000-000000000045"
            connection.execute(
                text(
                    "INSERT INTO quotes "
                    "(id,client_id,status,currency,valid_until,subtotal,total,created_by,"
                    "created_at,updated_at,version) VALUES "
                    "(:id,:client,'DRAFT','BRL',CURRENT_DATE,0,0,:actor,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                ),
                {"id": quote_id, "client": client_id, "actor": actor_id},
            )
            connection.execute(
                text(
                    "INSERT INTO timeline_events "
                    "(id,event_type,actor_type,actor_user_id,client_id,quote_id,payload,"
                    "occurred_at) "
                    "VALUES ('00000000-0000-4000-8000-000000000046','quote.created','USER',"
                    ':actor,:client,:quote,\'{"number":"ORC-000001",'
                    '"status_to":"DRAFT"}\',CURRENT_TIMESTAMP)'
                ),
                {"actor": actor_id, "client": client_id, "quote": quote_id},
            )
            assert connection.execute(
                text("SELECT count(*) FROM timeline_events WHERE quote_id=:id"),
                {"id": quote_id},
            ).scalar_one() == (1)
    finally:
        engine.dispose()
