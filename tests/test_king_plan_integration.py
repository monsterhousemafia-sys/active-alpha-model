"""König 32B → Modell-Plan Hintergrund-Integration."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.king_plan_integration import (
    apply_king_follow_on_to_plan,
    rebalance_plan_to_t212_holdings,
)
from analytics.r3_closed_loop import resolve_r3_plan_capital_eur


def _base_plan() -> dict:
    return {
        "investable_eur": 100.0,
        "allocations": [
            {"symbol": "STX", "side": "BUY", "model_weight_pct": 50.0, "target_eur": 50.0, "rationale_de": "STX"},
            {"symbol": "AMD", "side": "BUY", "model_weight_pct": 50.0, "target_eur": 50.0, "rationale_de": "AMD"},
        ],
    }


def test_king_boost_reweights_plan(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/king_trading_assist_policy.json").write_text(
        json.dumps(
            {
                "plan_integration": {
                    "enabled": True,
                    "weight_boost_pct_per_priority": 0.2,
                    "max_weight_boost_pct": 2.0,
                }
            }
        ),
        encoding="utf-8",
    )
    plan = _base_plan()
    king = {
        "follow_on_suggestions": [
            {"symbol": "STX", "worth_follow_on": True, "priority": 5.0, "reason_de": "Top Signal"},
        ]
    }
    out, meta = apply_king_follow_on_to_plan(plan, king, tmp_path)
    assert meta["applied"] == 1
    stx = next(a for a in out["allocations"] if a["symbol"] == "STX")
    assert float(stx["model_weight_pct"]) > 50.0
    assert stx.get("king_boost_pct")
    assert float(stx["target_eur"]) > 50.0


def test_plan_capital_uses_total_depot_when_positions(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    broker = {
        "cash_eur": 200.0,
        "cash_breakdown": {
            "planning_cash_eur": 200.0,
            "invested_current_value_eur": 500.0,
            "total_account_value_eur": 700.0,
        },
        "positions": [{"symbol": "STX", "value_eur": 500.0}],
        "positions_count": 1,
    }
    cap = resolve_r3_plan_capital_eur(tmp_path, broker, 200.0)
    assert cap["basis"] == "t212_total_account_live"
    assert cap["plan_capital_eur"] == 665.0
    assert cap["positions_count"] == 1


def test_plan_capital_uses_cash_when_flat_depot(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    broker = {
        "cash_eur": 675.0,
        "cash_breakdown": {"planning_cash_eur": 675.0, "total_account_value_eur": 675.0},
        "positions": [],
        "positions_count": 0,
    }
    cap = resolve_r3_plan_capital_eur(tmp_path, broker, 675.0)
    assert cap["basis"] == "r3_cash_investable_live"
    assert cap["plan_capital_eur"] == 641.25


def test_rebalance_plan_against_t212_holdings(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text(
        json.dumps({"min_trade_eur": 5.0}),
        encoding="utf-8",
    )
    plan = _base_plan()
    broker = {
        "cash_eur": 100.0,
        "positions": [
            {"ticker": "STX", "symbol": "STX", "value_eur": 40.0, "quantity": 1},
        ],
    }
    out, meta = rebalance_plan_to_t212_holdings(plan, broker, tmp_path)
    assert meta.get("ok") is True
    assert out.get("rebalanced_to_t212") is True
    stx = next(a for a in out["allocations"] if a["symbol"] == "STX")
    assert stx["side"] == "BUY"
    assert float(stx["target_eur"]) < 10.0
    assert float(stx["gap_eur_gross"]) == 10.0
    assert float(stx["held_eur"]) == 40.0


def test_holdings_parse_fail_closed(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    plan = _base_plan()
    broker = {
        "cash_eur": 200.0,
        "positions_count": 2,
        "positions": [],
        "credentials_configured": True,
        "connected": True,
    }
    out, meta = rebalance_plan_to_t212_holdings(plan, broker, tmp_path)
    assert meta.get("ok") is False
    assert out.get("holdings_parse_failed") is True
    assert out.get("allocations") == []
