"""Reeval must not apply cash_buffer twice when account_eur is already plan_capital."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.pilot_portfolio_reevaluation import _model_targets_from_champion


def _champion() -> dict:
    return {
        "meta": {"target_exposure": 1.0, "portfolio_exposure": 1.0, "risk_on": True},
        "symbols": {
            "STX": {
                "symbol": "STX",
                "target_weight": 1.0,
                "alpha_lcb": 0.01,
                "mu_hat": 0.01,
                "rank_score": 1.0,
                "eligible": True,
                "sector": "Tech",
            }
        },
    }


def test_no_double_buffer_when_plan_capital_already_net(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    pol = {"max_model_symbols": 15, "cash_buffer_pct": 5.0}
    targets, scaling = _model_targets_from_champion(
        _champion(),
        account_eur=500.0,
        buffer_pct=5.0,
        pol=pol,
        root=tmp_path,
        buffer_already_applied=True,
    )
    assert scaling["investable_eur"] == 500.0
    assert scaling["cash_buffer_pct_applied"] == 0.0
    assert float(targets["STX"]["target_eur_gross"]) == 500.0


def test_buffer_applied_when_not_pre_net(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    pol = {"max_model_symbols": 15, "cash_buffer_pct": 5.0}
    _, scaling = _model_targets_from_champion(
        _champion(),
        account_eur=500.0,
        buffer_pct=5.0,
        pol=pol,
        root=tmp_path,
        buffer_already_applied=False,
    )
    assert scaling["investable_eur"] == 475.0
