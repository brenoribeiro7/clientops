from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('user.created','user.disabled','user.enabled',"
            "'user.password_reset','user.password_changed','business.updated')",
            name="ck_timeline_events_type_cl02",
        ),
        CheckConstraint(
            "actor_type IN ('USER','SYSTEM_AUTOMATION')", name="ck_timeline_events_actor_type"
        ),
        CheckConstraint(
            "(actor_type = 'USER' AND actor_user_id IS NOT NULL) OR "
            "(actor_type = 'SYSTEM_AUTOMATION' AND actor_user_id IS NULL)",
            name="ck_timeline_events_actor",
        ),
        CheckConstraint(
            "subject_user_id IS NOT NULL OR business_profile_id IS NOT NULL",
            name="ck_timeline_events_context",
        ),
        CheckConstraint(
            "jsonb_typeof(payload) = 'object'", name="ck_timeline_events_payload_object"
        ),
        CheckConstraint(
            "octet_length(payload::text) <= 4096", name="ck_timeline_events_payload_size"
        ),
        Index(
            "ix_timeline_events_subject_user",
            "subject_user_id",
            "occurred_at",
            "id",
            postgresql_where=text("subject_user_id IS NOT NULL"),
        ),
        Index(
            "ix_timeline_events_business_profile",
            "business_profile_id",
            "occurred_at",
            "id",
            postgresql_where=text("business_profile_id IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    subject_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    business_profile_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("business_profiles.id", ondelete="RESTRICT"), nullable=True
    )
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
