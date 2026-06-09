from __future__ import annotations

import pandas as pd
import pytest

import active_alpha_model as aam


def test_allocate_with_caps_respects_limits(allocator_cfg, allocator_candidates, allocator_raw):
    weights = aam.allocate_with_caps(allocator_candidates, allocator_raw, allocator_cfg, target_exposure=1.0)
    aam.validate_weights(weights, allocator_candidates, allocator_cfg, context="test_allocation")
    diag = aam.portfolio_diagnostics(weights, allocator_candidates, allocator_cfg)
    assert diag["max_issuer_weight"] <= allocator_cfg.max_issuer + 1e-8
    assert diag["max_sector_weight"] <= allocator_cfg.max_sector + aam.VALIDATION_TOL
    assert diag["max_correlation_cluster_weight"] <= allocator_cfg.max_correlation_cluster + aam.VALIDATION_TOL
    assert diag["max_position_weight"] <= allocator_cfg.max_position + aam.VALIDATION_TOL
    assert diag["portfolio_beta"] <= allocator_cfg.max_portfolio_beta + 1e-6
    assert diag["portfolio_exposure"] <= allocator_cfg.max_gross_exposure + aam.VALIDATION_TOL


def test_allocate_with_caps_subset_raw_index(allocator_cfg):
    """Naive baselines pass a subset raw Series; group caps must not KeyError."""
    candidates = pd.DataFrame(
        {
            "ticker": ["AMZN", "HD", "LOW", "BKNG", "EBAY", "NKE", "TJX", "MSFT"],
            "sector": ["Consumer Cyclical"] * 7 + ["Technology"],
            "issuer": ["AMZN", "HD", "LOW", "BKNG", "EBAY", "NKE", "TJX", "MSFT"],
            "correlation_cluster": ["C1"] * 8,
            "beta_252": [1.1] * 8,
        }
    )
    raw = pd.Series(
        [5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5],
        index=["AMZN", "HD", "LOW", "BKNG", "EBAY", "NKE", "TJX"],
    )
    weights = aam.allocate_with_caps(candidates, raw, allocator_cfg, target_exposure=0.85)
    aam.validate_weights(weights, candidates, allocator_cfg, context="subset_raw_index")
    assert weights.sum() <= 0.85 + aam.VALIDATION_TOL


def test_trade_controls_preserve_valid_weights(allocator_candidates):
    cfg = aam.BacktestConfig(max_position=0.075, max_issuer=0.10, max_sector=0.25, max_correlation_cluster=0.20, max_portfolio_beta=0.60)
    raw = pd.Series([10, 9, 8, 7, 6, 5, 4, 3], index=allocator_candidates["ticker"])
    prev = aam.allocate_with_caps(allocator_candidates, raw, cfg, target_exposure=1.0)
    target = prev.sample(frac=1.0, random_state=1)
    trade_cfg = aam.BacktestConfig(no_trade_band=0.01, weight_smoothing=0.5, max_turnover=0.10)
    controlled = aam.apply_trade_controls(target, prev, allocator_candidates, trade_cfg)
    aam.validate_weights(controlled, allocator_candidates, trade_cfg, context="test_trade_controls")


def test_beta_drift_repair():
    drift_snapshot = pd.DataFrame(
        {
            "ticker": ["HIGH", "LOW"],
            "sector": ["Technology", "Utilities"],
            "issuer": ["HIGH", "LOW"],
            "beta_252": [2.0, 0.0],
        }
    )
    drift_cfg = aam.BacktestConfig(
        max_position=1.0,
        max_issuer=1.0,
        max_sector=1.0,
        max_portfolio_beta=0.50,
        no_trade_band=0.0,
        weight_smoothing=0.10,
        max_turnover=0.10,
    )
    invalid_prev = pd.Series({"HIGH": 0.40, "LOW": 0.60})
    valid_target = pd.Series({"HIGH": 0.00, "LOW": 1.00})
    repaired = aam.apply_trade_controls(valid_target, invalid_prev, drift_snapshot, drift_cfg)
    aam.validate_weights(repaired, drift_snapshot, drift_cfg, context="test_beta_drift_repair")


def test_cluster_drift_repair():
    cluster_snapshot = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "sector": ["Technology", "Technology", "Utilities"],
            "issuer": ["A", "B", "C"],
            "correlation_cluster": ["CLUSTER", "CLUSTER", "LOW"],
            "beta_252": [1.0, 1.0, 0.2],
        }
    )
    cluster_cfg = aam.BacktestConfig(
        max_position=1.0,
        max_issuer=1.0,
        max_sector=1.0,
        max_correlation_cluster=0.30,
        max_portfolio_beta=0.0,
        no_trade_band=0.0,
        weight_smoothing=0.10,
        max_turnover=0.05,
    )
    invalid_prev = pd.Series({"A": 0.20, "B": 0.20, "C": 0.60})
    valid_target = pd.Series({"A": 0.10, "B": 0.20, "C": 0.70})
    repaired = aam.apply_trade_controls(valid_target, invalid_prev, cluster_snapshot, cluster_cfg)
    aam.validate_weights(repaired, cluster_snapshot, cluster_cfg, context="test_cluster_drift_repair")


def test_overexposure_repair():
    exposure_snapshot = pd.DataFrame(
        {
            "ticker": ["A", "B", "C"],
            "sector": ["Technology", "Financials", "Utilities"],
            "issuer": ["A", "B", "C"],
            "correlation_cluster": ["A", "B", "C"],
            "beta_252": [1.0, 1.0, 0.4],
        }
    )
    exposure_cfg = aam.BacktestConfig(
        max_position=1.0,
        max_issuer=1.0,
        max_sector=1.0,
        max_correlation_cluster=1.0,
        max_portfolio_beta=0.0,
        max_gross_exposure=1.0,
        no_trade_band=0.0,
        weight_smoothing=0.10,
        max_turnover=0.10,
    )
    overexposed_prev = pd.Series({"A": 0.70, "B": 0.50, "C": 0.20})
    valid_target = pd.Series({"A": 0.40, "B": 0.40, "C": 0.20})
    repaired = aam.apply_trade_controls(valid_target, overexposed_prev, exposure_snapshot, exposure_cfg)
    aam.validate_weights(repaired, exposure_snapshot, exposure_cfg, context="test_exposure_repair")
    assert repaired.sum() <= exposure_cfg.max_gross_exposure + aam.VALIDATION_TOL


def test_first_rebalance_not_suppressed_by_controls():
    initial_cfg = aam.BacktestConfig(
        max_position=0.20,
        max_issuer=0.50,
        max_sector=1.0,
        max_correlation_cluster=1.0,
        max_portfolio_beta=0.0,
        no_trade_band=0.06,
        weight_smoothing=0.50,
        max_turnover=0.08,
    )
    initial_snapshot = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E"],
            "sector": ["S1", "S2", "S3", "S4", "S5"],
            "issuer": ["A", "B", "C", "D", "E"],
            "correlation_cluster": ["A", "B", "C", "D", "E"],
            "beta_252": [1, 1, 1, 1, 1],
        }
    )
    initial_target = pd.Series({"A": 0.20, "B": 0.20, "C": 0.20, "D": 0.20, "E": 0.20})
    first_trade = aam.apply_trade_controls(initial_target, pd.Series(dtype=float), initial_snapshot, initial_cfg)
    assert first_trade.sum() > 0.95


def test_tail_pruning():
    tail_cfg = aam.BacktestConfig(
        top_k=2,
        hold_rank_multiple=1.0,
        max_position=0.50,
        max_issuer=0.50,
        max_sector=1.0,
        max_correlation_cluster=1.0,
        max_portfolio_beta=0.0,
        tail_prune_enabled=True,
        residual_weight_floor=0.005,
        max_n_positions_soft=3,
        max_n_positions_hard=4,
        max_tail_reallocation_per_name=0.01,
        tail_reallocation_step=0.005,
        tail_reallocation_rounds=10,
    )
    tail_ranked = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D", "E"],
            "selection_score": [5, 4, 3, 2, 1],
            "alpha_lcb": [0.05, 0.04, 0.03, 0.02, 0.01],
            "sector": ["S1", "S2", "S3", "S4", "S5"],
            "issuer": ["A", "B", "C", "D", "E"],
            "correlation_cluster": ["A", "B", "C", "D", "E"],
            "beta_252": [1, 1, 1, 1, 1],
            "risk_on": [True, True, True, True, True],
        }
    )
    tail_weights = pd.Series({"A": 0.40, "B": 0.30, "C": 0.20, "D": 0.003, "E": 0.002})
    tail_out, tail_diag = aam.apply_tail_pruning(tail_weights, tail_weights, tail_ranked, tail_cfg)
    aam.validate_weights(tail_out, tail_ranked, tail_cfg, context="test_tail_prune")
    assert len(tail_out) <= 4
    assert tail_diag["residual_positions_pruned"] >= 1
