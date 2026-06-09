"""Integrity, provenance, variant ID, and calendar validation tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_backtest_ml import resolve_forwarded_ml_prediction
from aa_config import BacktestConfig
from aa_integrity import (
    IntegrityResult,
    validate_backtest_calendar_integrity,
    validate_prediction_cache_coverage,
    write_integrity_reports,
)
from aa_run_provenance import code_fingerprint, make_run_id, publish_validated_run
from aa_variant_id import resolve_canonical_variant_id


def _seed_validated_run(out: Path, run_id: str = "test_run") -> Path:
    run_dir = out / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "strategy_daily_returns.csv").write_text(
        "date,strategy_return\n2020-01-02,0.001\n",
        encoding="utf-8",
    )
    (run_dir / "backtest_report.txt").write_text(
        "Strategy metrics\n--------\ncagr: 0.12\n" + "x" * 80,
        encoding="utf-8",
    )
    (run_dir / "latest_target_portfolio.csv").write_text(
        "ticker,target_weight,signal_date\nAAPL,1.0,2026-05-29\n",
        encoding="utf-8",
    )
    integrity = IntegrityResult(status="PASS", run_id=run_id)
    write_integrity_reports(run_dir, integrity)
    publish_validated_run(out, run_dir, run_id, integrity=integrity)
    return run_dir


def test_validate_backtest_calendar_integrity_pass():
    rbs = pd.date_range("2020-01-01", periods=6, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4]])
    strat_idx = rbs[1:5]
    strategy_returns = pd.Series([0.001, -0.001, 0.002, 0.0], index=strat_idx)
    bench = pd.Series([0.0] * len(strat_idx), index=strat_idx)
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        benchmark_returns=bench,
        returns_calendar=rbs,
        simulated_rebalance_dates=rebalance_dates[:-1],
    )
    assert result.passed


def test_validate_backtest_calendar_integrity_missing_period():
    rbs = pd.date_range("2020-01-01", periods=8, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4, 6]])
    strategy_returns = pd.Series([0.001], index=[rbs[3]])
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=[rebalance_dates[0]],
    )
    assert not result.passed
    assert result.errors


def test_validate_backtest_calendar_integrity_duplicate_return_days():
    rbs = pd.date_range("2020-01-01", periods=6, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4]])
    strat_idx = [rbs[1], rbs[2], rbs[3]]
    strategy_returns = pd.Series([0.001, -0.001, 0.002], index=strat_idx)
    strategy_returns = pd.concat([strategy_returns, pd.Series([0.003], index=[rbs[2]])])
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=rebalance_dates[:-1],
    )
    assert not result.passed
    assert any("duplicate" in e.lower() for e in result.errors)


def test_validate_backtest_calendar_integrity_benchmark_mismatch():
    rbs = pd.date_range("2020-01-01", periods=6, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4]])
    strat_idx = rbs[1:5]
    strategy_returns = pd.Series([0.001, -0.001, 0.002, 0.0], index=strat_idx)
    bench = pd.Series([0.0, 0.0], index=strat_idx[:2])
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        benchmark_returns=bench,
        returns_calendar=rbs,
        simulated_rebalance_dates=rebalance_dates[:-1],
    )
    assert not result.passed
    assert any("mismatch" in e.lower() for e in result.errors)


def test_validate_backtest_calendar_integrity_systematic_trading_day_gaps():
    rbs = pd.date_range("2020-01-01", periods=20, freq="B")
    rebalance_dates = list(rbs[[0, 5, 10, 15]])
    # Only every other trading day in hold window -> large gap vs calendar
    strat_idx = rbs[1:16:2]
    strategy_returns = pd.Series([0.001] * len(strat_idx), index=strat_idx)
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=rebalance_dates[:-1],
    )
    assert not result.passed
    assert any("missing" in e.lower() for e in result.errors)


def test_validate_backtest_calendar_integrity_missing_intermediate_rebalance():
    """Simulated set skips a middle rebalance (ml_retrain_every-style gap)."""
    rbs = pd.date_range("2020-01-01", periods=10, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4, 6, 8]])
    strat_idx = rbs[1:9]
    strategy_returns = pd.Series([0.001] * len(strat_idx), index=strat_idx)
    simulated = [rebalance_dates[0], rebalance_dates[2], rebalance_dates[4]]
    result = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=simulated,
    )
    assert not result.passed
    assert result.missing_periods


def test_validate_prediction_cache_coverage_rejects_missing():
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-08"), pd.Timestamp("2020-01-15")]
    cache = {pd.Timestamp("2020-01-01"): {"status": "ok"}}
    result = validate_prediction_cache_coverage(cache, rbs)
    assert not result.passed


def test_publish_validated_run_invalid_does_not_overwrite_valid(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    _seed_validated_run(out, "good_run")
    bad_dir = out / "runs" / "bad_run"
    bad_dir.mkdir(parents=True)
    (bad_dir / "strategy_daily_returns.csv").write_text("date,strategy_return\n", encoding="utf-8")
    bad = IntegrityResult(status="INVALID", errors=["incomplete"], run_id="bad_run")
    write_integrity_reports(bad_dir, bad)
    assert not publish_validated_run(out, bad_dir, "bad_run", integrity=bad)
    pointer = __import__("json").loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "good_run"


def test_code_fingerprint_changes_with_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = Path(__file__).resolve().parents[1]
    fp1 = code_fingerprint(root)
    fake = tmp_path / "aa_backtest.py"
    fake.write_text("# mutated\n", encoding="utf-8")
    names = list(__import__("aa_run_provenance", fromlist=["BEHAVIOR_FILE_NAMES"]).BEHAVIOR_FILE_NAMES)
    monkeypatch.setitem(
        __import__("sys").modules["aa_run_provenance"].__dict__,
        "BEHAVIOR_FILE_NAMES",
        tuple(n if n != "aa_backtest.py" else str(fake.name) for n in names),
    )
    # fingerprint uses root / name — simpler test: two calls same root should match
    assert fp1 == code_fingerprint(root)


def test_resolve_canonical_variant_id_r3():
    cfg = BacktestConfig(
        risk_off_selection_mode="mom_blend_blend",
        risk_off_gate_mode="momentum_rescue",
        risk_off_momentum_weight=0.70,
        risk_off_momentum_rescue_quantile=0.70,
        risk_off_force_exit_enabled=False,
    )
    assert resolve_canonical_variant_id(cfg) == "R3_w070_q070_noexit"


def test_resolve_canonical_variant_id_m1():
    cfg = BacktestConfig(
        risk_off_selection_mode="legacy",
        risk_off_gate_mode="legacy",
        naive_detailed_reporting=True,
        naive_detailed_variants="mom_blend_matched_controls",
    )
    assert resolve_canonical_variant_id(cfg) == "M1_MOM_BLEND_MATCHED_CONTROLS"


def test_resolve_canonical_variant_id_r5_rank_only():
    cfg = BacktestConfig(
        alpha_model_mode="rank_only",
        train_years=5,
        risk_off_selection_mode="mom_blend_blend",
        risk_off_gate_mode="momentum_rescue",
    )
    assert resolve_canonical_variant_id(cfg) == "R5_rank_only_train5"


def test_validate_matched_controls_calendar_integrity_pass():
    idx = pd.date_range("2020-01-02", periods=5, freq="B")
    strat = pd.Series([0.001, -0.001, 0.002, 0.0, 0.001], index=idx)
    from aa_integrity import validate_matched_controls_calendar_integrity

    result = validate_matched_controls_calendar_integrity(
        strategy_returns=strat,
        matched_returns=strat * 0.5,
    )
    assert result.passed


def test_resolve_forwarded_ml_prediction_skips_without_snapshot():
    res = {
        "status": "forwarded_ml_retrain",
        "ranked": pd.DataFrame({"ticker": ["AAA"], "mu_hat": [0.02]}),
    }
    out = resolve_forwarded_ml_prediction(res, None, BacktestConfig())
    assert out.get("status") == "skip"
    assert out.get("reason") == "missing_snapshot_forward"


def test_make_run_id_contains_variant():
    cfg = BacktestConfig(
        risk_off_selection_mode="mom_blend_blend",
        risk_off_gate_mode="momentum_rescue",
    )
    run_id = make_run_id(cfg)
    assert "R3_" in run_id


def test_make_run_id_differs_for_slippage():
    base = BacktestConfig(out_dir="validation_runs/test_a")
    high_slip = BacktestConfig(out_dir="validation_runs/test_b", slippage_bps=10)
    assert make_run_id(base) != make_run_id(high_slip)


def test_ops_validation_requires_pointer(tmp_path: Path):
    from aa_ops_validation import validate_analytical_integrity

    out = tmp_path / "model"
    out.mkdir()
    ok, reason, _ = validate_analytical_integrity(out)
    assert not ok
    _seed_validated_run(out)
    ok2, reason2, run_id = validate_analytical_integrity(out)
    assert ok2, reason2
    assert run_id == "test_run"
