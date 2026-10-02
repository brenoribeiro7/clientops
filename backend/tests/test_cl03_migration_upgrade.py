from __future__ import annotations

import os
import subprocess

import pytest
from sqlalchemy import create_engine, text


@pytest.mark.postgres
def test_upgrade_from_cl02_preserves_timeline_and_accepts_cl03_events() -> None:
    url = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("MIGRATION_DATABASE_URL is required")
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            if revision != "0002_identity_sessions_security":
                pytest.skip("this regression is run explicitly against the CL-02 revision")
            connection.execute(
                text(
                    "INSERT INTO users "
                    "(id,name,email_normalized,password_hash,role,status,must_change_password,"
                    "temporary_password_expires_at,password_changed_at,created_at,updated_at,"
                    "version) "
                    "VALUES ('00000000-0000-4000-8000-000000000032','Migration Actor',"
                    "'migration.actor@example.com','$argon2id$probe','ADMIN','ACTIVE',false,NULL,"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO timeline_events "
                    "(id,event_type,actor_type,actor_user_id,subject_user_id,business_profile_id,"
                    "payload,occurred_at) VALUES "
                    "('00000000-0000-4000-8000-000000000033','user.created','USER',"
                    "'00000000-0000-4000-8000-000000000032',"
                    "'00000000-0000-4000-8000-000000000032',NULL,'{}',CURRENT_TIMESTAMP),"
                    "('00000000-0000-4000-8000-000000000034','business.updated',"
                    "'SYSTEM_AUTOMATION',NULL,NULL,1,'{}',CURRENT_TIMESTAMP)"
                )
            )
        subprocess.run(["alembic", "upgrade", "head"], check=True, timeout=30)
        with engine.begin() as connection:
            assert connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one() == ("0003_clients_equipment")
            old = connection.execute(
                text(
                    "SELECT id,event_type,client_id FROM timeline_events "
                    "WHERE id IN ('00000000-0000-4000-8000-000000000033',"
                    "'00000000-0000-4000-8000-000000000034') ORDER BY id"
                )
            ).all()
            assert [(str(row.id), row.event_type, row.client_id) for row in old] == [
                ("00000000-0000-4000-8000-000000000033", "user.created", None),
                ("00000000-0000-4000-8000-000000000034", "business.updated", None),
            ]
            connection.execute(
                text(
                    "INSERT INTO clients (id,name,status,created_at,updated_at,version) VALUES "
                    "('00000000-0000-4000-8000-000000000035','Migration Client','ACTIVE',"
                    "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO timeline_events "
                    "(id,event_type,actor_type,actor_user_id,subject_user_id,business_profile_id,"
                    "client_id,payload,occurred_at) VALUES "
                    "('00000000-0000-4000-8000-000000000036','client.created','USER',"
                    "'00000000-0000-4000-8000-000000000032',NULL,NULL,"
                    "'00000000-0000-4000-8000-000000000035','{}',CURRENT_TIMESTAMP)"
                )
            )
            assert (
                connection.execute(
                    text(
                        "SELECT count(*) FROM timeline_events WHERE client_id="
                        "'00000000-0000-4000-8000-000000000035'"
                    )
                ).scalar_one()
                == 1
            )
    finally:
        engine.dispose()
