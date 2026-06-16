"""Gemeinsame Test-Fixtures für R3 Order-Ausführung."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from tests.test_r3_stock_orders import _write_flat_context


def seed_operator_api_complete(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    from analytics.r3_t212_operator_api import mark_operator_api_setup_complete

    mark_operator_api_setup_complete(tmp_path)


def seed_orders_stack(tmp_path: Path, *, ref: float = 640.93) -> None:
    """Evidence-Stack für Initial-Paket + technische Vorbereitung."""
    seed_operator_api_complete(tmp_path)
    _write_flat_context(tmp_path)
    half = round(ref / 2, 2)
    (tmp_path / "evidence/r3_stock_orders_latest.json").write_text(
        json.dumps(
            {
                "stocks": [
                    {"symbol": "STX", "side": "BUY", "notional_eur": half},
                    {"symbol": "SPY", "side": "BUY", "notional_eur": round(ref - half, 2)},
                ],
                "initial_package": {"active": True, "notional_eur": ref, "budget_eur": ref},
            }
        ),
        encoding="utf-8",
    )
    reeval_path = tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json"
    reeval = json.loads(reeval_path.read_text(encoding="utf-8"))
    reeval["deployable_eur"] = ref
    reeval["account_eur"] = 674.66
    reeval_path.write_text(json.dumps(reeval), encoding="utf-8")
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": ref,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": half, "model_weight_pct": 50.0},
                    {
                        "symbol": "SPY",
                        "side": "BUY",
                        "target_eur": round(ref - half, 2),
                        "model_weight_pct": 50.0,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/gas_sell_steering_latest.json").write_text(
        json.dumps({"on_course": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {"symbol": "STX", "side": "BUY", "sanctioned": True, "priority_score": 9.5},
                    {"symbol": "SPY", "side": "BUY", "sanctioned": True, "priority_score": 8.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    sync_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    bond_doc = {
                "bonded": True,
                "connected": True,
                "credentials_configured": True,
                "broker_status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
                "last_sync_utc": sync_utc,
                "cash_eur": 674.66,
                "investable_eur": ref,
                "account_fingerprint": "testacctseed01",
                "account_label": "T212 LIVE READ ONLY · 675 EUR",
                "connection_label": "T212 LIVE · #testacct",
                "environment": "LIVE_READ_ONLY",
            }
    bond_path = tmp_path / "evidence/r3_t212_api_bond_latest.json"
    bond_path.write_text(json.dumps(bond_doc), encoding="utf-8")
    from analytics.r3_t212_account_identity import confirm_t212_account

    confirm_t212_account(tmp_path, bond=bond_doc)
    (tmp_path / "evidence/pilot_trading_day_warnings_latest.json").write_text(
        json.dumps(
            {
                "warnings": {
                    "must_resolve_before_trading": False,
                    "critical_count": 0,
                    "us_session_open": True,
                    "headline_de": "Keine kritischen Warnungen",
                },
                "traffic": "GRUEN",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/ai_kernel_ready_latest.json").write_text(
        json.dumps({"ready": True, "blockers": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/closed_loop_score_latest.json").write_text(
        json.dumps({"pct": 33, "tag": "AUFBAU", "stages": []}),
        encoding="utf-8",
    )
