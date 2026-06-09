from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd
import pytest

import active_alpha_model as aam


def test_prediction_fingerprint_changes_with_alpha_mode():
    cfg1 = aam.BacktestConfig(alpha_model_mode="ensemble")
    cfg2 = aam.BacktestConfig(alpha_model_mode="rank_only")
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"), pd.Timestamp("2020-03-01")]
    fp1 = aam._prediction_build_fingerprint(cfg1, 100, rbs)
    fp2 = aam._prediction_build_fingerprint(cfg2, 100, rbs)
    assert fp1 != fp2


def test_prediction_fingerprint_changes_with_risk_off_selection_mode():
    cfg_legacy = aam.BacktestConfig(risk_off_selection_mode="legacy")
    cfg_blend = aam.BacktestConfig(risk_off_selection_mode="mom_blend_blend", risk_off_momentum_weight=0.70)
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]
    assert aam._prediction_build_fingerprint(cfg_legacy, 100, rbs) != aam._prediction_build_fingerprint(cfg_blend, 100, rbs)


def test_prediction_cache_roundtrip(tmp_path: Path):
    cfg = aam.BacktestConfig(alpha_model_mode="ensemble", train_years=5, horizon=10)
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"), pd.Timestamp("2020-03-01")]
    results = {
        pd.Timestamp("2020-01-01"): {
            "status": "ok",
            "rb": pd.Timestamp("2020-01-01"),
            "next_rb": pd.Timestamp("2020-02-01"),
            "train_rows": 1000,
            "snapshot_rows": 50,
            "rmse": 0.01,
            "target_weights": pd.Series({"AAPL": 0.5, "MSFT": 0.5}),
            "ranked": pd.DataFrame({"ticker": ["AAPL", "MSFT"], "mu_hat": [0.01, 0.02]}),
            "effective_beta_cap": 1.25,
        },
        pd.Timestamp("2020-02-01"): {
            "status": "ok",
            "rb": pd.Timestamp("2020-02-01"),
            "next_rb": pd.Timestamp("2020-03-01"),
            "train_rows": 1000,
            "snapshot_rows": 50,
            "rmse": 0.01,
            "target_weights": pd.Series({"AAPL": 0.5, "MSFT": 0.5}),
            "ranked": pd.DataFrame({"ticker": ["AAPL", "MSFT"], "mu_hat": [0.01, 0.02]}),
            "effective_beta_cap": 1.25,
        },
    }
    aam._save_prediction_cache(tmp_path, cfg, 50, rbs, results)
    loaded, reason, missing = aam._try_load_prediction_cache(tmp_path, cfg, 50, rbs)
    assert reason is None
    assert missing == []
    assert loaded is not None
    assert pd.Timestamp("2020-01-01") in loaded
    assert loaded[pd.Timestamp("2020-01-01")]["status"] == "ok"
    meta = json.loads((tmp_path / "prediction_cache_meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == aam.PREDICTION_CACHE_SCHEMA_VERSION


def test_prediction_fingerprint_ignores_diagnostic_cluster_mode():
    cfg_static = aam.BacktestConfig(cluster_mode="static", cluster_constraint_mode="static_only")
    cfg_diag = aam.BacktestConfig(cluster_mode="dynamic_diagnostic", cluster_constraint_mode="static_only")
    cfg_enforced = aam.BacktestConfig(cluster_mode="dynamic_enforced", cluster_constraint_mode="static_only")
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"), pd.Timestamp("2020-03-01")]
    fp_static = aam._prediction_build_fingerprint(cfg_static, 100, rbs)
    fp_diag = aam._prediction_build_fingerprint(cfg_diag, 100, rbs)
    fp_enforced = aam._prediction_build_fingerprint(cfg_enforced, 100, rbs)
    assert fp_static == fp_diag
    assert fp_enforced != fp_static


def test_prediction_cache_incremental_extension(tmp_path: Path):
    cfg = aam.BacktestConfig(alpha_model_mode="ensemble", train_years=5, horizon=10)
    rbs_old = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01"), pd.Timestamp("2020-03-01")]
    results = {
        pd.Timestamp("2020-01-01"): {"status": "ok", "rb": pd.Timestamp("2020-01-01")},
        pd.Timestamp("2020-02-01"): {"status": "ok", "rb": pd.Timestamp("2020-02-01")},
    }
    aam._save_prediction_cache(tmp_path, cfg, 50, rbs_old, results)
    rbs_new = rbs_old + [pd.Timestamp("2020-04-01")]
    loaded, reason, missing = aam._try_load_prediction_cache(tmp_path, cfg, 50, rbs_new)
    assert reason is None
    assert len(missing) == 1
    assert pd.Timestamp("2020-02-01") in loaded
    assert pd.Timestamp("2020-03-01") not in loaded


def test_prediction_cache_config_mismatch(tmp_path: Path):
    cfg = aam.BacktestConfig(alpha_model_mode="ensemble")
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]
    aam._save_prediction_cache(
        tmp_path,
        cfg,
        50,
        rbs,
        {pd.Timestamp("2020-01-01"): {"status": "ok"}},
    )
    cfg2 = aam.BacktestConfig(alpha_model_mode="rank_only")
    loaded, reason, missing = aam._try_load_prediction_cache(tmp_path, cfg2, 50, rbs)
    assert loaded is None
    assert reason == "config_mismatch"
    assert missing == []


def test_frozen_env_enables_thread_parallel_and_caches():
    from aa_frozen import apply_frozen_env_defaults

    env = apply_frozen_env_defaults({}, force=True)
    assert env.get("AA_PARALLEL_BACKTEST_BACKEND") == "thread"
    assert env.get("AA_SKIP_DOWNLOAD_IF_CACHED") == "1"
    assert env.get("AA_N_JOBS") == "auto"
    assert env.get("AA_REUSE_PREDICTION_CACHE") == "1"


def test_price_cache_fingerprint_and_ttl(tmp_path: Path):
    fp1 = aam._price_cache_fingerprint(["AAPL", "MSFT"], "2020-01-01")
    fp2 = aam._price_cache_fingerprint(["MSFT", "AAPL"], "2020-01-01")
    assert fp1 == fp2
    assert fp1 != aam._price_cache_fingerprint(["AAPL", "MSFT"], "2021-01-01")
    assert aam._price_cache_is_fresh({"created_at_utc": "2099-01-01T00:00:00+00:00"}, 24)
    assert not aam._price_cache_is_fresh({"created_at_utc": "2000-01-01T00:00:00+00:00"}, 24)
