"""Extended ops and refresh tests."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from aa_data_freshness import DailyDataReport
from aa_ops import decide_run_plan, load_cached_run_result, validate_persisted_analysis
from aa_ops_refresh import run_ops_refresh
from aa_preflight import PreflightReport, run_launcher_preflight
from aa_system_status import health_from_parts


def test_validate_persisted_analysis_rejects_empty_returns(tmp_path: Path):
    from aa_run_provenance import load_validated_run_dir
    from tests.test_integrity import _seed_validated_run

    out = tmp_path / "model"
    run_dir = _seed_validated_run(out)
    empty = "date,strategy_return\n"
    (out / "strategy_daily_returns.csv").write_text(empty, encoding="utf-8")
    run_path = load_validated_run_dir(out) or run_dir
    (run_path / "strategy_daily_returns.csv").write_text(empty, encoding="utf-8")
    ok, reason = validate_persisted_analysis(out, env={"AA_RUN_MODE": "both"})
    assert not ok


def test_load_cached_run_result_invalid(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    (out / "backtest_report.txt").write_text("Strategy metrics\n--------\ncagr: 0.1\n", encoding="utf-8")
    (out / "latest_target_portfolio.csv").write_text("ticker,target_weight\nA,1\n", encoding="utf-8")
    result = load_cached_run_result(tmp_path, {"AA_BACKTEST_OUT_DIR": str(out)})
    assert not result.success


def test_ops_refresh_meta_records_attempt(tmp_path: Path, monkeypatch):
    out = tmp_path / "model_out"
    out.mkdir()
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_AUTO_OPS_REFRESH": "1", "AA_SKIP_DOWNLOAD_IF_CACHED": "1"}
    monkeypatch.setattr("aa_data_freshness.last_expected_market_date", lambda **_: date(2026, 5, 29))
    monkeypatch.setattr("aa_ops_refresh.refresh_price_panel_with_retry", lambda *a, **k: False)
    monkeypatch.setattr("aa_ops_refresh.refresh_universe_if_needed", lambda *a, **k: False)
    run_ops_refresh(tmp_path, env, log=lambda _m: None, force=True, include_signal=False)
    meta = (out / "ops_refresh_meta.json").read_text(encoding="utf-8")
    assert "last_attempt_at_utc" in meta


def test_health_warn_on_ops_lock():
    assert health_from_parts(preflight="OK", data_ok=True, ops_degraded=True) == "WARN"


def test_preflight_blocking_missing_membership(tmp_path: Path):
    env = {"AA_MEMBERSHIP_FILE": str(tmp_path / "missing_membership.csv")}
    report = run_launcher_preflight(tmp_path, env)
    assert report.blocking


def test_decide_run_plan_invalid_analysis(tmp_path: Path):
    out = tmp_path / "model_out"
    out.mkdir()
    (out / "backtest_report.txt").write_text("x" * 100, encoding="utf-8")
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_FAST_PATH": "1"}
    report = DailyDataReport(reference_date=date(2026, 5, 29), ok=True, price_current=True, signal_current=True)
    plan = decide_run_plan(tmp_path, env, data_report=report, preflight=PreflightReport(status="OK"))
    assert plan.mode == "analyze"
