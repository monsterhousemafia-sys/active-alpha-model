"""Evolution stage runner — secure ladder + governance."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analytics.evolution_governance import GOVERNANCE_BLOCKED_ACTIONS, kernel_blocks_full_auto
from analytics.evolution_stage_runner import run_evolution_cycle, stage_criteria_progress
from analytics.learning_cycle_audit import resolve_stage


def _write_track(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "control/evolution_track.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/evolution_track.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (root / "control/AI_KERNEL.json").write_text(
        json.dumps(
            {
                "safety": {"auto_execute_real_money": False, "gui_confirm_required": True},
            }
        ),
        encoding="utf-8",
    )


def _ledger_row(**kwargs) -> dict:
    base = {
        "prediction_id": "p1",
        "signal_id": "s1",
        "model_label": "m",
        "variant_id": "v",
        "source_run_id": "LIVE_T212",
        "rebalance_date": pd.Timestamp("2026-06-01"),
        "feature_date": pd.Timestamp("2026-06-01"),
        "signal_date": pd.Timestamp("2026-06-01"),
        "intended_trade_date": pd.Timestamp("2026-06-02"),
        "holding_period_start": pd.Timestamp("2026-06-02"),
        "holding_period_end": pd.Timestamp("2026-06-03"),
        "ticker": "INTC",
        "horizon": 1,
        "rebalance_every": 1,
        "mu_hat": 0.01,
        "alpha_lcb": 0.01,
        "rank_score": 0.5,
        "selection_score": 0.5,
        "target_weight": 0.1,
        "cash_weight": 0.0,
        "target_exposure": 1.0,
        "risk_on": True,
        "selection_mode": "x",
        "gate_mode": "x",
        "data_quality_status": "ok",
        "signal_validity_status": "ok",
        "status": "mature",
        "realized_target": 0.02,
        "prediction_error": -0.01,
        "signed_hit": True,
        "recorded_at_utc": "2026-06-01T00:00:00+00:00",
        "matured_at_utc": "2026-06-03T00:00:00+00:00",
    }
    base.update(kwargs)
    return base


def test_sport_plus_stage_with_live_fills(tmp_path: Path) -> None:
    _write_track(tmp_path)
    out_dir = tmp_path / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    rows = [_ledger_row(prediction_id=f"p{i}", ticker=f"T{i}") for i in range(3)]
    pd.DataFrame(rows).to_parquet(out_dir / "prediction_ledger.parquet", index=False)
    stage = resolve_stage(tmp_path)
    assert stage["stage_id"] == "sport_plus"
    assert "slippage_calibrate" in stage["auto_actions_allowed"]


def test_rennwagen_actions_always_blocked(tmp_path: Path) -> None:
    _write_track(tmp_path)
    (tmp_path / "control/evolution_track.json").write_text(
        json.dumps(
            {
                "governance": {"evolution_allow_full_auto": True, "max_auto_stage_without_m9": "rennwagen"},
                "stages": [
                    {
                        "id": "rennwagen",
                        "order": 4,
                        "label_de": "Rennwagen",
                        "criteria": {},
                        "auto_actions": list(GOVERNANCE_BLOCKED_ACTIONS),
                    }
                ],
                "safe_auto_limits": {},
            }
        ),
        encoding="utf-8",
    )
    assert kernel_blocks_full_auto(tmp_path)
    cycle = run_evolution_cycle(tmp_path, apply_improvements=True)
    skipped = cycle.get("auto_apply", {}).get("skipped") or []
    blocked = [s for s in skipped if s.get("action") in GOVERNANCE_BLOCKED_ACTIONS]
    assert blocked
    assert all(s.get("blocked") or "governance" in str(s.get("reason", "")).lower() for s in blocked)


def test_stage_progress_shows_gaps(tmp_path: Path) -> None:
    _write_track(tmp_path)
    prog = stage_criteria_progress(tmp_path, {})
    assert prog.get("next_stage_id") == "sport_plus"
    assert prog.get("ready_for_next") is False
    assert any("Live reif" in g for g in prog.get("gaps_de") or [])


def test_evolution_cycle_writes_evidence(tmp_path: Path) -> None:
    _write_track(tmp_path)
    out_dir = tmp_path / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    pd.DataFrame([_ledger_row()]).to_parquet(out_dir / "prediction_ledger.parquet", index=False)
    cycle = run_evolution_cycle(tmp_path)
    assert cycle.get("ok")
    assert (tmp_path / "evidence/evolution_cycle_latest.json").is_file()
