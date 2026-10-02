from __future__ import annotations

import argparse

import app.models  # noqa: F401
from app.cli._identity import tty_password, user_by_email, utc_now
from app.core.config import ApiSettings
from app.core.db import create_database_engine, create_session_factory
from app.modules.identity.passwords import hash_password
from app.modules.identity.service import revoke_all
from app.modules.timeline.service import append_event


def main() -> None:
    parser = argparse.ArgumentParser(description="Emergency ClientOps password reset")
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = tty_password()
    now = utc_now()
    settings = ApiSettings()
    engine = create_database_engine(settings)
    try:
        factory = create_session_factory(engine)
        with factory() as session:
            user = user_by_email(session, args.email, lock=True)
            user.password_hash = hash_password(password)
            user.must_change_password = False
            user.temporary_password_expires_at = None
            user.password_changed_at = now
            user.updated_at = now
            user.version += 1
            revoke_all(session, user.id, now, "OPERATOR_PASSWORD_RESET")
            append_event(
                session,
                event_type="user.password_reset",
                actor_type="SYSTEM_AUTOMATION",
                subject_user_id=user.id,
                payload={"source": "reset_password"},
                occurred_at=now,
            )
            session.commit()
    finally:
        engine.dispose()
    print("Password reset and sessions revoked.")


if __name__ == "__main__":
    main()
