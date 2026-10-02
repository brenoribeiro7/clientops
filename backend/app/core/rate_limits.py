from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, LargeBinary, String, and_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.config import ApiSettings
from app.core.db import Base
from app.core.errors import FoundationError


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint("octet_length(key_hash) = 32", name="ck_rate_limit_buckets_key_hash"),
        CheckConstraint("count >= 0", name="ck_rate_limit_buckets_count"),
        CheckConstraint("expires_at > window_start", name="ck_rate_limit_buckets_expiry"),
        Index("ix_rate_limit_buckets_expires_at", "expires_at"),
    )

    rule: Mapped[str] = mapped_column(String(40), primary_key=True, nullable=False)
    key_hash: Mapped[bytes] = mapped_column(LargeBinary, primary_key=True, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True)
class RateRule:
    name: str
    limit: int
    window_seconds: int


LOGIN_IP = RateRule("login_ip", 30, 900)
LOGIN_EMAIL = RateRule("login_email", 10, 900)
LOGIN_INSTALLATION = RateRule("login_installation", 100, 60)
RESET_ADMIN = RateRule("reset_admin", 10, 3600)
PRIVATE_USER = RateRule("private_user", 600, 300)


def _key(settings: ApiSettings, value: str) -> bytes:
    secret = base64.b64decode(settings.RATE_LIMIT_HMAC_KEY.get_secret_value(), validate=True)
    return hmac.new(secret, value.encode("utf-8"), hashlib.sha256).digest()


def _window(now: datetime, seconds: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, tz=now.tzinfo)


def consume(
    session: Session,
    settings: ApiSettings,
    rule: RateRule,
    raw_key: str,
    now: datetime,
) -> None:
    start = _window(now, rule.window_seconds)
    expires = start + timedelta(seconds=rule.window_seconds)
    table = RateLimitBucket.__table__
    insert_statement = insert(RateLimitBucket).values(
        rule=rule.name,
        key_hash=_key(settings, raw_key),
        window_start=start,
        count=1,
        expires_at=expires,
    )
    statement = insert_statement.on_conflict_do_update(
        index_elements=[table.c.rule, table.c.key_hash, table.c.window_start],
        set_={"count": table.c.count + 1, "expires_at": expires},
        where=and_(table.c.expires_at > now, table.c.count >= 0),
    ).returning(table.c.count)
    count = session.execute(statement).scalar_one()
    session.commit()
    if count > rule.limit:
        retry = max(1, int((expires - now).total_seconds()))
        raise FoundationError(
            status_code=429,
            code="RATE_LIMITED",
            message="Muitas tentativas. Tente novamente mais tarde.",
            headers={"Retry-After": str(retry)},
        )
