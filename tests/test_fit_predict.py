from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import active_alpha_model as aam
from conftest import make_synthetic_feature_table


def _fit_predict_frames(n_train: int = 700, n_pred: int = 25) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_days = (n_train + n_pred) // 5 + 10
    features = make_synthetic_feature_table(n_days=n_days)
    all_rows = features.dropna(subset=["target"])
    train = all_rows.iloc[:n_train].copy()
    pred = all_rows.iloc[n_train : n_train + n_pred].copy()
    assert len(train) >= 500
    assert len(pred) >= 1
    pred["rank_score"] = pred["rank_score"].fillna(0.5)
    train["rank_score"] = train["rank_score"].fillna(0.5)
    return train, pred


def test_fit_predict_populates_mu_hat():
    train, pred = _fit_predict_frames()
    out, rmse = aam.fit_predict(train, pred, aam.FEATURE_COLUMNS, aam.BacktestConfig(alpha_model_mode="ensemble"))
    assert np.isfinite(rmse)
    assert out["mu_hat"].notna().any()
    assert out["mu_calibrated"].notna().any()
    assert out["alpha_model_mode"].iloc[0] == "ensemble"


def test_fit_predict_rank_only_mode():
    train, pred = _fit_predict_frames()
    cfg = aam.BacktestConfig(alpha_model_mode="rank_only")
    out, rmse = aam.fit_predict(train, pred, aam.FEATURE_COLUMNS, cfg)
    assert out["alpha_model_mode"].iloc[0] == "rank_only"
    assert out["mu_hat"].notna().any()


def test_fit_predict_returns_nan_outputs_when_train_too_small():
    train, pred = _fit_predict_frames(n_train=700, n_pred=25)
    tiny_train = train.head(100)
    out, rmse = aam.fit_predict(tiny_train, pred, aam.FEATURE_COLUMNS, aam.BacktestConfig())
    assert np.isnan(rmse)
    assert out["mu_hat"].isna().all()
