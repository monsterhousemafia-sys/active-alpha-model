"""Execution breakdown reporting."""
from __future__ import annotations

from analytics.execution_result_report import attach_execution_report, summarize_execution_breakdown


def test_summarize_breakdown_categories() -> None:
    orders = [
        {"symbol": "A", "side": "BUY"},
        {"symbol": "B", "side": "BUY"},
        {"symbol": "C", "side": "BUY"},
    ]
    results = [
        {"symbol": "A", "ok": True, "sent_to_t212": True},
        {"symbol": "B", "ok": False, "error": "NO_LIMIT_PRICE"},
        {"symbol": "C", "ok": False, "error": "PREFLIGHT", "blocks": []},
    ]
    br = summarize_execution_breakdown(orders, results)
    assert br["executed"] == 1
    assert br["skipped_no_price"] == 1
    assert br["skipped_preflight"] == 1
    assert "ohne Kurs" in br["summary_de"]
    assert "B" in br["skipped_no_price_symbols"]


def test_attach_execution_report_updates_message() -> None:
    out = attach_execution_report(
        {"ok": False, "message_de": "Live-Rebalance", "results": [{"symbol": "X", "ok": True, "sent_to_t212": True}]},
        [{"symbol": "X"}],
    )
    assert "1/1 an T212" in out["message_de"]
