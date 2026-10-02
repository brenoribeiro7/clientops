from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BusinessProfile(Base):
    __tablename__ = "business_profiles"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_business_profiles_singleton"),
        CheckConstraint("version > 0", name="ck_business_profiles_version_positive"),
        CheckConstraint(
            "trade_name IS NULL OR trade_name = btrim(trade_name) AND trade_name <> ''",
            name="ck_business_profiles_trade_name",
        ),
        CheckConstraint(
            "phone IS NULL OR phone = btrim(phone) AND phone <> ''",
            name="ck_business_profiles_phone",
        ),
        CheckConstraint(
            "email IS NULL OR email = btrim(email) AND email <> ''",
            name="ck_business_profiles_email",
        ),
        CheckConstraint(
            "address IS NULL OR address = btrim(address) AND address <> ''",
            name="ck_business_profiles_address",
        ),
        CheckConstraint(
            "timezone IS NULL OR timezone = btrim(timezone) AND timezone <> ''",
            name="ck_business_profiles_timezone",
        ),
    )

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True, nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False, default=1)
