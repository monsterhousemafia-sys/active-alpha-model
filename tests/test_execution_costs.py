"""Tests for execution cost alignment."""
from __future__ import annotations

from aa_config import BacktestConfig
from aa_execution import effective_alpha_target_roundtrip_decimal


def test_effective_alpha_target_uses_execution_fees():
    cfg = BacktestConfig(
        align_target_cost_with_execution=True,
        slippage_bps=5.0,
        trading212_fx_bps=15.0,
        market_impact_bps=2.0,
    )
    dec = effective_alpha_target_roundtrip_decimal(cfg)
    assert 0.0015 < dec < 0.01


def test_effective_alpha_target_legacy_cost_bps():
    cfg = BacktestConfig(align_target_cost_with_execution=False, cost_bps=20.0)
    dec = effective_alpha_target_roundtrip_decimal(cfg)
    assert abs(dec - 0.004) < 1e-9
