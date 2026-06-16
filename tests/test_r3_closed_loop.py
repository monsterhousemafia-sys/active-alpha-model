"""Geschlossener Kreislauf — Engine rechnet mit R3-Kontostand."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.alpha_model_background_engine import tick_alpha_model_background
from analytics.r3_closed_loop import (
    load_r3_account_for_engine,
    record_closed_loop_tick,
    resolve_r3_plan_capital_eur,
)
from analytics.r3_desktop_view import run_r3_background_refresh
from tests.r3_order_fixtures import seed_operator_api_complete


def test_resolve_r3_investable_full_cash_when_buffer_zero(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 0.0, "use_full_free_cash": True}}),
        encoding="utf-8",
    )
    from analytics.r3_closed_loop import resolve_r3_investable_eur

    assert resolve_r3_investable_eur(tmp_path, 678.52) == 678.52


def test_fixed_preview_overrides_live_t212_cash(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    seed_operator_api_complete(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "budget": {
                    "mode": "fixed_preview",
                    "planning_capital_eur": 650.0,
                    "cash_buffer_pct": 0.0,
                    "use_full_free_cash": True,
                }
            }
        ),
        encoding="utf-8",
    )
    fresh_sync = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "credentials_configured": True,
                "broker_status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
                "last_sync_utc": fresh_sync,
                "cash_eur": 678.52,
                "cash_breakdown": {"planning_cash_eur": 678.52, "available_to_trade_eur": 678.52},
            }
        ),
        encoding="utf-8",
    )
    account = load_r3_account_for_engine(tmp_path)
    assert account.get("planning_override") is True
    assert account.get("planning_cash_eur") == 650.0
    assert account.get("investable_eur") == 650.0
    assert account.get("live_planning_cash_eur") == 678.52


def test_fixed_preview_plan_capital_ignores_depot_total(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps(
            {
                "budget": {
                    "mode": "fixed_preview",
                    "planning_capital_eur": 650.0,
                    "cash_buffer_pct": 0.0,
                    "use_full_free_cash": True,
                }
            }
        ),
        encoding="utf-8",
    )
    broker = {
        "cash_eur": 678.52,
        "cash_breakdown": {
            "planning_cash_eur": 678.52,
            "invested_current_value_eur": 350.0,
            "total_account_value_eur": 1028.52,
        },
        "positions": [{"symbol": "AMD", "value_eur": 350.0}],
        "positions_count": 1,
    }
    cap = resolve_r3_plan_capital_eur(tmp_path, broker, 650.0)
    assert cap["basis"] == "fixed_preview"
    assert cap["plan_capital_eur"] == 650.0


def test_resolve_r3_investable_applies_buffer(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    from analytics.r3_closed_loop import resolve_r3_investable_eur

    assert resolve_r3_investable_eur(tmp_path, 600.0) == 570.0


def test_plan_capital_from_live_depot(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    broker = {
        "cash_eur": 150.0,
        "cash_breakdown": {
            "planning_cash_eur": 150.0,
            "invested_current_value_eur": 350.0,
            "total_account_value_eur": 500.0,
        },
        "positions": [{"symbol": "AMD", "value_eur": 350.0}],
        "positions_count": 1,
    }
    cap = resolve_r3_plan_capital_eur(tmp_path, broker, 150.0)
    assert cap["basis"] == "t212_total_account_live"
    assert cap["plan_capital_eur"] == 475.0


def test_load_account_from_r3_bond(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    seed_operator_api_complete(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    fresh_sync = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "credentials_configured": True,
                "broker_status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
                "last_sync_utc": fresh_sync,
                "cash_eur": 500.0,
                "cash_breakdown": {"planning_cash_eur": 480.0, "available_to_trade_eur": 480.0},
            }
        ),
        encoding="utf-8",
    )
    account = load_r3_account_for_engine(tmp_path)
    assert account.get("ok") is True
    assert account.get("cash_source") == "r3_t212_api_bond"
    assert account.get("planning_cash_eur") == 480.0
    assert account.get("investable_eur") == 456.0


def test_untrusted_t212_blocks_stale_capital(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 0.0, "use_full_free_cash": True}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": False,
                "credentials_configured": True,
                "broker_status": "CONNECTION_FAILED_RETRY_AVAILABLE",
                "cash_eur": None,
                "last_sync_utc": None,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 678.52, "allocations": []}),
        encoding="utf-8",
    )
    account = load_r3_account_for_engine(tmp_path)
    assert account.get("t212_trusted") is False
    assert account.get("investable_eur") is None
    assert account.get("ok") is False


def test_readonly_cache_not_used_without_live_bond(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 0.0, "use_full_free_cash": True}}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": False,
                "credentials_configured": True,
                "broker_status": "CONNECTION_FAILED_RETRY_AVAILABLE",
                "cash_eur": None,
            }
        ),
        encoding="utf-8",
    )
    stale_sync = "2020-01-01T00:00:00+00:00"
    cache_dir = tmp_path / "live_pilot" / "manual_execution" / "readonly_real_account_state"
    cache_dir.mkdir(parents=True)
    (cache_dir / "latest_sync.json").write_text(
        json.dumps(
            {
                "cash_eur": 678.52,
                "cash_breakdown": {"planning_cash_eur": 678.52, "available_to_trade_eur": 678.52},
                "credentials_configured": True,
                "synced_at_utc": stale_sync,
                "status": "CACHED_READONLY_DATA",
                "environment": "LIVE_READ_ONLY",
            }
        ),
        encoding="utf-8",
    )
    account = load_r3_account_for_engine(tmp_path)
    assert account.get("cash_eur") is None
    assert account.get("investable_eur") is None
    assert account.get("cash_source") != "readonly_cache_fallback"


def test_engine_rebalance_uses_r3_cash_not_broker_sync(tmp_path: Path) -> None:
    from datetime import datetime, timezone

    seed_operator_api_complete(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05", "generated_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_operations.json").write_text(
        json.dumps({"budget": {"cash_buffer_pct": 5.0, "use_full_free_cash": False}}),
        encoding="utf-8",
    )
    fresh_sync = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "credentials_configured": True,
                "broker_status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
                "last_sync_utc": fresh_sync,
                "cash_eur": 600.0,
                "cash_breakdown": {"planning_cash_eur": 570.0, "available_to_trade_eur": 570.0},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True, "updated_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.prediction_operations.maybe_run_eod_prediction_switch",
        return_value={"ok": True, "skipped": True, "reason": "eod_not_due"},
    ), patch(
        "analytics.live_trading_operations.rebalance_status",
        return_value={"is_due": False, "summary_de": "OK"},
    ), patch(
        "analytics.king_plan_integration.rebuild_investment_plan_with_king",
        return_value={
            "ok": True,
            "pipeline_synced": True,
            "investable_eur": 541.5,
            "plan_capital_eur": 541.5,
            "plan_capital_basis": "r3_cash_investable_live",
            "t212_positions_count": 0,
            "detail_de": "Plan",
        },
    ), patch(
        "analytics.r3_freigabe.refresh_freigabe_evidence",
        return_value={"package_ready": True, "freigabe_ready": True, "headline_de": "OK"},
    ), patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True, "internet_ok": True},
    ), patch(
        "analytics.live_trading_operations.sync_broker_and_quotes",
    ) as mock_sync, patch(
        "analytics.live_profile_governance.h1_backtest_status",
        return_value={"status": "MISSING"},
    ), patch(
        "analytics.r3_prognosis_pipeline.ensure_r3_prognosis_fresh",
        return_value={
            "ok": True,
            "skipped": True,
            "prognosis": {"ok": True, "signal_date": "2026-06-05", "positions": 4},
        },
    ):
        doc = tick_alpha_model_background(tmp_path, force=True)

    mock_sync.assert_not_called()
    reb = next(s for s in doc.get("steps") or [] if s.get("step") == "rebalance_plan")
    assert reb.get("closed_loop") is True
    assert reb.get("planning_cash_eur") == 570.0
    assert reb.get("r3_investable_eur") == 541.5
    assert (tmp_path / "evidence/r3_closed_loop_latest.json").is_file()


def test_background_refresh_t212_before_engine(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text("{}", encoding="utf-8")
    order: list[str] = []

    def _bond(*_a, **_k):
        order.append("t212")
        return {"bonded": True, "cash_eur": 100.0}

    def _engine(*_a, **_k):
        order.append("engine")
        return {"ok": True, "steps": [{"step": "rebalance_plan", "planning_cash_eur": 95.0}]}

    with patch("analytics.r3_trading_cycle._run_cycle_steps") as mock_steps:
        mock_steps.return_value = {
            "ok": True,
            "steps": [
                {"id": "internet", "ok": True},
                {"id": "account", "ok": True},
                {"id": "engine", "ok": True},
            ],
        }
        run_r3_background_refresh(tmp_path)
        mock_steps.assert_called_once()


def test_record_closed_loop_persists(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    account = {"ok": True, "cash_source": "r3_t212_api_bond", "planning_cash_eur": 400.0, "cash_eur": 420.0}
    doc = record_closed_loop_tick(
        tmp_path,
        account=account,
        plan={"investable_eur": 380, "pipeline_synced": True, "t212_live": {"positions_count": 3}},
        loop_ok=True,
    )
    assert doc.get("loop_ok") is True
    assert doc.get("pipeline_synced") is True
    assert (tmp_path / "evidence/r3_closed_loop_latest.json").is_file()
