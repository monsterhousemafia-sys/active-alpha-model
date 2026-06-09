from __future__ import annotations

import pandas as pd
import pytest

import active_alpha_model as aam


def test_run_walkforward_pipeline_rejects_too_few_dates(smoke_features_returns):
    features, returns, cfg = smoke_features_returns
    tiny = features[features["date"] <= features["date"].iloc[100]].copy()
    with pytest.raises(RuntimeError, match="Not enough dates"):
        aam.run_walkforward_pipeline(tiny, returns, cfg, None, include_naive_baselines=False)


def test_simulate_walkforward_portfolio_path_smoke(smoke_features_returns):
    features, returns, cfg = smoke_features_returns
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]
    assert len(rebalance_dates) >= 2

    strategy_returns, decisions, weights = aam._simulate_walkforward_portfolio_path(
        {},
        features,
        returns,
        dates,
        rebalance_dates,
        cfg,
        None,
    )
    assert len(strategy_returns) > 0
    assert not decisions.empty
    assert "rebalance_date" in decisions.columns
    assert weights.empty or "rebalance_date" in weights.columns
