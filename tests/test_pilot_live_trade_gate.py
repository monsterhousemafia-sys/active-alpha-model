from pathlib import Path
from unittest.mock import patch

from analytics.pilot_live_trade_gate import (
    build_live_order_preflight,
    format_confirmation_dialog_text,
)


def test_preflight_blocks_stale_quotes_in_us_session(tmp_path: Path) -> None:
    broker = {"cash_eur": 500.0, "cash_breakdown": {}}
    plan = {"primary_action": {"symbol": "INTC", "target_eur": 40.0}}
    stale_snap = {
        "executable_prices_eur": {"INTC": 25.0},
        "freshness": {"status": "STALE", "reason": "too old", "calculation_allowed": False},
        "_quote_gate_ok": False,
        "_us_session_open": True,
    }
    with patch(
        "analytics.pilot_live_trade_gate.fetch_live_quotes_fail_closed",
        return_value=(stale_snap, [{"code": "QUOTES_NOT_FRESH", "message_de": "stale"}]),
    ):
        with patch(
            "analytics.pilot_live_trade_gate.fetch_live_fx_fail_closed",
            return_value=({"ok": True, "usd_per_eur": 1.08}, []),
        ):
            with patch(
                "analytics.pilot_live_trade_gate.run_fresh_portfolio_reevaluation",
                return_value={
                    "quote_fresh": False,
                    "us_session_open": True,
                    "trade_required": False,
                    "summary_de": "stale",
                    "rows": [],
                },
            ):
                pf = build_live_order_preflight(
                    tmp_path,
                    symbol="INTC",
                    target_notional_eur=40.0,
                    broker=broker,
                    plan=plan,
                    champion_guard={"champion_ok": True, "signals_ok": True},
                )
    assert pf["ok"] is False
    assert any(b["code"] == "QUOTES_NOT_FRESH" for b in pf["blocks"])


def test_confirmation_text_lists_factors() -> None:
    text = format_confirmation_dialog_text(
        {
            "ok": True,
            "confirmation_lines": ["Line A", "Modell-Begründung:", "  • alpha_lcb: 0.01"],
        }
    )
    assert "Live-Prüfung" in text
    assert "alpha_lcb" in text
