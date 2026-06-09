"""P1 integrity foundation gate tests (master prompt §10.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aa_dashboard_result import load_result_context, scale_portfolio_rows
from aa_integrity import IntegrityResult, backfill_integrity_status_json, validate_backtest_integrity
from aa_model_status import build_model_status, format_model_status_block, write_model_status
from aa_run_provenance import publish_validated_run


def test_p1_integrity_status_schema(tmp_path: Path):
    rbs = pd.date_range("2020-01-01", periods=6, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4]])
    strat_idx = rbs[1:5]
    strategy_returns = pd.Series([0.001, -0.001, 0.002, 0.0], index=strat_idx)
    result = validate_backtest_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=rebalance_dates[:-1],
    )
    from aa_integrity import write_integrity_reports

    write_integrity_reports(tmp_path, result)
    payload = json.loads((tmp_path / "integrity_status.json").read_text(encoding="utf-8"))
    for key in ("status", "checked_at_utc", "calendar_complete", "rebalance_complete", "returns_complete", "errors"):
        assert key in payload
    assert "matched_controls_calendar_complete" in payload


def test_p1_backfill_integrity_status(tmp_path: Path):
    report = {
        "status": "PASS",
        "errors": [],
        "expected_rebalance_periods": 2,
        "simulated_rebalance_periods": 2,
    }
    (tmp_path / "integrity_report.json").write_text(json.dumps(report), encoding="utf-8")
    path = backfill_integrity_status_json(tmp_path)
    assert path is not None
    assert (tmp_path / "integrity_status.json").is_file()


def test_p1_model_status_master_fields(tmp_path: Path):
    (tmp_path.parent / "DEVELOPMENT_PIPELINE.json").write_text(
        json.dumps({"current_phase": "P1_INTEGRITY_FOUNDATION"}),
        encoding="utf-8",
    )
    out = tmp_path / "model"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        '{"integrity_status":"PASS","variant_id":"R3_w075_q065_noexit","published_at_utc":"2026-05-30T12:00:00+00:00"}',
        encoding="utf-8",
    )
    status = build_model_status(out)
    for key in (
        "current_pipeline_phase",
        "failsafe_status",
        "auto_research_status",
        "auto_promotion_status",
        "realtime_behavioral_status",
    ):
        assert key in status
    assert status["auto_promotion_status"] == "DISABLED"
    text = format_model_status_block(status)
    assert "Pipeline-Phase" in text
    assert "Fail-Safe" in text


def test_p1_partial_exposure_65_percent_cash():
    df = pd.DataFrame({"ticker": ["AAA"], "target_weight": [0.65], "sector": ["Tech"]})
    _, invested, cash = scale_portfolio_rows(df, 1000.0)
    assert invested == pytest.approx(650.0, abs=0.01)
    assert cash == pytest.approx(350.0, abs=0.01)


def test_p1_invalid_run_does_not_overwrite_pointer(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    good = out / "runs" / "good"
    good.mkdir(parents=True)
    (good / "strategy_daily_returns.csv").write_text("date,strategy_return\n2020-01-02,0.001\n", encoding="utf-8")
    (good / "backtest_report.txt").write_text("x" * 100, encoding="utf-8")
    (good / "latest_target_portfolio.csv").write_text("ticker,target_weight\nA,1\n", encoding="utf-8")
    ok = IntegrityResult(status="PASS", run_id="good")
    from aa_integrity import write_integrity_reports

    write_integrity_reports(good, ok)
    publish_validated_run(out, good, "good", integrity=ok, variant_id="R3")
    bad = out / "runs" / "bad"
    bad.mkdir()
    (bad / "strategy_daily_returns.csv").write_text("date,strategy_return\n", encoding="utf-8")
    bad_r = IntegrityResult(status="INVALID", errors=["fail"], run_id="bad")
    write_integrity_reports(bad, bad_r)
    publish_validated_run(out, bad, "bad", integrity=bad_r)
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "good"


def test_p1_exe_loader_hides_metrics_when_not_validated(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    (out / "strategy_daily_returns.csv").write_text("date,strategy_return\n2020-01-02,0.001\n", encoding="utf-8")
    (out / "backtest_report.txt").write_text("cagr: 0.99\n" + "x" * 80, encoding="utf-8")
    ctx = load_result_context(out, metrics={"cagr": 0.99})
    assert ctx["analytical_validity"] != "PASS"
    assert "nicht freigegeben" in ctx["metrics_summary"].lower() or "ungültig" in ctx["metrics_summary"].lower()
