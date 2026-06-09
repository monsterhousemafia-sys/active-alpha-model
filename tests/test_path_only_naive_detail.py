"""Path-only backtest must emit naive detailed CSVs (H1 seal benchmark)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from aa_backtest import run_path_only_research
from aa_config import BacktestConfig
from aa_execution import PhaseTimings


def _minimal_inputs(tmp_path: Path):
    idx = pd.date_range("2015-01-02", periods=700, freq="B")
    features = pd.DataFrame(
        {
            "date": list(idx) * 2,
            "ticker": ["AAA"] * len(idx) + ["BBB"] * len(idx),
            "close": 100.0,
            "volume": 1_000_000.0,
            "market_trend_200": 1.0,
        }
    )
    returns = pd.DataFrame(
        {"AAA": 0.001, "BBB": 0.0005},
        index=idx,
    )
    cfg = BacktestConfig(
        start="2016-01-01",
        train_years=1,
        rebalance_every=1,
        out_dir=str(tmp_path),
        naive_detailed_reporting=True,
        naive_detailed_variants="mom_1_top12",
        n_jobs="2",
        cpu_cores=4,
    )
    strat = pd.Series(0.001, index=idx[300:])
    prediction_cache = {pd.Timestamp(d): {"portfolio": pd.DataFrame()} for d in idx[300::5]}
    return features, returns, cfg, strat, prediction_cache


@patch("aa_backtest.load_verified_benchmark_returns")
@patch("aa_backtest.validate_backtest_calendar_integrity")
@patch("aa_backtest._simulate_walkforward_portfolio_path")
@patch("aa_backtest.run_naive_detailed_reporting")
def test_path_only_runs_naive_detailed_serial_when_overlap_disabled(
    mock_naive_detail,
    mock_simulate,
    mock_integrity,
    mock_benchmark,
    tmp_path: Path,
) -> None:
    features, returns, cfg, strat, prediction_cache = _minimal_inputs(tmp_path)
    cfg.no_naive_overlap = True
    mock_simulate.return_value = (strat, pd.DataFrame(), pd.DataFrame())
    mock_benchmark.return_value = (strat * 0.5, "spy", True)
    mock_integrity.return_value = MagicMock(passed=True)
    seal_csv = tmp_path / "naive_mom_1_daily_returns.csv"
    seal_csv.write_text("date,return\n2016-01-01,0.001\n", encoding="utf-8")
    mock_naive_detail.return_value = [seal_csv]

    timings = PhaseTimings()
    run_path_only_research(
        features,
        returns,
        cfg,
        prediction_cache,
        phase_timings=timings,
    )

    mock_naive_detail.assert_called_once()
    assert seal_csv.is_file()
    assert timings.as_dict().get("walkforward_phase_c_naive", 0) >= 0
    assert timings.meta.get("naive_detailed_path_only") is True
    assert timings.meta.get("naive_detailed_overlap") is False
    assert "naive_mom_1_daily_returns.csv" in timings.meta.get("h1_seal_benchmark_paths", [])


@patch("aa_backtest.load_verified_benchmark_returns")
@patch("aa_backtest.validate_backtest_calendar_integrity")
@patch("aa_backtest._simulate_walkforward_portfolio_path")
@patch("aa_backtest.run_naive_detailed_reporting")
def test_path_only_runs_naive_detailed_parallel_when_overlap_enabled(
    mock_naive_detail,
    mock_simulate,
    mock_integrity,
    mock_benchmark,
    tmp_path: Path,
) -> None:
    features, returns, cfg, strat, prediction_cache = _minimal_inputs(tmp_path)
    mock_simulate.return_value = (strat, pd.DataFrame(), pd.DataFrame())
    mock_benchmark.return_value = (strat * 0.5, "spy", True)
    mock_integrity.return_value = MagicMock(passed=True)
    seal_csv = tmp_path / "naive_mom_1_daily_returns.csv"
    seal_csv.write_text("date,return\n2016-01-01,0.001\n", encoding="utf-8")
    mock_naive_detail.return_value = [seal_csv]

    timings = PhaseTimings()
    run_path_only_research(
        features,
        returns,
        cfg,
        prediction_cache,
        phase_timings=timings,
    )

    mock_naive_detail.assert_called_once()
    assert seal_csv.is_file()
    assert timings.meta.get("naive_detailed_overlap") is True
    assert timings.meta.get("naive_detailed_path_only") is True
    assert timings.as_dict().get("sections_seconds", {}).get("walkforward_phase_c_naive", 0) >= 0


@patch("aa_backtest.load_verified_benchmark_returns")
@patch("aa_backtest.validate_backtest_calendar_integrity")
@patch("aa_backtest._simulate_walkforward_portfolio_path")
@patch("aa_backtest.run_naive_detailed_reporting")
def test_path_only_skips_naive_detailed_when_disabled(
    mock_naive_detail,
    mock_simulate,
    mock_integrity,
    mock_benchmark,
    tmp_path: Path,
) -> None:
    features, returns, cfg, strat, prediction_cache = _minimal_inputs(tmp_path)
    cfg.naive_detailed_reporting = False
    mock_simulate.return_value = (strat, pd.DataFrame(), pd.DataFrame())
    mock_benchmark.return_value = (strat * 0.5, "spy", True)
    mock_integrity.return_value = MagicMock(passed=True)

    timings = PhaseTimings()
    run_path_only_research(
        features,
        returns,
        cfg,
        prediction_cache,
        phase_timings=timings,
    )

    mock_naive_detail.assert_not_called()
    assert timings.as_dict().get("sections_seconds", {}).get("walkforward_phase_c_naive", 0) == 0
    assert timings.meta.get("naive_detailed_path_only") is False


@patch("aa_backtest.load_verified_benchmark_returns")
@patch("aa_backtest.validate_backtest_calendar_integrity")
@patch("aa_backtest._simulate_walkforward_portfolio_path")
@patch("aa_backtest.run_naive_detailed_reporting")
def test_path_only_fails_closed_when_seal_csv_missing(
    mock_naive_detail,
    mock_simulate,
    mock_integrity,
    mock_benchmark,
    tmp_path: Path,
) -> None:
    features, returns, cfg, strat, prediction_cache = _minimal_inputs(tmp_path)
    mock_simulate.return_value = (strat, pd.DataFrame(), pd.DataFrame())
    mock_benchmark.return_value = (strat * 0.5, "spy", True)
    mock_integrity.return_value = MagicMock(passed=True)
    mock_naive_detail.return_value = []

    with pytest.raises(RuntimeError, match="naive_mom_1_daily_returns.csv"):
        run_path_only_research(features, returns, cfg, prediction_cache)
