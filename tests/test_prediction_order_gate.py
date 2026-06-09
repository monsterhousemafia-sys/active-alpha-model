"""Prediction must be ready before any live order."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from analytics.prediction_operations import (
    ensure_prediction_before_orders,
    evaluate_prediction_readiness_for_orders,
)


def _write_ops(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "active_profile": "daily_alpha_h1",
                "profiles": {"daily_alpha_h1": {"variant_key": "DAILY_ALPHA_H1"}},
                "orders": {"require_prediction_ready": True, "auto_run_predict_before_orders": False},
            }
        ),
        encoding="utf-8",
    )


def _write_readiness(root: Path, *, ok: bool = True, signal_date: str | None = None) -> None:
    sig = signal_date or date.today().isoformat()
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/prediction_readiness.json").write_text(
        json.dumps(
            {
                "ok": ok,
                "profile_used": "daily_alpha_h1",
                "signal_date": sig,
                "top_picks": [{"ticker": "INTC", "target_weight": 0.5}],
                "generated_at_utc": "2026-06-05T20:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    import pandas as pd

    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{"ticker": "INTC", "target_weight": 0.5, "signal_date": sig}]).to_csv(
        out / "latest_target_portfolio.csv", index=False
    )
    cache = out / "price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    days = pd.date_range(end=sig, periods=3, freq="D")
    pd.DataFrame({"date": days, "ticker": ["INTC"] * len(days), "close": [100.0, 101.0, 102.0]}).to_parquet(
        cache / "ohlcv_panel.parquet", index=False
    )


def test_blocks_without_readiness(tmp_path: Path) -> None:
    _write_ops(tmp_path)
    gate = evaluate_prediction_readiness_for_orders(tmp_path)
    assert gate["ok"] is False
    assert "PREDICTION_READINESS_MISSING" in gate["blockers"]


def test_ok_when_readiness_and_signal_current(tmp_path: Path) -> None:
    _write_ops(tmp_path)
    _write_readiness(tmp_path)
    gate = evaluate_prediction_readiness_for_orders(tmp_path)
    assert gate["ok"] is True


def test_blocks_stale_signal(tmp_path: Path) -> None:
    _write_ops(tmp_path)
    _write_readiness(tmp_path, signal_date="2020-01-01")
    gate = evaluate_prediction_readiness_for_orders(tmp_path)
    assert gate["ok"] is False
    assert "SIGNAL_NOT_CURRENT" in gate["blockers"]


def test_grant_blocked_without_predict(tmp_path: Path) -> None:
    _write_ops(tmp_path)
    from execution.confirmed_live.gui_execution_confirmation import grant_execution_confirmation

    grant = grant_execution_confirmation(tmp_path, source="TEST")
    assert grant.get("ok") is False
    assert grant.get("error") == "PREDICTION_NOT_READY"


def test_ensure_no_auto_run_when_disabled(tmp_path: Path) -> None:
    _write_ops(tmp_path)
    out = ensure_prediction_before_orders(tmp_path, auto_run=False)
    assert out.get("ok") is False
    assert out.get("auto_run") is False
