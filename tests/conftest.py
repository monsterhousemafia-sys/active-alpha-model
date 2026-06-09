from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

os.environ.pop("AA_PYTEST_SESSION", None)


@pytest.fixture(autouse=True)
def _mark_pytest_session(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AA_PYTEST_SESSION", "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import active_alpha_model as aam  # noqa: E402


@pytest.fixture
def model_module():
    return aam


@pytest.fixture
def allocator_cfg() -> aam.BacktestConfig:
    return aam.BacktestConfig(
        max_position=0.075,
        max_issuer=0.10,
        max_sector=0.25,
        max_correlation_cluster=0.20,
        max_portfolio_beta=0.60,
    )


@pytest.fixture
def allocator_candidates() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["GOOG", "GOOGL", "NVDA", "AMD", "JPM", "MSFT", "AAPL", "XOM"],
            "sector": [
                "Communication",
                "Communication",
                "Semiconductors",
                "Semiconductors",
                "Financials",
                "Technology",
                "Technology",
                "Energy",
            ],
            "issuer": ["ALPHABET", "ALPHABET", "NVDA", "AMD", "JPM", "MSFT", "AAPL", "XOM"],
            "beta_252": [1.2, 1.1, 1.8, 1.6, 1.0, 1.1, 1.0, 0.8],
        }
    )


@pytest.fixture
def allocator_raw(allocator_candidates: pd.DataFrame) -> pd.Series:
    return pd.Series([10, 9, 8, 7, 6, 5, 4, 3], index=allocator_candidates["ticker"])


def make_synthetic_feature_table(
    *,
    n_days: int = 500,
    tickers: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    tickers = tickers or ["AAPL", "MSFT", "NVDA", "JPM", "XOM"]
    dates = pd.bdate_range("2018-01-01", periods=n_days)
    rows: list[dict] = []
    for dt in dates:
        for tk in tickers:
            row = {col: float(rng.normal()) for col in aam.FEATURE_COLUMNS}
            row.update(
                {
                    "date": pd.Timestamp(dt),
                    "ticker": tk,
                    "target": float(rng.normal(0, 0.02)),
                    "rank_score": float(rng.uniform(0.0, 1.0)),
                    "close": float(100.0 + rng.normal()),
                    "adv_20": float(rng.uniform(20e6, 120e6)),
                    "trend_50": 1.0,
                    "trend_200": 1.0,
                    "market_trend_200": 1.0,
                    "market_ret_63": 0.05,
                    "vol_20": 0.20,
                    "in_universe": True,
                    "sector": "Technology",
                    "issuer": tk,
                    "correlation_cluster": tk,
                    "beta_252": 1.0,
                    "risk_on": True,
                    "selection_score": float(rng.normal()),
                    "alpha_lcb": float(rng.normal(0, 0.01)),
                    "universe_adv": float(rng.uniform(20e6, 120e6)),
                    "universe_history_days": 300,
                }
            )
            rows.append(row)
    return pd.DataFrame(rows)


def make_synthetic_returns(features: pd.DataFrame, *, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.DatetimeIndex(sorted(pd.to_datetime(features["date"].dropna().unique())))
    tickers = sorted(features["ticker"].astype(str).unique())
    data = {tk: rng.normal(0.0, 0.01, len(dates)) for tk in tickers}
    data["SPY"] = rng.normal(0.0, 0.008, len(dates))
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def smoke_backtest_cfg() -> aam.BacktestConfig:
    return aam.BacktestConfig(
        start="2018-01-01",
        benchmark="SPY",
        train_years=1,
        min_train_rows=120,
        rebalance_every=25,
        top_k=3,
        n_jobs="1",
        naive_momentum_baseline=False,
        max_position=0.40,
        max_issuer=0.50,
        max_sector=1.0,
        max_correlation_cluster=1.0,
        max_portfolio_beta=0.0,
        min_adv=1_000_000.0,
    )


@pytest.fixture
def smoke_features_returns(smoke_backtest_cfg: aam.BacktestConfig):
    features = make_synthetic_feature_table(n_days=500)
    returns = make_synthetic_returns(features)
    return features, returns, smoke_backtest_cfg
