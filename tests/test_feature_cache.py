from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import active_alpha_model as aam


def test_fingerprint_changes_with_horizon():
    fp10 = aam._feature_build_fingerprint(aam.BacktestConfig(horizon=10), 500)
    fp21 = aam._feature_build_fingerprint(aam.BacktestConfig(horizon=21), 500)
    assert fp10 != fp21


def test_missing_cache_reports_reason():
    pack, reason = aam._try_load_feature_cache(Path("__missing_feature_cache_dir__"), aam.BacktestConfig(), 1)
    assert pack is None
    assert reason == "missing_files"


def test_schema_version_mismatch(tmp_path: Path):
    feat_path, ret_path, meta_path = aam._feature_cache_paths(tmp_path)
    features = pd.DataFrame({"date": pd.to_datetime(["2024-01-01"]), "ticker": ["AAPL"], "close": [100.0]})
    returns = pd.DataFrame({"AAPL": [0.01]}, index=pd.to_datetime(["2024-01-01"]))
    features.to_parquet(feat_path, index=False)
    returns.to_parquet(ret_path)
    meta_path.write_text(
        json.dumps({"schema_version": 1, "fingerprint": "stale", "rows": 1}),
        encoding="utf-8",
    )
    pack, reason = aam._try_load_feature_cache(tmp_path, aam.BacktestConfig(), 1)
    assert pack is None
    assert reason is not None and reason.startswith("schema_version")


def test_cache_roundtrip(tmp_path: Path):
    cfg = aam.BacktestConfig(start="2020-01-01", horizon=10, membership_mode="off")
    features = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-01-01", "2020-01-02"]),
            "ticker": ["AAPL", "AAPL"],
            "close": [100.0, 101.0],
        }
    )
    returns = pd.DataFrame(
        {"AAPL": [0.01, 0.02], "SPY": [0.005, 0.006]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    aam._save_feature_cache(tmp_path, cfg, 1, features, returns)
    pack, reason = aam._try_load_feature_cache(tmp_path, cfg, 1)
    assert reason is None
    assert pack is not None
    loaded_features, _bench_close, loaded_returns = pack
    assert len(loaded_features) == 2
    assert len(loaded_returns) == 2
    meta = json.loads((tmp_path / "feature_cache_meta.json").read_text(encoding="utf-8"))
    assert meta["schema_version"] == aam.FEATURE_CACHE_SCHEMA_VERSION


def test_membership_file_affects_fingerprint(tmp_path: Path):
    membership_a = tmp_path / "membership_a.csv"
    membership_b = tmp_path / "membership_b.csv"
    pd.DataFrame([{"ticker": "AAPL", "valid_from": "2020-01-01", "valid_to": "", "source": "t", "reason": "t"}]).to_csv(
        membership_a, index=False
    )
    pd.DataFrame([{"ticker": "MSFT", "valid_from": "2020-01-01", "valid_to": "", "source": "t", "reason": "t"}]).to_csv(
        membership_b, index=False
    )
    cfg_a = aam.BacktestConfig(membership_file=str(membership_a))
    cfg_b = aam.BacktestConfig(membership_file=str(membership_b))
    assert aam._feature_build_fingerprint(cfg_a, 10) != aam._feature_build_fingerprint(cfg_b, 10)
