from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Status = Literal["ACTIVE", "ARCHIVED"]
Sort = Literal["name", "-name", "created_at", "-created_at"]


def _clean(value: str | None, *, multiline: bool) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    allowed = {"\t", "\n"} if multiline else set()
    if any(ord(character) < 32 and character not in allowed for character in cleaned):
        raise ValueError("control characters are not allowed")
    return cleaned


def _required(value: str, *, multiline: bool = False) -> str:
    cleaned = _clean(value, multiline=multiline)
    if cleaned is None:
        raise ValueError("value cannot be blank")
    return cleaned


class ClientFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return _required(value, multiline=False) if isinstance(value, str) else value

    @field_validator("phone", "email", mode="before")
    @classmethod
    def clean_single_line(cls, value: object) -> object:
        return _clean(value, multiline=False) if isinstance(value, str) or value is None else value

    @field_validator("address", "notes", mode="before")
    @classmethod
    def clean_multiline(cls, value: object) -> object:
        return _clean(value, multiline=True) if isinstance(value, str) or value is None else value


class ClientCreate(ClientFields):
    pass


class ClientPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("name cannot be null")
        return _required(value, multiline=False) if isinstance(value, str) else value

    @field_validator("phone", "email", mode="before")
    @classmethod
    def clean_single_line(cls, value: object) -> object:
        return _clean(value, multiline=False) if isinstance(value, str) or value is None else value

    @field_validator("address", "notes", mode="before")
    @classmethod
    def clean_multiline(cls, value: object) -> object:
        return _clean(value, multiline=True) if isinstance(value, str) or value is None else value


class EquipmentFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=160)
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=100)
    location_description: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        return _required(value, multiline=False) if isinstance(value, str) else value

    @field_validator("brand", "model", "serial_number", "location_description", mode="before")
    @classmethod
    def clean_single_line(cls, value: object) -> object:
        return _clean(value, multiline=False) if isinstance(value, str) or value is None else value

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: object) -> object:
        return _clean(value, multiline=True) if isinstance(value, str) or value is None else value


class EquipmentCreate(EquipmentFields):
    pass


class EquipmentPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=160)
    brand: str | None = Field(default=None, max_length=120)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=100)
    location_description: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=5000)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: object) -> object:
        if value is None:
            raise ValueError("name cannot be null")
        return _required(value, multiline=False) if isinstance(value, str) else value

    @field_validator("brand", "model", "serial_number", "location_description", mode="before")
    @classmethod
    def clean_single_line(cls, value: object) -> object:
        return _clean(value, multiline=False) if isinstance(value, str) or value is None else value

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: object) -> object:
        return _clean(value, multiline=True) if isinstance(value, str) or value is None else value


class ListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Status = "ACTIVE"
    q: str | None = Field(default=None, min_length=2, max_length=100)
    sort: Sort = "-created_at"


class TimelineQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageData(BaseModel):
    number: int
    size: int
    total: int
    total_pages: int


class ClientSummary(BaseModel):
    id: UUID
    name: str
    phone: str | None
    email: str | None
    status: Status
    created_at: datetime
    updated_at: datetime
    version: int


class ClientLinks(BaseModel):
    equipment: str
    timeline: str


class ClientData(ClientSummary):
    address: str | None
    notes: str | None
    archived_at: datetime | None
    links: ClientLinks


class ClientResponse(BaseModel):
    data: ClientData


class ClientPage(BaseModel):
    data: list[ClientSummary]
    page: PageData


class EquipmentSummary(BaseModel):
    id: UUID
    client_id: UUID
    name: str
    brand: str | None
    model: str | None
    serial_number: str | None
    location_description: str | None
    status: Status
    created_at: datetime
    updated_at: datetime
    version: int


class EquipmentData(EquipmentSummary):
    notes: str | None
    archived_at: datetime | None


class EquipmentResponse(BaseModel):
    data: EquipmentData


class EquipmentPage(BaseModel):
    data: list[EquipmentSummary]
    page: PageData


class TimelineActor(BaseModel):
    type: Literal["USER", "SYSTEM_AUTOMATION"]
    display_name: str


class TimelineData(BaseModel):
    id: UUID
    event_type: str
    occurred_at: datetime
    actor: TimelineActor
    payload: dict[str, object]


class TimelinePage(BaseModel):
    data: list[TimelineData]
    page: PageData
