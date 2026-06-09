"""Phase 5 — quote + wave + walkforward integration (mocked execution)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from execution.confirmed_live.rebalance_wave_planner import plan_rebalance_wave


def _champion_buy_orders(n: int = 13, each_eur: float = 36.15) -> list:
    symbols = (
        "STX", "WDC", "INTC", "CIEN", "GOOGL", "GOOG", "AMD", "CAT", "ON", "MU", "VRT", "TXN", "OXY"
    )
    return [
        {"symbol": sym, "side": "BUY", "notional_eur": each_eur, "limit_price_eur": 80.0}
        for sym in symbols[:n]
    ]


def test_wave_cash_cap_470_on_200_eur() -> None:
    """Remediation plan: 470 € gaps at 200 € cash → factor ≈ 0.43."""
    orders = _champion_buy_orders(13, 470 / 13)
    wave = plan_rebalance_wave(orders, 200.0)
    assert wave["scale_factor"] < 0.45
    assert wave["total_buy_notional_scaled"] <= 200.01


def test_quote_gate_blocks_partial_coverage() -> None:
    from market.champion_quote_gate import require_champion_quote_coverage

    snap = {"executable_prices_eur": {"STX": 90.0, "WDC": 80.0}}
    gate = require_champion_quote_coverage(
        Path("."),
        symbols=["STX", "WDC", "MU"],
        quote_snapshot=snap,
        refresh_if_stale=False,
    )
    assert gate["ok"] is False
    assert "MU" in gate["coverage"]["missing_symbols"]


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for rel in (
        "control",
        "live_pilot/confirmed_execution",
        "paper/p16d",
        "paper/config",
        "evidence",
    ):
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
    (tmp_path / "control" / "pilot_day_trading.json").write_text(
        '{"live_trading":{"enabled":true,"relaxed_order_preflight":true}}',
        encoding="utf-8",
    )
    return tmp_path


def test_execute_live_rebalance_dry_run_pipeline(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Full pipeline: coverage gate → wave → dry-run walkforward (no T212 POST)."""
    monkeypatch.setenv("AA_EXECUTION_DRY_RUN", "1")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "0")

    symbols = [o["symbol"] for o in _champion_buy_orders()]
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    prices = {s: 75.0 + i for i, s in enumerate(symbols)}
    quote_snap = {
        "generated_at_utc": now,
        "executable_prices_eur": prices,
        "price_source_by_symbol": {s: "YAHOO_VALIDATED" for s in symbols},
        "freshness": {"status": "FRESH", "calculation_allowed": True},
        "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE",
    }
    broker = {
        "cash_eur": 492.0,
        "positions": [],
        "credentials_configured": True,
        "cash_breakdown": {"planning_cash_eur": 492.0, "available_to_trade_eur": 492.0},
    }
    reeval = {
        "recommended_actions": [
            {
                "symbol": s,
                "action_code": "NACHKAUF",
                "gap_eur": 36.0,
                "priority_score": 10.0,
                "weight_gap_pct": 5.0,
                "target_eur": 36.0,
                "current_eur": 0.0,
            }
            for s in symbols
        ],
        "quote_fresh": True,
        "us_session_open": True,
    }
    plan = {
        "champion_id": "R3_w075_q065_noexit",
        "signal_date": "2026-06-02",
        "allocations": [{"symbol": s, "target_eur": 36.0} for s in symbols],
        "primary_action": {"symbol": "STX", "target_eur": 36.0},
    }

    dry_submit = {"ok": True, "sent_to_t212": True, "status": "DRY_RUN", "dry_run": True}

    with patch(
        "execution.confirmed_live.live_trading_enablement.ensure_live_trading_enabled",
        return_value={"enabled": True},
    ), patch(
        "analytics.prediction_operations.ensure_prediction_before_orders",
        return_value={"ok": True, "skipped": True},
    ), patch(
        "analytics.live_trading_operations.sync_broker_and_quotes",
        return_value={"broker": broker, "quote_snapshot": quote_snap},
    ), patch(
        "analytics.live_trading_operations.run_champion_signal_update",
        return_value={"ok": True, "skipped": True},
    ), patch(
        "analytics.pilot_investment_plan.build_investment_plan",
        return_value=plan,
    ), patch(
        "analytics.pilot_investment_plan.ensure_plan_symbols_in_scope",
        return_value=True,
    ), patch(
        "analytics.live_trading_operations.build_rebalance_orders",
        return_value=_champion_buy_orders(),
    ), patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True},
    ), patch(
        "integrations.trading212.t212_order_readiness.assess_order_readiness"
    ) as readiness:
        readiness.return_value.ok = True
        readiness.return_value.as_dict = lambda: {"ok": True}
        with patch(
            "execution.confirmed_live.order_auto_scale_submit.submit_scaled_limit_buy",
            return_value=dry_submit,
        ), patch(
            "analytics.live_trading_operations.note_rebalance_completed",
            return_value={"is_due": False},
        ):
            from analytics.live_trading_operations import execute_live_rebalance

            out = execute_live_rebalance(
                root,
                force=True,
                run_signal_before=False,
                source="USER_CLICK",
            )

    assert out.get("quote_coverage", {}).get("ok") is True
    cov = out["quote_coverage"]["coverage"]
    assert cov["covered_count"] == 13
    wave = out.get("execution", {}).get("rebalance_wave") or {}
    assert wave.get("total_buy_notional_scaled", 0) <= 492.0 * 1.02 + 0.01
    br = out.get("execution_breakdown") or out.get("execution", {}).get("execution_breakdown")
    assert br is not None
    assert br.get("executed", 0) >= 1
