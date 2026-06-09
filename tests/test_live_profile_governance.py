"""Live profile governance — experimental H1 gate, single truth readiness."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd

from analytics.live_profile_governance import (
    experimental_profile_blockers,
    is_h1_backtest_sealed,
    sync_readiness_with_order_gate,
)
from analytics.prediction_operations import evaluate_prediction_readiness_for_orders


def _write_ops(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "active_profile": "daily_alpha_h1",
                "experimental_profiles": ["daily_alpha_h1"],
                "profiles": {"daily_alpha_h1": {"variant_key": "DAILY_ALPHA_H1"}},
                "safety": {"real_money": True},
                "orders": {"require_prediction_ready": True},
            }
        ),
        encoding="utf-8",
    )


def _write_portfolio(root: Path, signal_date: str) -> None:
    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [{"ticker": "INTC", "target_weight": 0.5, "signal_date": signal_date, "eligible": True}]
    ).to_csv(out / "latest_target_portfolio.csv", index=False)
    cache = out / "price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(end=signal_date, periods=5, freq="B")
    pd.DataFrame({"date": days, "ticker": ["INTC"] * len(days), "Close": [100.0, 101.0, 102.0, 103.0, 104.0]}).to_parquet(
        cache / "ohlcv_panel.parquet", index=False
    )
    meta = {"updated_at_utc": f"{signal_date}T12:00:00+00:00", "source": "test"}
    (cache / "price_cache_meta.json").write_text(json.dumps(meta), encoding="utf-8")


def test_experimental_real_money_blocked_without_seal(tmp_path: Path) -> None:
    sig = date.today().isoformat()
    _write_ops(tmp_path)
    _write_portfolio(tmp_path, sig)
    blocks = experimental_profile_blockers(tmp_path)
    assert "EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY" in blocks
    gate = evaluate_prediction_readiness_for_orders(tmp_path)
    assert not gate.get("ok")
    assert "EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY" in (gate.get("blockers") or [])


def test_sync_readiness_single_truth(tmp_path: Path) -> None:
    sig = date.today().isoformat()
    _write_ops(tmp_path)
    _write_portfolio(tmp_path, sig)
    payload = {
        "ok": True,
        "profile_used": "daily_alpha_h1",
        "top_picks": [{"ticker": "INTC", "target_weight": 0.5}],
        "signal_date": sig,
    }
    synced = sync_readiness_with_order_gate(tmp_path, payload)
    assert synced.get("ok") is False
    assert synced.get("order_gate_ok") is False
    assert "EXPERIMENTAL_PROFILE_UNSEALED_REAL_MONEY" in (synced.get("blockers") or [])


def test_sealed_when_evaluation_pass(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/daily_alpha_h1_evaluation_latest.json").write_text(
        json.dumps({"pass_alpha_objective": True, "pass_daily_cost_stress": True}),
        encoding="utf-8",
    )
    assert is_h1_backtest_sealed(tmp_path)
