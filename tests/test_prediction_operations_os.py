"""OS integration: prediction profile, EOD switch, variable budget."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from analytics.prediction_operations import (
    active_profile,
    apply_prediction_profile_to_env,
    budget_config,
    eod_switch_due,
    load_prediction_operations,
    resolve_operational_signal_id,
    resolve_planning_basis_eur,
)
from analytics.pilot_investment_plan import build_investment_plan


def _write_ops(root, **overrides) -> None:
    doc = {
        "schema_version": 1,
        "active_profile": "daily_alpha_h1",
        "profiles": {
            "daily_alpha_h1": {"variant_key": "DAILY_ALPHA_H1"},
        },
        "schedule": {"switch_at": "eod", "eod_local_time_cet": "22:15"},
        "budget": {
            "mode": "variable_free_cash",
            "source": "T212_availableToTrade",
            "cash_buffer_pct": 5.0,
            "min_position_eur": 25.0,
            "exclude_symbols": ["LITE"],
        },
    }
    doc.update(overrides)
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps(doc), encoding="utf-8"
    )


def test_active_profile_and_env_overlay(tmp_path) -> None:
    _write_ops(tmp_path)
    assert active_profile(tmp_path) == "daily_alpha_h1"
    assert resolve_operational_signal_id(tmp_path) == "DAILY_ALPHA_H1"
    env = apply_prediction_profile_to_env(tmp_path, {})
    assert env.get("AA_PREDICTION_PROFILE") == "daily_alpha_h1"
    assert env.get("AA_VARIANT_ID") == "DAILY_ALPHA_H1"


def test_budget_config_exclude_lite(tmp_path) -> None:
    _write_ops(tmp_path)
    import pandas as pd

    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "INTC", "target_weight": 0.5, "alpha_lcb": 0.5, "signal_date": "2026-06-01"},
            {"ticker": "LITE", "target_weight": 0.5, "alpha_lcb": 0.4, "signal_date": "2026-06-01"},
        ]
    ).to_csv(tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)

    plan = build_investment_plan(tmp_path, 700.0)
    syms = {a["symbol"] for a in plan["allocations"]}
    assert "LITE" not in syms
    assert plan["budget_mode"] == "variable_free_cash"
    assert plan["investable_eur"] == pytest.approx(665.0)
    assert plan["available_cash_eur"] == 700.0


def test_eod_switch_due_after_cutoff(tmp_path, monkeypatch) -> None:
    _write_ops(tmp_path)
    berlin = ZoneInfo("Europe/Berlin")
    late = datetime(2026, 6, 5, 23, 0, tzinfo=berlin)
    assert eod_switch_due(tmp_path, now=late) is True
    early = datetime(2026, 6, 5, 20, 0, tzinfo=berlin)
    assert eod_switch_due(tmp_path, now=early) is False


def test_champion_guard_allows_prediction_profile_mismatch(tmp_path, monkeypatch) -> None:
    from analytics.champion_runtime_guard import verify_champion_runtime

    _write_ops(tmp_path)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/learning_collection_policy.json").write_text(
        json.dumps({"active_champion_locked": "R3_w075_q065_noexit", "auto_champion_update_enabled": False}),
        encoding="utf-8",
    )
    import pandas as pd

    ref = datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()
    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    pd.DataFrame([{"ticker": "INTC", "target_weight": 0.1, "alpha_lcb": 0.5, "signal_date": ref}]).to_csv(
        tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False
    )
    status = verify_champion_runtime(tmp_path)
    assert status.champion_ok
    assert "CHAMPION_POLICY_CODE_MISMATCH" not in status.blockers
    assert "GOVERNANCE_CHAMPION_DIFFERS_FROM_SIGNAL_PROFILE" in status.warnings


def test_fixed_preview_budget_scales_plan_to_650(tmp_path) -> None:
    _write_ops(
        tmp_path,
        budget={
            "mode": "fixed_preview",
            "planning_capital_eur": 650.0,
            "source": "fixed_preview_650eur",
            "cash_buffer_pct": 0.0,
            "use_full_free_cash": True,
            "min_position_eur": 25.0,
            "exclude_symbols": ["LITE"],
        },
    )
    bcfg = budget_config(tmp_path)
    assert bcfg["mode"] == "fixed_preview"
    assert bcfg["planning_capital_eur"] == 650.0

    basis = resolve_planning_basis_eur(tmp_path, 678.52)
    assert basis["planning_override"] is True
    assert basis["planning_cash_eur"] == 650.0
    assert basis["investable_eur"] == 650.0
    assert basis["live_planning_cash_eur"] == 678.52

    import pandas as pd

    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    pd.DataFrame(
        [
            {"ticker": "INTC", "target_weight": 0.5, "alpha_lcb": 0.5, "signal_date": "2026-06-01"},
            {"ticker": "MU", "target_weight": 0.5, "alpha_lcb": 0.4, "signal_date": "2026-06-01"},
        ]
    ).to_csv(tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)

    plan = build_investment_plan(tmp_path, 650.0, investable_eur=650.0, budget_source="fixed_preview")
    assert plan["investable_eur"] == 650.0
    assert plan["budget_mode"] == "fixed_preview"
    assert sum(a["target_eur"] for a in plan["allocations"]) <= 650.0
