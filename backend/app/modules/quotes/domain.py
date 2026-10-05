from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Literal, TypedDict, cast
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

MONEY_QUANTUM = Decimal("0.01")
QUANTITY_QUANTUM = Decimal("0.001")
MAX_MONEY = Decimal("999999999.99")
MAX_UNIT_PRICE = Decimal("9999999.99")
MAX_QUANTITY = Decimal("9999.999")

_QUANTITY_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,3})?\Z")
_MONEY_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,6})\.[0-9]{2}\Z")
_TOTAL_PATTERN = re.compile(r"(?:0|[1-9][0-9]{0,8})\.[0-9]{2}\Z")
_NUMBER_PATTERN = re.compile(r"ORC-[0-9]{6,}\Z")

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


def _exact_keys(value: object, keys: set[str]) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid quote snapshot structure")
    return value


def _required_text(value: object, maximum: int) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > maximum:
        raise ValueError("invalid quote snapshot text")
    return value


def _nullable_text(value: object, maximum: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, maximum)


def _snapshot_total(value: object) -> Decimal:
    if not isinstance(value, str) or _TOTAL_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid quote snapshot total")
    parsed = Decimal(value)
    if parsed < 0 or parsed > MAX_MONEY:
        raise ValueError("invalid quote snapshot total")
    return parsed


def validate_snapshot(value: object) -> QuoteSnapshot:
    snapshot = _exact_keys(
        value,
        {"schema_version", "quote", "business", "client", "items", "subtotal", "total", "notes"},
    )
    if type(snapshot["schema_version"]) is not int or snapshot["schema_version"] != 1:
        raise ValueError("invalid quote snapshot version")

    quote = _exact_keys(
        snapshot["quote"],
        {"id", "number", "sent_at", "currency", "valid_until", "business_timezone"},
    )
    try:
        UUID(_required_text(quote["id"], 36))
        sent_at = datetime.fromisoformat(
            _required_text(quote["sent_at"], 32).replace("Z", "+00:00")
        )
        date.fromisoformat(_required_text(quote["valid_until"], 10))
        ZoneInfo(_required_text(quote["business_timezone"], 64))
    except (ValueError, TypeError, ZoneInfoNotFoundError) as error:
        raise ValueError("invalid quote snapshot quote") from error
    if (
        _NUMBER_PATTERN.fullmatch(_required_text(quote["number"], 32)) is None
        or quote["currency"] != "BRL"
        or sent_at.tzinfo is None
    ):
        raise ValueError("invalid quote snapshot quote")

    business = _exact_keys(
        snapshot["business"], {"trade_name", "phone", "email", "address", "logo"}
    )
    _required_text(business["trade_name"], 160)
    _required_text(business["phone"], 32)
    _required_text(business["email"], 254)
    _required_text(business["address"], 500)
    if business["logo"] is not None:
        raise ValueError("invalid quote snapshot logo")

    client = _exact_keys(snapshot["client"], {"id", "name", "phone", "email", "address"})
    try:
        UUID(_required_text(client["id"], 36))
    except ValueError as error:
        raise ValueError("invalid quote snapshot client") from error
    _required_text(client["name"], 160)
    _nullable_text(client["phone"], 32)
    _nullable_text(client["email"], 254)
    _nullable_text(client["address"], 500)

    raw_items = snapshot["items"]
    if not isinstance(raw_items, list) or not 1 <= len(raw_items) <= 100:
        raise ValueError("invalid quote snapshot items")
    line_totals: list[Decimal] = []
    for expected_position, raw_item in enumerate(raw_items, start=1):
        item = _exact_keys(
            raw_item,
            {"id", "position", "description", "quantity", "unit_price", "line_total"},
        )
        try:
            UUID(_required_text(item["id"], 36))
            quantity = parse_quantity(item["quantity"])
            unit_price = parse_money(item["unit_price"])
            line_total = _snapshot_total(item["line_total"])
        except ValueError as error:
            raise ValueError("invalid quote snapshot item") from error
        if type(item["position"]) is not int or item["position"] != expected_position:
            raise ValueError("invalid quote snapshot item position")
        _required_text(item["description"], 500)
        if calculate_line_total(quantity, unit_price) != line_total:
            raise ValueError("invalid quote snapshot line total")
        line_totals.append(line_total)

    subtotal = _snapshot_total(snapshot["subtotal"])
    total = _snapshot_total(snapshot["total"])
    if sum(line_totals, start=Decimal("0.00")) != subtotal or subtotal != total:
        raise ValueError("invalid quote snapshot totals")
    _nullable_text(snapshot["notes"], 5000)
    return cast(QuoteSnapshot, snapshot)
