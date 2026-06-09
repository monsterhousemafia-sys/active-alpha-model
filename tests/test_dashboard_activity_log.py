from __future__ import annotations

from ui.live_trading_dashboard.activity_log import format_activity_line, summarize_refresh


def test_format_activity_line() -> None:
    line = format_activity_line(
        {
            "timestamp_utc": "2026-06-06T10:00:00+00:00",
            "source": "AUTO",
            "category": "Auto-Refresh",
            "action": "Läuft",
            "result": "Konto OK",
            "status": "ERFOLGREICH",
        }
    )
    assert "Auto-Refresh" in line
    assert "Konto OK" in line


def test_summarize_refresh() -> None:
    s = summarize_refresh(
        {
            "traffic": "GELB",
            "broker": {"cash_eur": 100.0},
            "rebalance_status": {"recommendation": "MARK_TO_MARKET_ONLY"},
            "quote_coverage": {"quote_coverage_label_de": "8/14"},
            "day_warnings": {"critical_count": 1},
        }
    )
    assert "100" in s
    assert "8/14" in s
