from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from aa_dashboard_result import (
    DISCLAIMER_TEXT,
    build_context_line,
    calendar_year_returns,
    exemplar_stock_portfolio,
    export_portfolio_csv,
    load_result_context,
    load_target_portfolio,
    resolve_portfolio_exposure,
    scale_portfolio_rows,
    stock_only_portfolio,
)


ROOT = Path(__file__).resolve().parents[1]
MODEL_OUT = ROOT / "model_output_sp500_pit_t212"


def test_calendar_year_returns_from_daily():
    idx = pd.date_range("2020-01-02", periods=4, freq="B")
    daily = pd.Series([0.01, -0.01, 0.02, 0.0], index=idx)
    yr = calendar_year_returns(daily)
    assert len(yr) == 1
    assert yr.index[0] == 2020
    assert yr.iloc[0] == pytest.approx((1.01 * 0.99 * 1.02 * 1.0) - 1.0, rel=1e-6)


def test_stock_only_portfolio_drops_benchmark_filler():
    df = pd.DataFrame(
        {
            "ticker": ["SPY", "AAPL"],
            "target_weight": [0.2, 0.8],
            "sector": ["Benchmark", "Technology"],
            "correlation_cluster": ["Benchmark_Completion", "Tech"],
        }
    )
    out = stock_only_portfolio(df)
    assert list(out["ticker"]) == ["AAPL"]


def test_scale_portfolio_rows_full_investment():
    df = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "target_weight": [0.6, 0.4],
            "sector": ["Tech", "Health"],
            "portfolio_exposure": [1.0, 1.0],
        }
    )
    rows, invested, cash = scale_portfolio_rows(df, 1000.0)
    assert len(rows) == 2
    assert invested == pytest.approx(1000.0, abs=0.01)
    assert cash == pytest.approx(0.0, abs=0.01)


def test_scale_portfolio_rows_partial_exposure_leaves_cash():
    df = pd.DataFrame(
        {
            "ticker": ["AAA", "BBB"],
            "target_weight": [0.384, 0.256],
            "sector": ["Tech", "Health"],
            "portfolio_exposure": [0.64, 0.64],
        }
    )
    rows, invested, cash = scale_portfolio_rows(
        df,
        10_000.0,
        prices_usd={"AAA": 100.0, "BBB": 50.0},
        eurusd=1.1,
    )
    assert invested == pytest.approx(6400.0, abs=0.05)
    assert cash == pytest.approx(3600.0, abs=0.05)
    assert rows[0]["weight_pct"] == pytest.approx(38.4, abs=0.1)


def test_resolve_portfolio_exposure_from_column():
    df = pd.DataFrame({"portfolio_exposure": [0.642], "target_weight": [0.1]})
    assert resolve_portfolio_exposure(df) == pytest.approx(0.642)


def test_export_portfolio_csv_writes_file(tmp_path: Path):
    rows = [
        {"ticker": "AAA", "sector": "Tech", "weight_pct": 60.0, "amount": 600.0, "shares": "5"},
        {"ticker": "BBB", "sector": "Health", "weight_pct": 40.0, "amount": 400.0, "shares": "2"},
    ]
    path = export_portfolio_csv(tmp_path / "p.csv", rows, amount=1000.0, context_line="test")
    text = path.read_text(encoding="utf-8-sig")
    assert "AAA" in text
    assert "Bargeld" not in text.split("Ticker", 1)[-1]
    assert DISCLAIMER_TEXT


@pytest.mark.skipif(not MODEL_OUT.is_dir(), reason="model output missing")
def test_load_target_portfolio_from_model_output():
    df, source = load_target_portfolio(MODEL_OUT)
    assert not df.empty
    assert "target_weight" in df.columns
    assert source
    # Model may include benchmark-completion ETF (e.g. SPY) as a normal position.
    assert float(df["target_weight"].sum()) > 0


@pytest.mark.skipif(not (MODEL_OUT / "strategy_daily_returns.csv").is_file(), reason="returns missing")
def test_load_result_context_builds_chart():
    ctx = load_result_context(MODEL_OUT, metrics={"cagr": 0.265, "sharpe_0rf": 1.14})
    assert not ctx["strategy_returns"].empty
    assert isinstance(ctx["chart_png"], (bytes, bytearray))
    assert len(ctx["chart_png"]) > 1000
    assert "Ø Rendite" in ctx["metrics_summary"]
    assert ctx["disclaimer"]
    assert "Zeitraum:" in ctx["context_line"]


@pytest.mark.skipif(not (MODEL_OUT / "strategy_daily_returns.csv").is_file(), reason="returns missing")
def test_build_context_line_includes_period():
    line = build_context_line(MODEL_OUT, signal_date="2026-05-28", portfolio_exposure=0.64)
    assert "Zeitraum:" in line
    assert "2026-05-28" in line
    assert "64%" in line


def test_exemplar_stock_portfolio_renormalizes_without_cash():
    df = pd.DataFrame(
        {
            "ticker": ["SPY", "AAA", "BBB"],
            "target_weight": [0.135, 0.45, 0.115],
            "sector": ["Benchmark", "Tech", "Health"],
            "correlation_cluster": ["Benchmark_Completion", "Tech", "Health"],
        }
    )
    out = exemplar_stock_portfolio(df)
    assert "SPY" not in out["ticker"].tolist()
    assert out["target_weight"].sum() == pytest.approx(1.0, abs=1e-9)
    rows, invested, cash = scale_portfolio_rows(out, 10_000.0)
    assert cash == pytest.approx(0.0, abs=0.05)
    assert invested == pytest.approx(10_000.0, abs=0.05)


def test_weighted_progress_eta():
    from aa_dashboard_core import DashboardCore

    core = DashboardCore()
    core.start_phase("Walk-forward ML (Phase A)", total=100, step="ML")
    core.advance_phase(25)
    ratio = core.progress_ratio()
    assert 0.30 < ratio < 0.45
    eta = core.eta_seconds(120.0)
    assert eta is not None
    assert eta > 0
