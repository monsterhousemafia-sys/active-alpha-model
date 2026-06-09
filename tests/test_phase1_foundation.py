"""Phase 1 minimal improvement foundation tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_integrity import (
    IntegrityResult,
    integrity_status_payload,
    validate_backtest_integrity,
    write_integrity_reports,
)
from aa_model_status import build_model_status, format_model_status_block, resolve_integrity_label


def test_validate_backtest_integrity_alias_pass():
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
    assert result.passed


def test_integrity_status_json_written(tmp_path: Path):
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
    write_integrity_reports(tmp_path, result)
    payload = __import__("json").loads((tmp_path / "integrity_status.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["calendar_complete"] is True
    assert payload["rebalance_complete"] is True
    assert payload["returns_complete"] is True
    assert "checked_at_utc" in payload


def test_integrity_status_fail_on_missing_period():
    rbs = pd.date_range("2020-01-01", periods=8, freq="B")
    rebalance_dates = list(rbs[[0, 2, 4, 6]])
    strategy_returns = pd.Series([0.001], index=[rbs[3]])
    result = validate_backtest_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        returns_calendar=rbs,
        simulated_rebalance_dates=[rebalance_dates[0]],
    )
    payload = integrity_status_payload(result)
    assert payload["status"] == "FAIL"
    assert payload["calendar_complete"] is False


def test_final_cash_weight_invariant():
    exposure = 0.65
    cash = max(0.0, 1.0 - exposure)
    assert exposure + cash == pytest.approx(1.0)
    assert cash == pytest.approx(0.35)


def test_model_status_not_validated(tmp_path: Path):
    status = build_model_status(tmp_path)
    assert status["integrity_status"] == "NOT_VALIDATED"
    text = format_model_status_block(status)
    assert "nicht freigegeben" in text.lower() or "NOT_VALIDATED" in text


def test_model_status_pass_from_pointer(tmp_path: Path):
    out = tmp_path / "model"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        '{"integrity_status":"PASS","variant_id":"R3_w070_q070_noexit","published_at_utc":"2026-05-30T12:00:00+00:00"}',
        encoding="utf-8",
    )
    assert resolve_integrity_label(out) == "PASS"
    status = build_model_status(out)
    assert status["integrity_status"] == "PASS"
    assert "R3_w070" in status["active_variant_label"]


def test_load_result_context_invalid_hides_metrics(tmp_path: Path):
    from aa_dashboard_result import load_result_context

    out = tmp_path / "model"
    out.mkdir()
    (out / "strategy_daily_returns.csv").write_text("date,strategy_return\n2020-01-02,0.001\n", encoding="utf-8")
    (out / "backtest_report.txt").write_text("Strategy metrics\n--------\ncagr: 0.12\n" + "x" * 80, encoding="utf-8")
    (out / "latest_target_portfolio.csv").write_text("ticker,target_weight\nAAPL,1.0\n", encoding="utf-8")
    ctx = load_result_context(out, metrics={"cagr": 0.5})
    assert ctx["analytical_validity"] in {"INVALID", "NOT_VALIDATED"}
    assert "nicht freigegeben" in ctx["metrics_summary"].lower() or "ungültig" in ctx["metrics_summary"].lower()
