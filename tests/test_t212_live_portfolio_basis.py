from pathlib import Path
from unittest.mock import patch

from analytics.t212_live_portfolio_basis import (
    build_plan_on_live_basis,
    enrich_broker_from_live_picture,
    resolve_calculation_basis,
)


def test_enrich_broker_from_bond_evidence(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        '{"cash_eur":500.0,"positions":[{"instrument":{"ticker":"STX"},"walletImpact":{"currentValue":150.0}}],'
        '"positions_count":1,"last_sync_utc":"2026-06-09T12:00:00+00:00"}',
        encoding="utf-8",
    )
    out = enrich_broker_from_live_picture(tmp_path, {"cash_eur": None, "positions": []})
    assert out.get("cash_eur") == 500.0
    assert out.get("positions_count") == 1


def test_resolve_calculation_basis_uses_total_depot(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        '{"budget":{"cash_buffer_pct":0.0,"mode":"variable_free_cash"}}',
        encoding="utf-8",
    )
    broker = {
        "cash_eur": 400.0,
        "positions": [{"instrument": {"ticker": "AMD"}, "walletImpact": {"currentValue": 200.0}}],
        "positions_count": 1,
        "credentials_configured": True,
    }
    basis = resolve_calculation_basis(tmp_path, broker, 400.0)
    assert basis.get("calculation_basis") == "t212_total_account_live"
    assert float(basis.get("invested_eur") or 0) == 200.0
    assert float(basis.get("total_account_value_eur") or 0) == 600.0
    assert basis.get("broker_economics")
    assert "ohne Puffer" in (basis.get("basis_de") or "")


def test_build_plan_rebalances_to_live_holdings(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/prediction_operations.json").write_text(
        '{"active_profile":"daily_alpha_h1","budget":{"cash_buffer_pct":0.0,"min_position_eur":25.0}}',
        encoding="utf-8",
    )
    (tmp_path / "control/pilot_day_trading.json").write_text("{}", encoding="utf-8")
    broker = {
        "cash_eur": 300.0,
        "positions": [{"instrument": {"ticker": "STX"}, "walletImpact": {"currentValue": 100.0}}],
        "positions_count": 1,
        "credentials_configured": True,
        "connected": True,
    }
    base_plan = {
        "allocations": [
            {"symbol": "STX", "model_weight_pct": 50.0, "target_eur": 200.0, "alpha_lcb": 0.002},
            {"symbol": "MU", "model_weight_pct": 50.0, "target_eur": 200.0, "alpha_lcb": 0.002},
        ],
        "investable_eur": 400.0,
        "signal_date": "2026-06-09",
    }
    with patch("analytics.pilot_investment_plan.build_investment_plan", return_value=dict(base_plan)), patch(
        "analytics.king_plan_integration.rebalance_plan_to_t212_holdings",
        side_effect=lambda plan, b, r: (
            {
                **plan,
                "rebalanced_to_t212": True,
                "rebalance_mode_de": "gap_vs_live_holdings",
                "allocations": [
                    {
                        "symbol": "MU",
                        "side": "BUY",
                        "target_eur": 150.0,
                        "gap_eur": 150.0,
                        "held_eur": 0.0,
                        "side_de": "Neue Aktie",
                    }
                ],
            },
            {"ok": True, "gap_rows": 1},
        ),
    ):
        plan, meta = build_plan_on_live_basis(tmp_path, broker, planning_cash_eur=300.0)
    assert plan.get("rebalanced_to_t212") is True
    assert (plan.get("t212_live") or {}).get("positions_count") == 1
    assert meta.get("basis", {}).get("calculation_basis") == "t212_total_account_live"
