from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.quotes.domain import (
    CalculatedItem,
    build_snapshot,
    calculate_line_total,
    calculate_total,
    current_business_date,
    is_commercially_expired,
    money_string,
    parse_money,
    parse_quantity,
    quantity_string,
    quote_number,
)


def test_money_uses_decimal_half_up_per_line() -> None:
    quantity = parse_quantity("0.005")
    price = parse_money("1.00")
    assert calculate_line_total(quantity, price) == Decimal("0.01")
    assert quantity_string(quantity) == "0.005"
    assert money_string(price) == "1.00"


@pytest.mark.parametrize(
    "value",
    [1, 1.0, "1e0", "NaN", "Infinity", "-1.000", "0", "0.000", "1.0000", "10000"],
)
def test_quantity_rejects_noncanonical_or_out_of_range_values(value: object) -> None:
    with pytest.raises(ValueError):
        parse_quantity(value)


@pytest.mark.parametrize(
    "value",
    [1, 1.0, "1", "1.0", "1.000", "1e0", "NaN", "Infinity", "-1.00", "10000000.00"],
)
def test_money_rejects_noncanonical_or_out_of_range_values(value: object) -> None:
    with pytest.raises(ValueError):
        parse_money(value)


def test_total_sums_rounded_lines_and_enforces_limit() -> None:
    items = [
        CalculatedItem(
            id=UUID(int=1),
            position=1,
            description="A",
            quantity=Decimal("0.005"),
            unit_price=Decimal("1.00"),
            line_total=Decimal("0.01"),
        ),
        CalculatedItem(
            id=UUID(int=2),
            position=2,
            description="B",
            quantity=Decimal("1.000"),
            unit_price=Decimal("0.00"),
            line_total=Decimal("0.00"),
        ),
    ]
    assert calculate_total(items) == Decimal("0.01")


def test_business_date_and_expiry_use_the_current_timezone() -> None:
    now = datetime(2026, 10, 5, 2, 30, tzinfo=UTC)
    assert current_business_date(now, "America/Bahia") == date(2026, 10, 4)
    assert current_business_date(now, "Asia/Tokyo") == date(2026, 10, 5)
    assert is_commercially_expired("SENT", date(2026, 10, 4), date(2026, 10, 5))
    assert not is_commercially_expired("APPROVED", date(2026, 10, 4), date(2026, 10, 5))


def test_snapshot_has_canonical_values_and_no_client_notes() -> None:
    item = CalculatedItem(
        id=UUID(int=2),
        position=1,
        description="Serviço",
        quantity=Decimal("1"),
        unit_price=Decimal("100"),
        line_total=Decimal("100"),
    )
    snapshot = build_snapshot(
        quote_id=UUID(int=1),
        number=123,
        sent_at=datetime(2026, 10, 5, 12, tzinfo=UTC),
        valid_until=date(2026, 10, 20),
        business_timezone="America/Bahia",
        business={
            "trade_name": "Climatech",
            "phone": "phone",
            "email": "business@example.com",
            "address": "address",
        },
        client={
            "id": UUID(int=3),
            "name": "Cliente",
            "phone": "private-phone",
            "email": "private@example.com",
            "address": "private-address",
        },
        items=[item],
        subtotal=Decimal("100"),
        notes=None,
    )
    assert snapshot["schema_version"] == 1
    assert snapshot["quote"]["number"] == "ORC-000123"
    assert snapshot["items"][0]["quantity"] == "1.000"
    assert snapshot["items"][0]["unit_price"] == "100.00"
    assert snapshot["business"]["logo"] is None
    assert set(snapshot["client"]) == {"id", "name", "phone", "email", "address"}
    assert quote_number(1_000_000) == "ORC-1000000"
