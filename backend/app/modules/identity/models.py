from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    LargeBinary,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN','TECHNICIAN')", name="ck_users_role"),
        CheckConstraint("status IN ('ACTIVE','DISABLED')", name="ck_users_status"),
        CheckConstraint(
            "(must_change_password AND temporary_password_expires_at IS NOT NULL) OR "
            "(NOT must_change_password AND temporary_password_expires_at IS NULL)",
            name="ck_users_temporary_password_state",
        ),
        CheckConstraint("version > 0", name="ck_users_version_positive"),
        CheckConstraint("name = btrim(name) AND name <> ''", name="ck_users_name"),
        CheckConstraint(
            "email_normalized = lower(btrim(email_normalized)) AND "
            "octet_length(email_normalized) <= 254 AND "
            "email_normalized ~ '^[\\x00-\\x7F]+$'",
            name="ck_users_email_normalized",
        ),
        CheckConstraint("password_hash LIKE '$argon2id$%'", name="ck_users_password_hash_argon2id"),
        Index("ix_users_role_status_name_id", "role", "status", "name", "id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False)
    temporary_password_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    password_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
    sessions: Mapped[list[Session]] = relationship(back_populates="user")


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint("octet_length(bearer_hash) = 32", name="ck_sessions_bearer_hash"),
        CheckConstraint(
            "created_at <= last_seen_at AND last_seen_at <= absolute_expires_at",
            name="ck_sessions_time_order",
        ),
        CheckConstraint(
            "(revoked_at IS NULL AND revocation_reason IS NULL) OR "
            "(revoked_at IS NOT NULL AND revocation_reason IS NOT NULL)",
            name="ck_sessions_revocation_pair",
        ),
        Index("ix_sessions_user_id", "user_id"),
        Index("ix_sessions_absolute_expires_at", "absolute_expires_at"),
        Index(
            "ix_sessions_active_candidates",
            "user_id",
            "created_at",
            "id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    bearer_hash: Mapped[bytes] = mapped_column(LargeBinary, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    user: Mapped[User] = relationship(back_populates="sessions")
