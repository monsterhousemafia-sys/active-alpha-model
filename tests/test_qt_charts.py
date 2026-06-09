"""Tests for native Qt Charts result panels."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


def _require_qt():
    pytest.importorskip("PySide6.QtWidgets")
    pytest.importorskip("PySide6.QtCharts")


def test_qt_charts_build_from_model_output():
    _require_qt()
    from PySide6.QtWidgets import QApplication

    from aa_qt_charts import build_annual_chart, build_equity_chart, build_sector_chart, qt_charts_available

    assert qt_charts_available()
    app = QApplication.instance() or QApplication([])

    model_out = Path(__file__).resolve().parents[1] / "model_output_sp500_pit_t212"
    if not (model_out / "strategy_daily_returns.csv").is_file():
        pytest.skip("model output missing")

    from aa_dashboard_result import load_benchmark_returns, load_strategy_returns, load_target_portfolio
    from aa_result_views import sector_weights

    strategy = load_strategy_returns(model_out)
    benchmark = load_benchmark_returns(model_out)
    portfolio, _ = load_target_portfolio(model_out)
    sectors = sector_weights(portfolio)

    equity = build_equity_chart(strategy, benchmark, bench_label="SPY")
    annual = build_annual_chart(strategy, benchmark, bench_label="SPY")
    sector = build_sector_chart(sectors)

    assert len(equity.series()) >= 1
    assert len(annual.series()) >= 1
    assert len(sector.series()) >= 1
    _ = app


def test_qt_result_chart_panel_updates():
    _require_qt()
    from PySide6.QtWidgets import QApplication

    from aa_qt_charts import QtResultChartPanel

    app = QApplication.instance() or QApplication([])
    panel = QtResultChartPanel("equity")
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    strat = pd.Series(0.0004, index=idx)
    bench = pd.Series(0.0003, index=idx)
    assert panel.show_equity(strat, bench, bench_label="SPY")
    panel.show_message("leer")
    assert panel.widget is not None
    _ = app
