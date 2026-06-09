"""Tests for aa_ops run planning and system status."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from aa_data_freshness import DailyDataReport
from aa_ops import decide_run_plan, has_persisted_analysis, load_cached_run_result
from aa_preflight import PreflightReport
from aa_system_status import SystemStatus, read_system_status, write_system_status


def test_has_persisted_analysis(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    assert not has_persisted_analysis(out)
    from tests.test_integrity import _seed_validated_run

    _seed_validated_run(out)


def test_decide_run_plan_fast_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    out = tmp_path / "model_out"
    out.mkdir()
    pd.DataFrame({"date": ["2026-05-29"], "close": [1.0]}).to_parquet(out / "dummy.parquet", index=False)
    from tests.test_integrity import _seed_validated_run

    _seed_validated_run(out)

    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_FAST_PATH": "1"}
    report = DailyDataReport(
        reference_date=date(2026, 5, 29),
        price_latest=date(2026, 5, 29),
        price_current=True,
        signal_date=date(2026, 5, 29),
        signal_current=True,
        ok=True,
    )
    plan = decide_run_plan(tmp_path, env, data_report=report, preflight=PreflightReport(status="OK"))
    assert plan.mode == "results"


def test_decide_run_plan_analyze_when_stale(tmp_path: Path):
    out = tmp_path / "model_out"
    out.mkdir()
    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_FAST_PATH": "1"}
    report = DailyDataReport(reference_date=date(2026, 5, 29), ok=False, price_current=False)
    plan = decide_run_plan(tmp_path, env, data_report=report, preflight=PreflightReport(status="OK"))
    assert plan.mode == "refresh_analyze"


def test_decide_run_plan_signal_refresh_when_stale_but_valid(tmp_path: Path):
    out = tmp_path / "model_out"
    out.mkdir()
    from tests.test_integrity import _seed_validated_run

    _seed_validated_run(out)
    env = {
        "AA_BACKTEST_OUT_DIR": str(out),
        "AA_FAST_PATH": "1",
        "AA_SIGNAL_REFRESH_ON_STALE_DATA": "1",
    }
    report = DailyDataReport(reference_date=date(2026, 5, 29), ok=False, price_current=False)
    plan = decide_run_plan(tmp_path, env, data_report=report, preflight=PreflightReport(status="OK"))
    assert plan.mode == "refresh_signal"


def test_system_status_roundtrip(tmp_path: Path):
    write_system_status(
        tmp_path,
        SystemStatus(health="OK", phase="results", message="test", price_date="2026-05-29"),
    )
    st = read_system_status(tmp_path)
    assert st.health == "OK"
    assert st.price_date == "2026-05-29"
    raw = json.loads((tmp_path / "system_status.json").read_text(encoding="utf-8"))
    assert raw["phase"] == "results"


def test_load_cached_run_result(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    report = (
        "Configuration\n"
        "-------------\n"
        "top_k: 15\n"
        "Strategy metrics\n"
        "----------------\n"
        "cagr: 0.15\n"
        "sharpe_0rf: 1.2\n"
    )
    from tests.test_integrity import _seed_validated_run

    _seed_validated_run(out)
    (out / "backtest_report.txt").write_text(report, encoding="utf-8")
    env = {"AA_BACKTEST_OUT_DIR": str(out)}
    result = load_cached_run_result(tmp_path, env)
    assert result.success
    assert result.signal_date == "2026-05-29"
    assert result.metrics.get("cagr") == 0.15
    assert result.metrics.get("sharpe_0rf") == 1.2
    assert "top_k" not in result.metrics
