"""Tests for challenger evaluation scaffold."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_challenger_eval import (
    build_challenger_report,
    evaluate_promotion_gate,
    format_challenger_report_text,
    resolve_champion_variant,
    run_challenger_evaluation,
)


def _seed_run(run_dir: Path, *, variant_suffix: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    dates = pd.date_range("2020-01-01", periods=260, freq="B")
    rets = pd.Series(0.0005, index=dates)
    rets.to_frame("strategy_return").to_csv(run_dir / "strategy_daily_returns.csv")
    (run_dir / "integrity_report.json").write_text(
        json.dumps({"status": "PASS", "errors": []}),
        encoding="utf-8",
    )


def test_promotion_gate_always_blocked() -> None:
    gate = evaluate_promotion_gate(
        champion={"integrity_pass": True, "metrics": {"sharpe_0rf": 1.0}, "n_days": 300},
        m1={"metrics": {"sharpe_0rf": 0.5}},
    )
    assert gate["status"] == "BLOCKED"
    assert "auto_promotion_disabled" in gate["blocked_reasons"]


def test_build_report_with_validation_runs(tmp_path: Path) -> None:
    root = tmp_path
    out_dir = root / "model_output_test"
    out_dir.mkdir()
    (out_dir / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R3_w075_q065_noexit", "integrity_status": "PASS"}),
        encoding="utf-8",
    )
    _seed_run(root / "validation_runs" / "20260101_R3_w075_q065_noexit", variant_suffix="R3")
    _seed_run(root / "validation_runs" / "20260101_M1_MOM_BLEND_MATCHED_CONTROLS", variant_suffix="M1")
    report = build_challenger_report(root, out_dir)
    assert report["variants_compared"] >= 1
    assert report["promotion_gate"]["status"] == "BLOCKED"
    text = format_challenger_report_text(report)
    assert "CHAMPION" in text or "R3" in text


def test_resolve_champion_variant_always_locked(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    (out / "latest_validated_run.json").write_text(
        json.dumps(
            {
                "variant_id": "R5_rank_only_train5",
                "run_id": "20260531T171255442Z_R5_rank_only_train5_x",
            }
        ),
        encoding="utf-8",
    )
    assert resolve_champion_variant(out, root=tmp_path) == AUTHORITATIVE_CHAMPION


def test_report_champion_is_locked_not_r5(tmp_path: Path) -> None:
    root = tmp_path
    out_dir = root / "model_output_sp500_pit_t212"
    out_dir.mkdir(parents=True)
    (out_dir / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R5_rank_only_train5", "run_id": "R5_x"}),
        encoding="utf-8",
    )
    rets = __import__("pandas").date_range("2020-01-01", periods=260, freq="B")
    series = __import__("pandas").Series(0.001, index=rets)
    series.to_frame("strategy_return").to_csv(out_dir / "strategy_daily_returns.csv")
    _seed_run(root / "validation_runs" / "20260101_R3_w075_q065_noexit", variant_suffix="R3")
    report = build_challenger_report(root, out_dir)
    assert report["champion_variant_id"] == AUTHORITATIVE_CHAMPION
    assert not any(e.get("is_champion") and "R5" in str(e.get("variant_id")) for e in report.get("entries") or [])


def test_run_challenger_evaluation(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    (out_dir / "latest_validated_run.json").write_text(
        json.dumps({"variant_id": "R3_w075_q065_noexit"}),
        encoding="utf-8",
    )
    _seed_run(tmp_path / "validation_runs" / "x_R3_w075_q065_noexit", variant_suffix="R3")
    summary = run_challenger_evaluation(tmp_path, out_dir)
    assert (out_dir / "challenger_report.json").is_file()
    assert summary["promotion_status"] == "BLOCKED"
