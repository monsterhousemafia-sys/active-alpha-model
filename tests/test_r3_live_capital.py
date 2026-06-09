"""Live-Kontostand + lohnende Positionen."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


def _trusted_capital(*, investable: float = 675.0) -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "ok": True,
        "trusted": True,
        "planning_cash_eur": 675.0,
        "investable_eur": investable,
        "cash_eur": 675.0,
        "positions_count": 0,
        "last_sync_utc": now,
        "broker": {
            "cash_eur": 675.0,
            "positions": [],
            "positions_count": 0,
            "last_successful_sync_utc": now,
            "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
            "credentials_configured": True,
            "r3_planning_cash_eur": 675.0,
            "r3_investable_eur": investable,
            "source": "t212_live_sync",
        },
    }


def test_sync_live_capital_untrusted(tmp_path: Path) -> None:
    with patch(
        "analytics.king_plan_integration.sync_t212_realtime_for_plan",
        return_value={"cash_eur": 100.0, "last_sync_utc": "2020-01-01T00:00:00+00:00"},
    ), patch(
        "integrations.trading212.t212_trust_gate.assess_t212_trust_from_root",
        return_value={"trusted": False, "message_de": "veraltet", "reason_code": "STALE_SYNC"},
    ):
        from analytics.r3_live_capital import sync_live_capital_basis

        doc = sync_live_capital_basis(tmp_path, force=True)
    assert doc.get("ok") is False
    assert doc.get("trusted") is False


def test_compute_worthwhile_flat_depot(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 0.0, "use_full_free_cash": True}}),
        encoding="utf-8",
    )
    plan = {
        "allocations": [
            {"symbol": "STX", "model_weight_pct": 6.0, "target_eur": 40.0, "alpha_lcb": 0.002, "rationale_de": "STX ok"},
            {"symbol": "MU", "model_weight_pct": 5.0, "target_eur": 35.0, "alpha_lcb": 0.002, "rationale_de": "MU ok"},
        ],
        "investable_eur": 675.0,
        "available_cash_eur": 675.0,
    }
    reeval = {
        "status": "OK",
        "risk_on": True,
        "signals_ok": True,
        "champion_ok": True,
        "exposure_check": {"under_invested": True},
        "trade_required": True,
        "summary_de": "test",
        "recommended_actions": [],
    }
    with patch("analytics.r3_live_capital.sync_live_capital_basis", return_value=_trusted_capital()), patch(
        "analytics.t212_live_portfolio_basis.build_plan_on_live_basis",
        return_value=(
            {**plan, "rebalanced_to_t212": False, "t212_live": {"positions_count": 0}},
            {"basis": {"positions_count": 0, "calculation_basis": "r3_cash_investable_live", "basis_de": "cash"}},
        ),
    ), patch(
        "analytics.t212_live_portfolio_basis.persist_live_basis_evidence",
    ), patch(
        "analytics.pilot_portfolio_reevaluation.evaluate_live_portfolio_vs_champion",
        return_value=reeval,
    ), patch("analytics.r3_trading_functions.build_r3_trading_functions"):
        from analytics.r3_live_capital import compute_worthwhile_positions

        doc = compute_worthwhile_positions(tmp_path, force_sync=False, persist=True)
    assert doc.get("ok") is True
    assert doc.get("worthwhile_buy_count") == 2
    assert (tmp_path / "evidence/r3_worthwhile_positions_latest.json").is_file()
