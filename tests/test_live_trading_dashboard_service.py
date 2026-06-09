"""Live trading dashboard service."""
from __future__ import annotations

from pathlib import Path

import pytest

from ui.live_trading_dashboard import service as dash


def test_write_dashboard_txt(tmp_path: Path) -> None:
    snap = {
        "traffic": "GRUEN",
        "sector_status": {"summary_de": "Sektoren: —", "traffic": "GELB"},
        "today_action_de": "NUR MARK",
        "live_enabled": True,
        "rebalance_status": {
            "rebalance_every_trading_days": 5,
            "recorded_trading_days_since_rebalance": 2,
            "days_remaining": 3,
            "recommendation": "MARK_TO_MARKET_ONLY",
            "summary_de": "Test",
        },
        "broker": {"cash_eur": 1000.0},
        "guard": {"champion_ok": True, "signals_ok": True},
        "plan": {"allocations": [{"symbol": "AAPL", "target_eur": 100, "model_weight_pct": 10}]},
        "reevaluation": {"urgency": "LOW", "recommended_actions": []},
        "deferred": {"pending_count": 0, "status_de": "leer"},
        "n_positions": 1,
    }
    path = dash.write_dashboard_txt(tmp_path, snap)
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "Live Trading - Dashboard" in text
    assert "MARK_TO_MARKET_ONLY" in text
    assert "Sector reference" in text


def test_today_action_rebalance_due() -> None:
    assert "REBALANCE" in dash._today_action_de({"recommendation": "REBALANCE_DUE"})


def test_summarize_portfolio_orders() -> None:
    orders = [
        {"symbol": "AAPL", "side": "BUY", "notional_eur": 100.0},
        {"symbol": "MSFT", "side": "SELL", "notional_eur": 50.0},
    ]
    s = dash.summarize_portfolio_orders(orders, signal_date="2026-06-01")
    assert s["has_orders"] is True
    assert s["n_buys"] == 1
    assert s["n_sells"] == 1
    assert s["order_count"] == 2
    assert "AAPL" in "\n".join(s["lines_de"])


def test_portfolio_table_rows() -> None:
    snap = {
        "plan": {
            "allocations": [
                {"symbol": "MSFT", "target_eur": 200.0, "model_weight_pct": 20.0},
            ]
        },
        "reevaluation": {
            "recommended_actions": [
                {
                    "symbol": "MSFT",
                    "current_eur": 50.0,
                    "target_eur": 200.0,
                    "gap_eur": 150.0,
                    "action_de": "Kaufen",
                }
            ]
        },
    }
    rows = dash.portfolio_table_rows(snap)
    assert len(rows) == 1
    assert rows[0]["symbol"] == "MSFT"
    assert rows[0]["gap_eur"] == 150.0
