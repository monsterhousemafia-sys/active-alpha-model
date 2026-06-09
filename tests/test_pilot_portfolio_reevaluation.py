"""Live portfolio re-evaluation v2 — champion CSV + US session."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analytics.pilot_investment_plan import build_investment_plan
from analytics.pilot_portfolio_reevaluation import (
    effective_interval_minutes,
    evaluate_live_portfolio_vs_champion,
    load_champion_portfolio_model,
    load_policy,
    run_periodic_reevaluation,
    should_run_periodic_reevaluation,
)


def _seed_model(root: Path) -> None:
    (root / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    rows = []
    for i, (sym, tw, rs, al) in enumerate(
        [
            ("SPY", 0.0, 0.0, 0.0),
            ("INTC", 0.08, 0.94, 0.6),
            ("WDC", 0.07, 0.88, 0.5),
        ]
    ):
        rows.append(
            {
                "signal_date": "2026-06-01",
                "ticker": sym,
                "target_weight": tw,
                "mu_hat": al * 0.05,
                "alpha_lcb": al,
                "rank_score": rs,
                "selection_score": rs,
                "eligible": sym != "SPY",
                "risk_on": True,
                "target_exposure": 1.0,
                "portfolio_exposure": 0.7,
                "portfolio_beta": 1.2,
            }
        )
    pd.DataFrame(rows).to_csv(
        root / "model_output_sp500_pit_t212/latest_target_portfolio.csv",
        index=False,
    )


def test_load_champion_model(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    m = load_champion_portfolio_model(tmp_path)
    assert m["status"] == "OK"
    assert m["meta"]["risk_on"] is True
    assert "INTC" in m["symbols"]


def test_reeval_prefers_r3_t212_cash_over_stale_broker(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "cash_eur": 674.66,
                "investable_eur": 640.93,
                "cash_breakdown": {
                    "available_to_trade_eur": 674.66,
                    "planning_cash_eur": 674.66,
                },
                "positions_count": 0,
            }
        ),
        encoding="utf-8",
    )
    plan = build_investment_plan(tmp_path, 674.66, investable_eur=640.93, budget_source="r3_t212_investable")
    broker = {
        "cash_eur": 674.66,
        "r3_planning_cash_eur": 674.66,
        "r3_investable_eur": 640.93,
        "cash_breakdown": {"total_account_value_eur": 674.66, "planning_cash_eur": 674.66},
        "positions": [],
        "source": "t212_live_sync",
    }
    report = evaluate_live_portfolio_vs_champion(
        tmp_path,
        broker=broker,
        plan=plan,
        champion_guard={"champion_ok": True, "signals_ok": True},
    )
    assert report["status"] == "OK"
    assert float(report["account_eur"]) == 674.66
    assert float(report["deployable_eur"]) >= 600.0


def test_detects_underweight_buy(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    plan = build_investment_plan(tmp_path, 400.0)
    broker = {
        "cash_eur": 350.0,
        "cash_breakdown": {"total_account_value_eur": 500.0},
        "positions": [
            {
                "instrument": {"ticker": "INTCl_EQ"},
                "walletImpact": {"currentValue": 50.0},
            }
        ],
    }
    with patch(
        "analytics.pilot_portfolio_reevaluation._us_session_open",
        return_value=True,
    ):
        report = evaluate_live_portfolio_vs_champion(
            tmp_path,
            broker=broker,
            plan=plan,
            quote_snapshot={
                "generated_at_utc": "2099-01-01T12:00:00+00:00",
                "freshness": {"status": "FRESH", "calculation_allowed": True, "age_seconds": 10},
                "executable_prices_eur": {"INTC": 22.0, "WDC": 45.0, "SPY": 400.0},
            },
            champion_guard={"champion_ok": True, "signals_ok": True},
        )
    assert report["status"] == "OK"
    assert report["risk_on"] is True
    assert report.get("exposure_check")
    assert report["trade_required"] is True
    assert any(a["symbol"] == "INTC" for a in report["recommended_actions"])


def test_risk_off_blocks_buys(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    path = tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv"
    df = pd.read_csv(path)
    df["risk_on"] = False
    df["target_exposure"] = 0.3
    df.to_csv(path, index=False)
    plan = build_investment_plan(tmp_path, 400.0)
    broker = {
        "cash_eur": 300.0,
        "cash_breakdown": {"total_account_value_eur": 500.0},
        "positions": [],
    }
    report = evaluate_live_portfolio_vs_champion(
        tmp_path,
        broker=broker,
        plan=plan,
        champion_guard={"champion_ok": True, "signals_ok": True},
    )
    assert report["risk_on"] is False
    assert not any(a.get("action_code") == "NACHKAUF" for a in report["recommended_actions"])


def test_stale_signals_watch_only(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    plan = build_investment_plan(tmp_path, 400.0)
    broker = {"cash_eur": 400.0, "cash_breakdown": {"total_account_value_eur": 400.0}, "positions": []}
    report = evaluate_live_portfolio_vs_champion(
        tmp_path,
        broker=broker,
        plan=plan,
        champion_guard={"champion_ok": True, "signals_ok": False},
    )
    assert report["urgency"] == "WATCH_ONLY"
    assert report["trade_required"] is False


def test_us_open_shorter_interval(tmp_path: Path) -> None:
    pol = load_policy(tmp_path)
    with patch("analytics.pilot_portfolio_reevaluation._us_session_open", return_value=True):
        assert effective_interval_minutes(pol) == 5
    with patch("analytics.pilot_portfolio_reevaluation._us_session_open", return_value=False):
        assert effective_interval_minutes(pol) == 30


def test_periodic_throttle(tmp_path: Path) -> None:
    _seed_model(tmp_path)
    broker = {"cash_eur": 400.0, "cash_breakdown": {"total_account_value_eur": 400.0}, "positions": []}
    r1 = run_periodic_reevaluation(
        tmp_path,
        broker=broker,
        champion_guard={"champion_ok": True, "signals_ok": True},
        force=True,
    )
    assert r1["status"] == "OK"
    assert not should_run_periodic_reevaluation(tmp_path, force=False)
    cached = json.loads((tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").read_text())
    assert cached.get("schema_version") == 2
