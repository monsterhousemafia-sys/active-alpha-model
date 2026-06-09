from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import active_alpha_model as aam


def test_write_backtest_core_outputs_writes_csvs(tmp_path: Path):
    idx = pd.date_range("2024-01-02", periods=3, freq="B")
    research = aam.ResearchPipelineResult(
        strategy_returns=pd.Series([0.001, -0.002, 0.003], index=idx),
        decisions=pd.DataFrame({"date": idx[:1], "ticker": ["AAPL"], "target_weight": [0.05]}),
        weight_history=pd.DataFrame({"date": idx[:1], "ticker": ["AAPL"], "weight": [0.05]}),
        naive_returns=pd.DataFrame(),
        benchmark_returns=pd.Series([0.0005, -0.001, 0.002], index=idx),
        metrics={"total_return": 0.01},
        bench_metrics={"total_return": 0.005},
    )
    output_files: list[Path] = []
    strategy_path, decisions_path, weights_path, report_path = aam.write_backtest_core_outputs(
        tmp_path,
        research,
        output_files=output_files,
    )
    assert strategy_path.exists()
    assert decisions_path.exists()
    assert weights_path.exists()
    assert report_path.name == "backtest_report.txt"
    assert strategy_path in output_files


def test_run_research_pipeline_requires_enough_dates(smoke_features_returns):
    features, returns, cfg = smoke_features_returns
    short_features = features.head(100)
    with pytest.raises(RuntimeError, match="Not enough dates"):
        aam.run_research_pipeline(short_features, returns, cfg)


def test_custom_benchmark_helpers_match_legacy_shape():
    cfg = aam.BacktestConfig(membership_mode="off", custom_benchmarks=True)
    # Need >=100 dates for compute_custom_benchmark_returns
    dates = pd.bdate_range("2020-01-01", periods=120)
    tickers = ["AAPL", "MSFT"]
    rows = []
    for dt in dates:
        for tk in tickers:
            rows.append(
                {
                    "date": dt,
                    "ticker": tk,
                    "in_universe": True,
                    "universe_adv": 50e6,
                    "adv_20": 50e6,
                    "close": 100.0,
                    "mom_252_21": 0.1,
                    "mom_126_21": 0.08,
                    "mom_63_21": 0.05,
                    "sector": "Technology",
                    "issuer": tk,
                    "correlation_cluster": "TECH",
                }
            )
    features = pd.DataFrame(rows)
    ret_idx = dates
    returns = pd.DataFrame(
        {
            "AAPL": [0.001] * len(dates),
            "MSFT": [0.002] * len(dates),
            "SPY": [0.0005] * len(dates),
        },
        index=ret_idx,
    )
    out = aam.compute_custom_benchmark_returns(features, returns, cfg)
    assert "STRATEGY_UNIVERSE_EQUAL_WEIGHT" in out
    assert len(out["STRATEGY_UNIVERSE_EQUAL_WEIGHT"]) > 50


def test_min_trade_value_rounding_vectorized():
    cfg = aam.BacktestConfig(
        policy_min_trade_value=0.0,
        order_value_rounding=1.0,
        broker_min_remaining_position_value=0.0,
        backtest_capital=100_000.0,
    )
    target = pd.Series({"A": 0.10, "B": 0.05})
    previous = pd.Series({"A": 0.08, "B": 0.05})
    out = aam.apply_min_trade_value_filter(target, previous, 100_000.0, cfg)
    assert "A" in out.index
    assert abs(out["A"] - 0.10) < 0.002 or abs(out["A"] - 0.08) < 0.002
