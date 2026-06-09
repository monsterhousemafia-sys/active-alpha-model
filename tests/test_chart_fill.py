from __future__ import annotations

from pathlib import Path

import pytest


def test_measure_ink_ratio_on_equity_chart():
    from aa_chart_render import measure_ink_ratio, render_equity_chart_png, validate_chart_png
    import pandas as pd

    idx = pd.date_range("2020-01-01", periods=400, freq="B")
    strat = pd.Series(0.0005, index=idx)
    bench = pd.Series(0.0003, index=idx)
    png = render_equity_chart_png(strat, bench, width_px=420, height_px=300)
    assert len(png) > 500
    ink = measure_ink_ratio(png)
    assert ink >= 0.06
    rep = validate_chart_png("equity", png, target_w=420, target_h=300)
    assert rep.ok, rep.message


def test_sized_panels_match_dimensions():
    from aa_chart_render import png_dimensions, render_result_panels_sized
    import pandas as pd

    model_out = Path(__file__).resolve().parents[1] / "model_output_sp500_pit_t212"
    if not (model_out / "strategy_daily_returns.csv").is_file():
        pytest.skip("model output missing")
    from aa_result_views import sector_weights
    from aa_dashboard_result import load_benchmark_returns, load_strategy_returns, load_target_portfolio

    strategy = load_strategy_returns(model_out)
    benchmark = load_benchmark_returns(model_out)
    portfolio, _ = load_target_portfolio(model_out)
    sectors = sector_weights(portfolio)
    sizes = {"equity": (400, 280), "annual": (400, 280), "sector": (400, 280)}
    charts, reports = render_result_panels_sized(strategy, benchmark, sectors, sizes, bench_label="SPY")
    for key, (tw, th) in sizes.items():
        png = charts[f"{key}_chart_png"]
        w, h = png_dimensions(png)
        assert w == tw, f"{key} width {w} != {tw}"
        assert h == th, f"{key} height {h} != {th}"
    assert all(r.ok for r in reports), [r.message for r in reports if not r.ok]
