from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from execution.h1_cpu_priority import (
    h1_priority_profile,
    is_h1_yield_to_operator_hours,
)


def test_yield_hours_daytime() -> None:
    noon = datetime(2026, 6, 8, 12, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_h1_yield_to_operator_hours(now=noon) is True
    prof = h1_priority_profile(yield_hours=True)
    assert prof["nice"] >= 10


def test_yield_hours_night() -> None:
    night = datetime(2026, 6, 8, 23, 0, tzinfo=ZoneInfo("Europe/Berlin"))
    assert is_h1_yield_to_operator_hours(now=night) is False
    prof = h1_priority_profile(yield_hours=False)
    assert prof["nice"] < 10
