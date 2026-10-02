from __future__ import annotations

import argparse
import json
from uuid import UUID

from sqlalchemy import create_engine, select, text

import app.models  # noqa: F401
from app.cli._identity import utc_now
from app.core.config import ApiSettings, AppEnvironment, MigrationSettings
from app.core.db import create_database_engine, create_session_factory
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password
from app.modules.timeline.service import append_event

ADMIN_ID = UUID("00000000-0000-4000-8000-000000000001")
ADMIN_EMAIL = "admin.e2e@example.com"
ADMIN_PASSWORD = "ClientOps E2E admin password 2026!"


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the isolated CL-02 browser-test identity")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    settings = ApiSettings()
    if settings.APP_ENV != AppEnvironment.TEST:
        raise RuntimeError("test identity fixture is restricted to APP_ENV=test")
    if args.reset:
        migration_settings = MigrationSettings()
        migration_engine = create_engine(
            migration_settings.MIGRATION_DATABASE_URL.get_secret_value()
        )
        try:
            with migration_engine.begin() as connection:
                connection.execute(
                    text(
                        "TRUNCATE timeline_events, sessions, rate_limit_buckets, users "
                        "RESTART IDENTITY CASCADE"
                    )
                )
                connection.execute(
                    text(
                        "UPDATE business_profiles SET trade_name=NULL, phone=NULL, email=NULL, "
                        "address=NULL, timezone=NULL, updated_at=CURRENT_TIMESTAMP, version=1 "
                        "WHERE id=1"
                    )
                )
        finally:
            migration_engine.dispose()
    now = utc_now()
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        with factory() as session:
            existing = session.scalar(select(User).where(User.email_normalized == ADMIN_EMAIL))
            if existing is None:
                user = User(
                    id=ADMIN_ID,
                    name="E2E Admin",
                    email_normalized=ADMIN_EMAIL,
                    password_hash=hash_password(ADMIN_PASSWORD),
                    role="ADMIN",
                    status="ACTIVE",
                    must_change_password=False,
                    temporary_password_expires_at=None,
                    password_changed_at=now,
                    created_at=now,
                    updated_at=now,
                    version=1,
                )
                session.add(user)
                append_event(
                    session,
                    event_type="user.created",
                    actor_type="SYSTEM_AUTOMATION",
                    subject_user_id=user.id,
                    payload={"role": "ADMIN", "status": "ACTIVE", "source": "test_fixture"},
                    occurred_at=now,
                )
                session.commit()
        print(json.dumps({"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
