from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, TypedDict
from uuid import UUID
from zoneinfo import ZoneInfo

MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.001")
MAX_MONEY = Decimal("999999999.99")
MAX_UNIT_PRICE = Decimal("9999999.99")
MAX_QUANTITY = Decimal("9999.999")

_QUANTITY_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,3})?\Z")
_MONEY_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,6})\.[0-9]{2}\Z")

QuoteStatus = Literal["DRAFT", "SENT", "APPROVED", "CANCELLED"]


class SnapshotLogo(TypedDict):
    storage_key: str
    content_hash: str
    content_type: str


class SnapshotItem(TypedDict):
    id: str
    position: int
    description: str
    quantity: str
    unit_price: str
    line_total: str


class QuoteSnapshot(TypedDict):
    schema_version: int
    quote: dict[str, object]
    business: dict[str, object]
    client: dict[str, object]
    items: list[SnapshotItem]
    subtotal: str
    total: str
    notes: str | None


@dataclass(frozen=True)
class CalculatedItem:
    id: UUID
    position: int
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal


def parse_quantity(value: object) -> Decimal:
    if not isinstance(value, str) or _QUANTITY_PATTERN.fullmatch(value) is None:
        raise ValueError("quantity must be a plain decimal string with at most three places")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid quantity") from error
    if parsed < QUANTITY_QUANTUM or parsed > MAX_QUANTITY:
        raise ValueError("quantity is outside the supported range")
    return parsed.quantize(QUANTITY_QUANTUM)


def parse_money(value: object) -> Decimal:
    if not isinstance(value, str) or _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError("money must be a plain decimal string with exactly two places")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid money") from error
    if parsed < 0 or parsed > MAX_UNIT_PRICE:
        raise ValueError("money is outside the supported range")
    return parsed.quantize(MONEY_QUANTUM)


def quantity_string(value: Decimal) -> str:
    return format(value.quantize(QUANTITY_QUANTUM), ".3f")


def money_string(value: Decimal) -> str:
    return format(value.quantize(MONEY_QUANTUM), ".2f")


def calculate_line_total(quantity: Decimal, unit_price: Decimal) -> Decimal:
    value = (quantity * unit_price).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    if value > MAX_MONEY:
        raise ValueError("line total exceeds the supported range")
    return value


def calculate_total(items: list[CalculatedItem]) -> Decimal:
    total = sum((item.line_total for item in items), start=Decimal("0.00"))
    if total > MAX_MONEY:
        raise ValueError("quote total exceeds the supported range")
    return total.quantize(MONEY_QUANTUM)


def current_business_date(now: datetime, timezone: str) -> date:
    return now.astimezone(ZoneInfo(timezone)).date()


def is_commercially_expired(status: QuoteStatus, valid_until: date, today: date) -> bool:
    return status == "SENT" and valid_until < today


def quote_number(value: int) -> str:
    return f"ORC-{value:06d}"


def build_snapshot(
    *,
    quote_id: UUID,
    number: int,
    sent_at: datetime,
    valid_until: date,
    business_timezone: str,
    business: dict[str, str],
    client: dict[str, str | UUID | None],
    items: list[CalculatedItem],
    subtotal: Decimal,
    notes: str | None,
) -> QuoteSnapshot:
    return {
        "schema_version": 1,
        "quote": {
            "id": str(quote_id),
            "number": quote_number(number),
            "sent_at": sent_at.isoformat().replace("+00:00", "Z"),
            "currency": "BRL",
            "valid_until": valid_until.isoformat(),
            "business_timezone": business_timezone,
        },
        "business": {
            "trade_name": business["trade_name"],
            "phone": business["phone"],
            "email": business["email"],
            "address": business["address"],
            "logo": None,
        },
        "client": {
            "id": str(client["id"]),
            "name": client["name"],
            "phone": client["phone"],
            "email": client["email"],
            "address": client["address"],
        },
        "items": [
            {
                "id": str(item.id),
                "position": item.position,
                "description": item.description,
                "quantity": quantity_string(item.quantity),
                "unit_price": money_string(item.unit_price),
                "line_total": money_string(item.line_total),
            }
            for item in sorted(items, key=lambda value: value.position)
        ],
        "subtotal": money_string(subtotal),
        "total": money_string(subtotal),
        "notes": notes,
    }
