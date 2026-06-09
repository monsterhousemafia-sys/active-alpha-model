from __future__ import annotations

from pathlib import Path

import pytest


def test_project_root_finds_repo():
    from aa_paths import project_root

    root = project_root()
    assert (root / "active_alpha_model.py").is_file()


def test_version_strings():
    from aa_version import APP_TITLE, APP_VERSION, MODEL_PROFILE

    assert APP_VERSION
    assert MODEL_PROFILE == "R3"
    assert APP_TITLE == "R3"


def test_eta_calibration_budgets():
    from aa_eta_calibration import build_backtest_budgets, estimate_backtest_remaining

    budgets = build_backtest_budgets()
    assert sum(budgets.values()) > 100
    eta = estimate_backtest_remaining(
        pipeline_status={"universe": "done", "features": "done", "ml": "active", "path": "pending", "export": "pending"},
        active_key="ml",
        sub_completed=10,
        sub_total=100,
        elapsed=300.0,
        out_dir="",
    )
    assert eta is not None
    assert eta >= 0


def test_load_result_context_enriched():
    model_out = Path(__file__).resolve().parents[1] / "model_output_sp500_pit_t212"
    if not (model_out / "strategy_daily_returns.csv").is_file():
        pytest.skip("model output missing")
    from aa_dashboard_result import load_result_context

    ctx = load_result_context(model_out, metrics={"cagr": 0.2, "sharpe_0rf": 1.0, "max_drawdown": -0.2})
    assert ctx["chart_png"]
    assert ctx["app_title"]
    assert ctx["disclaimer"]
    assert "context_line" in ctx
    assert ctx.get("price_source") in {"live", "cache", "offline"}


def test_sector_weights_and_fees():
    import pandas as pd

    from aa_result_views import estimate_portfolio_fees, sector_weights

    df = pd.DataFrame(
        {"ticker": ["AAPL", "MSFT"], "target_weight": [0.6, 0.4], "sector": ["Tech", "Tech"]}
    )
    sw = sector_weights(df)
    assert float(sw.sum()) == pytest.approx(1.0)
    fees = estimate_portfolio_fees(
        [{"ticker": "AAPL", "amount": 100.0}],
        prices_usd={"AAPL": 200.0},
        eurusd=1.1,
    )
    assert fees["total_cost_eur"] >= 0
