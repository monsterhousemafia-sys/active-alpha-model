from __future__ import annotations

from analytics.trading_warning_context import (
    dampen_off_hours_warnings,
    finalize_warning_counts,
)


def test_dampen_quote_coverage_off_hours() -> None:
    warnings = [
        {
            "code": "PARTIAL_QUOTE_COVERAGE",
            "severity": "critical",
            "title_de": "Kurs-Abdeckung",
            "detail_de": "4/12",
        },
        {
            "code": "BROKER_SYNC_FAIL",
            "severity": "critical",
            "title_de": "Sync",
            "detail_de": "fail",
        },
    ]
    damped, codes = dampen_off_hours_warnings(warnings, us_open=False)
    assert "PARTIAL_QUOTE_COVERAGE" in codes
    assert damped[0]["severity"] == "warn"
    assert damped[1]["severity"] == "critical"
    counts = finalize_warning_counts(damped, dampened_codes=codes, us_open=False)
    assert counts["critical_count"] == 1
    assert counts["critical_count_raw"] == 2
    assert counts["must_resolve_before_trading"] is True


def test_dampen_all_market_warnings_weekend() -> None:
    warnings = [
        {"code": "PARTIAL_QUOTE_COVERAGE", "severity": "critical", "title_de": "A", "detail_de": "x"},
        {"code": "UNDER_INVESTED_CASH", "severity": "critical", "title_de": "B", "detail_de": "x"},
        {"code": "REBALANCE_DUE_NO_POSITIONS", "severity": "critical", "title_de": "C", "detail_de": "x"},
    ]
    damped, codes = dampen_off_hours_warnings(warnings, us_open=False)
    counts = finalize_warning_counts(damped, dampened_codes=codes, us_open=False)
    assert counts["critical_count"] == 0
    assert counts["must_resolve_before_trading"] is False
    assert len(codes) == 3
