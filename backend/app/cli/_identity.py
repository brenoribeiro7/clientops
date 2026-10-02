from __future__ import annotations

import getpass
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import FoundationError
from app.modules.identity.email import InvalidIdentityEmail, normalize_identity_email
from app.modules.identity.models import User
from app.modules.identity.passwords import validate_permanent_password


def utc_now() -> datetime:
    return datetime.now(UTC)


def tty_password(prompt: str = "Password: ") -> str:
    if not sys.stdin.isatty() or not sys.stderr.isatty():
        raise RuntimeError("password input requires an interactive TTY")
    password = getpass.getpass(prompt)
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise RuntimeError("password confirmation does not match")
    validate_permanent_password(password)
    return password


def normalized_email(value: str) -> str:
    try:
        return normalize_identity_email(value)
    except InvalidIdentityEmail as error:
        raise RuntimeError("invalid email") from error


def user_by_email(session: Session, email: str, *, lock: bool = False) -> User:
    statement = select(User).where(User.email_normalized == normalized_email(email))
    if lock:
        statement = statement.with_for_update()
    user = session.execute(statement).scalar_one_or_none()
    if user is None:
        raise FoundationError(status_code=404, code="NOT_FOUND", message="user not found")
    return user
