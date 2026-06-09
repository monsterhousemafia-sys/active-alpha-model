from __future__ import annotations

from pathlib import Path

from analytics.preview_cockpit import build_preview_cockpit, preview_actions


def test_preview_actions_include_order_desk() -> None:
    ids = {a["id"] for a in preview_actions()}
    assert "order-desk" in ids
    assert "daily-mark" in ids


def test_build_preview_cockpit_from_snap() -> None:
    snap = {
        "traffic": "GRUEN",
        "today_action_de": "NUR MARK",
        "broker": {"cash_eur": 1234.5},
        "n_positions": 3,
        "rebalance_status": {"is_due": False, "summary_de": "OK", "recorded_trading_days_since_rebalance": 2, "rebalance_every_trading_days": 5},
        "public_learning": {"grade": "B"},
        "portfolio_orders": {"summary_de": "Keine Orders", "order_count": 0, "has_orders": False},
        "day_warnings": {"headline_de": "—", "critical_count": 0},
        "deferred": {"status_de": "leer"},
        "guard": {"champion_ok": True, "signals_ok": True},
        "live_enabled": True,
        "trading_readiness": {"orders_allowed": True},
        "sector_status": {"summary_de": "OK"},
    }
    doc = build_preview_cockpit(Path("/tmp"), snap=snap)
    assert doc["traffic_class"] == "ok"
    assert doc["cash_de"] == "1,234.50 €"
    assert doc["n_positions"] == 3
