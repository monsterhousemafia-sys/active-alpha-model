"""Virtual integration — full day-trading snapshot without network."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analytics.pilot_day_trading_facade import (
    PilotTradingSnapshot,
    refresh_trading_snapshot,
)
from analytics.pilot_day_trading_policy import load_unified_policy, migrate_legacy_policies_to_unified


def _seed_champion_csv(root: Path) -> None:
    (root / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "signal_date": "2026-06-01",
                "ticker": "SPY",
                "target_weight": 0,
                "risk_on": True,
                "target_exposure": 1.0,
                "portfolio_exposure": 0.7,
                "portfolio_beta": 1.2,
                "eligible": False,
                "alpha_lcb": 0,
                "rank_score": 0,
                "mu_hat": 0,
                "selection_score": 0,
            },
            {
                "signal_date": "2026-06-01",
                "ticker": "INTC",
                "target_weight": 0.08,
                "risk_on": True,
                "target_exposure": 1.0,
                "portfolio_exposure": 0.7,
                "portfolio_beta": 1.2,
                "eligible": True,
                "alpha_lcb": 0.6,
                "rank_score": 0.94,
                "mu_hat": 0.03,
                "selection_score": 0.94,
            },
        ]
    ).to_csv(root / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)


def test_unified_policy_loads(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    migrate_legacy_policies_to_unified(tmp_path)
    pol = load_unified_policy(tmp_path)
    assert "reevaluation" in pol
    assert "deferred" in pol
    assert "playbook" in pol
    assert (tmp_path / "control/pilot_day_trading.json").is_file()


def test_virtual_refresh_snapshot_open_session(tmp_path: Path) -> None:
    _seed_champion_csv(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    migrate_legacy_policies_to_unified(tmp_path)
    broker = {
        "cash_eur": 400.0,
        "cash_breakdown": {"total_account_value_eur": 500.0},
        "positions": [],
    }
    plan = {
        "champion_id": "R3_w075_q065_noexit",
        "signal_date": "2026-06-01",
        "investable_eur": 400.0,
        "plan_capital_eur": 400.0,
        "pipeline_synced": True,
        "updated_at_utc": "2026-06-08T12:00:00+00:00",
        "t212_live": {"positions_count": 0, "cash_eur": 400.0},
        "primary_action": {"symbol": "INTC", "target_eur": 40.0},
        "allocations": [
            {"symbol": "INTC", "side": "BUY", "model_weight_pct": 8.0, "alpha_lcb": 0.6, "target_eur": 40.0},
            {"symbol": "AMD", "side": "BUY", "model_weight_pct": 8.0, "target_eur": 35.0},
        ],
    }
    quotes = {
        "freshness": {"status": "FRESH", "calculation_allowed": True, "age_seconds": 5},
        "executable_prices_eur": {"INTC": 22.0},
    }
    guard = {"champion_ok": True, "signals_ok": True}

    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        with patch(
            "execution.confirmed_live.us_equity_deferred_intents.process_deferred_intents_if_due",
            return_value={"executed": 0, "skipped": []},
        ):
            with patch(
                "integrations.trading212.t212_order_readiness.assess_order_readiness",
            ) as mock_ready:
                from integrations.trading212.t212_order_readiness import T212OrderReadiness

                mock_ready.return_value = T212OrderReadiness(
                    ok=True,
                    api_execute_configured=True,
                    api_execute_scope_proven=True,
                    us_session_open=True,
                    cash_eur=400.0,
                    cash_source="test",
                    blockers=[],
                    warnings=[],
                    status_de="ok",
                    session={"open": True},
                )
                snap = refresh_trading_snapshot(
                    tmp_path,
                    broker=broker,
                    plan=plan,
                    quote_snapshot=quotes,
                    champion_guard=guard,
                    force_reevaluation=True,
                    auto_enqueue=False,
                )

    assert isinstance(snap, PilotTradingSnapshot)
    assert snap.playbook.get("status") == "OK"
    assert snap.reevaluation.get("status") == "OK"
    assert (tmp_path / "evidence/pilot_day_trading_snapshot_latest.json").is_file()
    evidence = json.loads(
        (tmp_path / "evidence/pilot_day_trading_snapshot_latest.json").read_text(encoding="utf-8")
    )
    assert evidence["playbook"]["next_action"] in (
        "EXECUTE_NOW",
        "WAIT",
        "ENQUEUE_OPEN",
        "REFRESH",
        "NO_TRADE",
        "EXECUTE_DEFERRED",
    )


def test_virtual_closed_session_enqueue_path(tmp_path: Path) -> None:
    _seed_champion_csv(tmp_path)
    migrate_legacy_policies_to_unified(tmp_path)
    broker = {"cash_eur": 400.0, "cash_breakdown": {"total_account_value_eur": 500.0}, "positions": []}
    plan = {
        "primary_action": {"symbol": "INTC", "target_eur": 40.0},
        "investable_eur": 400.0,
        "plan_capital_eur": 400.0,
        "pipeline_synced": True,
        "updated_at_utc": "2026-06-08T12:00:00+00:00",
        "t212_live": {"positions_count": 0},
        "allocations": [
            {"symbol": "INTC", "side": "BUY", "model_weight_pct": 8.0, "alpha_lcb": 0.6, "target_eur": 40.0},
            {"symbol": "MU", "side": "BUY", "target_eur": 30.0},
        ],
        "signal_date": "2026-06-01",
    }
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": False, "phase": "CLOSED"},
    ):
        with patch(
            "execution.confirmed_live.us_equity_deferred_intents.process_deferred_intents_if_due",
            return_value={"executed": 0},
        ):
            with patch(
                "integrations.trading212.t212_order_readiness.assess_order_readiness",
            ) as mock_ready:
                from integrations.trading212.t212_order_readiness import T212OrderReadiness

                mock_ready.return_value = T212OrderReadiness(
                    ok=False,
                    api_execute_configured=True,
                    api_execute_scope_proven=True,
                    us_session_open=False,
                    cash_eur=400.0,
                    cash_source="test",
                    blockers=["US_REGULAR_SESSION_CLOSED"],
                    warnings=[],
                    status_de="closed",
                    session={"open": False},
                )
                snap = refresh_trading_snapshot(
                    tmp_path,
                    broker=broker,
                    plan=plan,
                    champion_guard={"champion_ok": True, "signals_ok": True},
                    force_reevaluation=True,
                )
    assert snap.playbook.get("next_action") in ("ENQUEUE_OPEN", "WAIT", "NO_TRADE")
