from datetime import UTC, datetime

from tests.conftest import FakeClock


def test_fake_clock_returns_aware_utc_instant() -> None:
    instant = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)
    assert FakeClock(instant).now_utc() is instant
