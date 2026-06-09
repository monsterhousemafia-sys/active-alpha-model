from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS

def make_model(random_state: int = 42):
    try:
        from sklearn.compose import TransformedTargetRegressor
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import ElasticNet
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import RobustScaler, StandardScaler
    except ImportError as e:
        raise SystemExit("scikit-learn is not installed. Run: pip install -r requirements.txt") from e

    elastic = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", ElasticNet(alpha=0.0005, l1_ratio=0.20, max_iter=5000, random_state=random_state)),
    ])

    gbm = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("model", HistGradientBoostingRegressor(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=15,
            min_samples_leaf=80,
            l2_regularization=0.10,
            random_state=random_state,
        )),
    ])
    return elastic, gbm


def fit_predict(train: pd.DataFrame, pred: pd.DataFrame, feature_cols: List[str], cfg: Optional[BacktestConfig] = None) -> Tuple[pd.DataFrame, float]:
    train = train.dropna(subset=["target"]).copy()
    pred = pred.copy()
    if len(train) < 500:
        pred["mu_elastic"] = np.nan
        pred["mu_gbm"] = np.nan
        pred["mu_rank"] = np.nan
        pred["mu_hat_raw"] = np.nan
        pred["mu_calibrated"] = np.nan
        pred["mu_hat"] = np.nan
        return pred, np.nan

    X = train[feature_cols]
    y = train["target"].astype(float)
    x_pred = pred[feature_cols]

    seed = int(getattr(cfg, "random_seed", 42) or 42) if cfg is not None else 42
    elastic, gbm = make_model(random_state=seed)
    train_fit = train
    train_cal = train.iloc[0:0]
    if "date" in train.columns and len(train) >= 800:
        ordered = train.sort_values("date")
        cal_start = int(len(ordered) * 0.80)
        if len(ordered) - cal_start >= 100:
            train_fit = ordered.iloc[:cal_start]
            train_cal = ordered.iloc[cal_start:]
    X_fit = train_fit[feature_cols]
    y_fit = train_fit["target"].astype(float)
    elastic.fit(X_fit, y_fit)
    gbm.fit(X_fit, y_fit)

    pred["mu_elastic"] = elastic.predict(x_pred)
    pred["mu_gbm"] = gbm.predict(x_pred)

    # Map rank_score into return units using training target dispersion.
    target_std = float(np.nanstd(y)) if np.nanstd(y) > 0 else 0.02
    pred["mu_rank"] = (pred["rank_score"].fillna(0.5) - 0.5) * target_std
    train_rank = (train["rank_score"].fillna(0.5) - 0.5) * target_std
    train_elastic = pd.Series(elastic.predict(X_fit), index=train_fit.index)
    train_gbm = pd.Series(gbm.predict(X_fit), index=train_fit.index)
    train_rank_fit = (train_fit["rank_score"].fillna(0.5) - 0.5) * target_std
    mode = str(getattr(cfg, "alpha_model_mode", "ensemble") if cfg is not None else "ensemble").lower().strip()
    if mode == "rank_only":
        raw_pred = pred["mu_rank"]
        train_raw = train_rank_fit
    elif mode == "ml_only":
        raw_pred = 0.50 * pred["mu_elastic"] + 0.50 * pred["mu_gbm"]
        train_raw = 0.50 * train_elastic + 0.50 * train_gbm
    elif mode == "elastic_only":
        raw_pred = pred["mu_elastic"]
        train_raw = train_elastic
    elif mode == "gbm_only":
        raw_pred = pred["mu_gbm"]
        train_raw = train_gbm
    else:
        raw_pred = 0.40 * pred["mu_elastic"] + 0.40 * pred["mu_gbm"] + 0.20 * pred["mu_rank"]
        train_raw = 0.40 * train_elastic + 0.40 * train_gbm + 0.20 * train_rank_fit
    pred["alpha_model_mode"] = mode
    pred["mu_hat_raw"] = raw_pred

    # In-sample predictions are used only to calibrate score bins, not to report performance.
    rmse = float(np.sqrt(np.nanmean((y_fit - train_raw) ** 2)))

    # OOS calibration holdout: bins from last 20% of training window (not full in-sample fit).
    try:
        cal_source = train_cal if len(train_cal) >= 50 else train_fit
        cal_y = cal_source["target"].astype(float)
        cal_X = cal_source[feature_cols]
        if mode == "rank_only":
            cal_raw = (cal_source["rank_score"].fillna(0.5) - 0.5) * target_std
        elif mode == "ml_only":
            cal_raw = 0.50 * pd.Series(elastic.predict(cal_X), index=cal_source.index) + 0.50 * pd.Series(gbm.predict(cal_X), index=cal_source.index)
        elif mode == "elastic_only":
            cal_raw = pd.Series(elastic.predict(cal_X), index=cal_source.index)
        elif mode == "gbm_only":
            cal_raw = pd.Series(gbm.predict(cal_X), index=cal_source.index)
        else:
            cal_rank = (cal_source["rank_score"].fillna(0.5) - 0.5) * target_std
            cal_raw = 0.40 * pd.Series(elastic.predict(cal_X), index=cal_source.index) + 0.40 * pd.Series(gbm.predict(cal_X), index=cal_source.index) + 0.20 * cal_rank
        train_bins = pd.qcut(pd.Series(cal_raw, index=cal_source.index).rank(method="first"), q=10, labels=False, duplicates="drop")
        bin_means = cal_y.groupby(train_bins).mean()
        sorted_cal_raw = np.sort(np.asarray(cal_raw, dtype=float))
        pct = np.searchsorted(sorted_cal_raw, np.asarray(raw_pred, dtype=float), side="right") / max(len(sorted_cal_raw), 1)
        pred_bins = np.clip(np.floor(pct * 10).astype(int), 0, 9)
        fallback = float(np.nanmean(cal_y)) if np.isfinite(np.nanmean(cal_y)) else 0.0
        pred["mu_calibrated"] = pd.Series(pred_bins, index=pred.index).map(bin_means).fillna(fallback).astype(float)
        pred["mu_hat"] = 0.65 * pred["mu_hat_raw"] + 0.35 * pred["mu_calibrated"]
    except Exception:
        pred["mu_calibrated"] = np.nan
        pred["mu_hat"] = pred["mu_hat_raw"]

    return pred, rmse
