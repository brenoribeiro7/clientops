from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class BusinessProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trade_name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    timezone: str | None = Field(default=None, max_length=64)
    acknowledge_timezone_change: bool = False


class BusinessProfileData(BaseModel):
    id: int
    trade_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    timezone: str | None
    is_complete: bool
    missing_fields: list[str]
    business_timezone: str | None
    business_today: date | None
    created_at: datetime
    updated_at: datetime
    version: int


class BusinessProfileResponse(BaseModel):
    data: BusinessProfileData
