from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import aa_config as cfg_mod
import active_alpha_model as aam


def test_from_args_maps_cli_defaults(monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["active_alpha_model.py", "--membership-mode", "off"],
    )
    args = cfg_mod.parse_args()
    cfg = cfg_mod.BacktestConfig.from_args(args)
    assert cfg.fee_model == "trading212_us"
    assert cfg.membership_mode == "off"
    assert cfg.top_k == args.top_k
    assert cfg.reuse_feature_cache == bool(args.reuse_feature_cache)


def test_post_init_rejects_invalid_fee_model():
    with pytest.raises(ValueError, match="trading212_us"):
        aam.BacktestConfig(fee_model="ibkr")


def test_post_init_rejects_non_positive_capital():
    with pytest.raises(ValueError, match="positive"):
        aam.BacktestConfig(backtest_capital=0.0)


def test_post_init_rejects_soft_positions_above_hard():
    with pytest.raises(ValueError, match="max_n_positions_soft"):
        aam.BacktestConfig(max_n_positions_soft=40, max_n_positions_hard=30)


def test_post_init_rejects_top_k_above_universe_top_n():
    with pytest.raises(ValueError, match="top_k"):
        aam.BacktestConfig(universe_mode="diy_pit_liquidity", top_k=50, universe_top_n=30)


def test_write_reporting_errors_json(tmp_path: Path):
    errors = [{"step": "factor_proxy_regression", "type": "RuntimeError", "message": "boom"}]
    path = tmp_path / "reporting_errors.json"
    aam.write_reporting_errors_json(path, errors)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["count"] == 1
    assert payload["errors"] == errors
