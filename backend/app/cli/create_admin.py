from __future__ import annotations

import argparse
from uuid import uuid4

from sqlalchemy import func, select

import app.models  # noqa: F401
from app.cli._identity import normalized_email, tty_password, utc_now
from app.core.config import ApiSettings
from app.core.db import create_database_engine, create_session_factory
from app.modules.identity.models import User
from app.modules.identity.passwords import hash_password
from app.modules.timeline.service import append_event

ADMIN_BOOTSTRAP_LOCK = 1431197003


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a ClientOps Admin")
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--additional",
        action="store_true",
        help="explicitly authorize creation when an Admin already exists",
    )
    args = parser.parse_args()
    name = args.name.strip()
    if not name:
        parser.error("--name cannot be blank")
    email = normalized_email(args.email)
    password = tty_password()
    now = utc_now()
    settings = ApiSettings()
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        with factory() as session:
            session.execute(select(func.pg_advisory_xact_lock(ADMIN_BOOTSTRAP_LOCK)))
            admin_count = session.scalar(
                select(func.count()).select_from(User).where(User.role == "ADMIN")
            )
            if admin_count and not args.additional:
                raise RuntimeError("an Admin exists; pass --additional explicitly")
            if session.scalar(
                select(func.count()).select_from(User).where(User.email_normalized == email)
            ):
                raise RuntimeError("email already exists")
            user = User(
                id=uuid4(),
                name=name,
                email_normalized=email,
                password_hash=hash_password(password),
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
                payload={"role": "ADMIN", "status": "ACTIVE", "source": "create_admin"},
                occurred_at=now,
            )
            session.commit()
    finally:
        engine.dispose()
    print("Admin created.")


if __name__ == "__main__":
    main()
