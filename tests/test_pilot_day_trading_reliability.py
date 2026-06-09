"""Day-Trading — Fail-closed, All-in-Schutz, Snapshot-Health."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.pilot_day_trading_facade import refresh_trading_snapshot
from analytics.pilot_day_trading_reliability import (
    assess_plan_trade_safety,
    build_snapshot_health,
    resolve_broker_for_day_trading,
)
from execution.confirmed_live.us_day_trading_coordinator import build_day_trading_playbook


def _plan_multi(investable: float = 400.0) -> dict:
    rows = [
        {"symbol": "STX", "side": "BUY", "target_eur": investable * 0.08},
        {"symbol": "AMD", "side": "BUY", "target_eur": investable * 0.08},
        {"symbol": "MU", "side": "BUY", "target_eur": investable * 0.08},
    ]
    return {
        "investable_eur": investable,
        "plan_capital_eur": investable,
        "pipeline_synced": True,
        "updated_at_utc": "2026-06-08T12:00:00+00:00",
        "t212_live": {"positions_count": 0, "cash_eur": investable},
        "primary_action": {"symbol": "STX", "target_eur": rows[0]["target_eur"]},
        "allocations": rows,
    }


def test_all_in_plan_blocked(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    plan = {
        "investable_eur": 600.0,
        "plan_capital_eur": 600.0,
        "pipeline_synced": True,
        "t212_live": {"positions_count": 0},
        "allocations": [{"symbol": "STX", "side": "BUY", "target_eur": 600.0}],
    }
    safety = assess_plan_trade_safety(tmp_path, plan)
    assert safety.get("blocks_execute") is True
    assert any("All-in" in e for e in safety.get("errors_de") or [])


def test_missing_t212_live_blocks(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    plan = {"investable_eur": 400, "allocations": [{"symbol": "A", "side": "BUY", "target_eur": 40}]}
    safety = assess_plan_trade_safety(tmp_path, plan)
    assert safety.get("blocks_execute") is True


def test_playbook_no_trade_when_plan_unsafe(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text(
        json.dumps({"playbook": {"enabled": True, "execution_window_mode": "full_session"}}),
        encoding="utf-8",
    )
    plan = {
        "investable_eur": 500.0,
        "allocations": [{"symbol": "STX", "side": "BUY", "target_eur": 500.0}],
    }
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        pb = build_day_trading_playbook(
            tmp_path,
            broker={"cash_eur": 500.0, "positions": []},
            plan=plan,
            champion_guard={"champion_ok": True, "signals_ok": True},
            reevaluation={"urgency": "HIGH", "trade_required": True},
        )
    assert pb.get("next_action") == "NO_TRADE"
    assert pb.get("plan_safety", {}).get("blocks_execute") is True


def test_snapshot_health_in_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    plan = _plan_multi()
    broker = {"cash_eur": 400.0, "positions": [], "source": "test"}
    health = build_snapshot_health(
        broker=broker,
        plan=plan,
        reevaluation={"status": "OK", "trade_required": False},
        playbook={"next_action": "WAIT"},
        broker_warnings=[],
        plan_warnings=[],
        step_errors=[],
        root=tmp_path,
    )
    assert health.get("ok") is True


def test_resolve_broker_from_bond(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "connected": True,
                "cash_eur": 675.0,
                "cash_breakdown": {"planning_cash_eur": 675.0},
                "positions": [],
                "positions_count": 0,
            }
        ),
        encoding="utf-8",
    )
    broker, _ = resolve_broker_for_day_trading(tmp_path, None)
    assert broker.get("cash_eur") == 675.0
