from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.modules.quotes.domain import money_string, parse_money, parse_quantity, quantity_string

Status = Literal["DRAFT", "SENT", "APPROVED", "CANCELLED"]
Sort = Literal["number", "-number", "created_at", "-created_at", "valid_until", "-valid_until"]


def _clean(value: str | None, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError("value is required")
        return None
    cleaned = value.strip()
    if not cleaned:
        if required:
            raise ValueError("value cannot be blank")
        return None
    if any(ord(character) < 32 and character not in {"\t", "\n"} for character in cleaned):
        raise ValueError("control characters are not allowed")
    return cleaned


class QuoteItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID | None = None
    position: int = Field(ge=1, le=100)
    description: str = Field(max_length=500)
    quantity: str
    unit_price: str

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        return _clean(value, required=True) if isinstance(value, str) else value

    @field_validator("quantity", mode="before")
    @classmethod
    def validate_quantity(cls, value: object) -> str:
        return quantity_string(parse_quantity(value))

    @field_validator("unit_price", mode="before")
    @classmethod
    def validate_unit_price(cls, value: object) -> str:
        return money_string(parse_money(value))


class QuoteInputBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @staticmethod
    def validate_positions(items: list[QuoteItemInput]) -> list[QuoteItemInput]:
        if len(items) > 100:
            raise ValueError("at most 100 items are allowed")
        if sorted(item.position for item in items) != list(range(1, len(items) + 1)):
            raise ValueError("item positions must be contiguous")
        ids = [item.id for item in items if item.id is not None]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        return items


class QuoteCreate(QuoteInputBase):
    client_id: UUID
    valid_until: date
    notes: str | None = Field(default=None, max_length=5000)
    items: list[QuoteItemInput] = Field(default_factory=list)

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: object) -> object:
        return _clean(value, required=False) if isinstance(value, str) or value is None else value

    @field_validator("items")
    @classmethod
    def positions(cls, value: list[QuoteItemInput]) -> list[QuoteItemInput]:
        return cls.validate_positions(value)

    @model_validator(mode="after")
    def ids_are_server_generated(self) -> QuoteCreate:
        if any(item.id is not None for item in self.items):
            raise ValueError("item id is not accepted when creating a quote")
        return self


class QuotePatch(QuoteInputBase):
    client_id: UUID | SkipJsonSchema[None] = None
    valid_until: date | SkipJsonSchema[None] = None
    notes: str | None = Field(default=None, max_length=5000)
    items: list[QuoteItemInput] | SkipJsonSchema[None] = None

    @field_validator("client_id", "valid_until", "items", mode="before")
    @classmethod
    def non_nullable_fields(cls, value: object) -> object:
        if value is None:
            raise ValueError("field cannot be null")
        return value

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: object) -> object:
        return _clean(value, required=False) if isinstance(value, str) or value is None else value

    @field_validator("items")
    @classmethod
    def positions(cls, value: list[QuoteItemInput] | None) -> list[QuoteItemInput] | None:
        return cls.validate_positions(value) if value is not None else value


class EmptyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def clean_reason(cls, value: object) -> object:
        return _clean(value, required=True) if isinstance(value, str) else value


class RotateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_access_id: UUID | None


class ApproveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accept: Literal[True]


class QuoteListQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: Status | None = None
    client_id: UUID | None = None
    is_expired: bool | None = None
    q: str | None = Field(default=None, min_length=2, max_length=100)
    sort: Sort = "-created_at"


class TimelineQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PageData(BaseModel):
    number: int
    size: int
    total: int
    total_pages: int


class QuoteItemData(BaseModel):
    id: UUID
    position: int
    description: str
    quantity: str
    unit_price: str
    line_total: str


class PublicAccessData(BaseModel):
    id: UUID
    expires_at: datetime
    revoked_at: datetime | None


class QuoteSummary(BaseModel):
    id: UUID
    number: str
    client_id: UUID
    status: Status
    currency: Literal["BRL"]
    valid_until: date
    subtotal: str
    total: str
    is_expired: bool
    created_at: datetime
    updated_at: datetime
    version: int


class QuoteDetail(QuoteSummary):
    source_quote_id: UUID | None
    notes: str | None
    items: list[QuoteItemData]
    commercial_snapshot: dict[str, object] | None
    sent_at: datetime | None
    approved_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    public_access: PublicAccessData | None


class QuoteResponse(BaseModel):
    data: QuoteDetail


class QuotePage(BaseModel):
    data: list[QuoteSummary]
    page: PageData


class IssuedPublicAccess(PublicAccessData):
    share_url: str


class QuoteIssuedResponse(BaseModel):
    data: QuoteDetail
    public_access: IssuedPublicAccess


class PublicAccessResponse(BaseModel):
    data: PublicAccessData


class PublicAccessIssuedResponse(BaseModel):
    data: IssuedPublicAccess


class TimelineActor(BaseModel):
    type: Literal["USER", "CUSTOMER_QUOTE_LINK", "SYSTEM_AUTOMATION"]
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


class PublicBusiness(BaseModel):
    trade_name: str
    phone: str
    email: str
    address: str
    has_logo: bool


class PublicClient(BaseModel):
    name: str


class PublicQuoteItem(BaseModel):
    position: int
    description: str
    quantity: str
    unit_price: str
    line_total: str


class PublicQuoteData(BaseModel):
    business: PublicBusiness
    client: PublicClient
    number: str
    notes: str | None
    valid_until: date
    items: list[PublicQuoteItem]
    subtotal: str
    total: str
    currency: Literal["BRL"]
    status: Literal["SENT", "APPROVED"]
    sent_at: datetime
    approved_at: datetime | None
    is_expired: bool
    can_approve: bool
    server_now: datetime
    business_today: date


class PublicQuoteResponse(BaseModel):
    data: PublicQuoteData


class PublicApprovalData(BaseModel):
    status: Literal["APPROVED"]
    approved_at: datetime


class PublicApprovalResponse(BaseModel):
    data: PublicApprovalData
