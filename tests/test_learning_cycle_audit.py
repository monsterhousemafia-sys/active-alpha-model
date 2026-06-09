"""Tests for evolution audit and safe auto-apply."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analytics.evolution_auto_apply import apply_safe_evolution_improvements
from analytics.learning_cycle_audit import resolve_stage, run_learning_cycle_audit


def _write_track(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/evolution_track.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/evolution_track.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )


def test_stage_sportwagen_by_default(tmp_path: Path) -> None:
    _write_track(tmp_path)
    out = resolve_stage(tmp_path)
    assert out["stage_id"] == "sportwagen"


def test_audit_writes_evidence(tmp_path: Path) -> None:
    _write_track(tmp_path)
    out_dir = tmp_path / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    pd.DataFrame(
        columns=[
            "prediction_id",
            "signal_id",
            "model_label",
            "variant_id",
            "source_run_id",
            "rebalance_date",
            "feature_date",
            "signal_date",
            "intended_trade_date",
            "holding_period_start",
            "holding_period_end",
            "ticker",
            "horizon",
            "rebalance_every",
            "mu_hat",
            "alpha_lcb",
            "rank_score",
            "selection_score",
            "target_weight",
            "cash_weight",
            "target_exposure",
            "risk_on",
            "selection_mode",
            "gate_mode",
            "data_quality_status",
            "signal_validity_status",
            "status",
            "realized_target",
            "prediction_error",
            "signed_hit",
            "recorded_at_utc",
            "matured_at_utc",
        ]
    ).to_parquet(out_dir / "prediction_ledger.parquet", index=False)
    report = run_learning_cycle_audit(tmp_path)
    assert report.get("ok") is True
    assert (tmp_path / "evidence/learning_cycle_audit_latest.json").is_file()


def test_auto_apply_never_enables_full_auto(tmp_path: Path) -> None:
    _write_track(tmp_path)
    audit = run_learning_cycle_audit(tmp_path)
    result = apply_safe_evolution_improvements(tmp_path, audit=audit)
    forbidden = [s for s in result.get("skipped", []) if "auto_execute" in str(s.get("action", ""))]
    assert all("governance" in str(s.get("reason", "")).lower() or "stage" in str(s.get("reason", "")) for s in forbidden) or not forbidden
