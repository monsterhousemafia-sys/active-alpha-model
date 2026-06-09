"""Mirror — Vorbestellungs-Status auf /r3."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_mirror_state import _collect_deferred_package_status, build_exec_mirror_state


def test_collect_deferred_package_status_complete(tmp_path: Path) -> None:
    queue = tmp_path / "live_pilot/confirmed_execution/us_equity_deferred_intents.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "intents": [
                    {"instrument": "STX", "status": "pending", "source": "R3_DESKTOP"},
                    {"instrument": "SPY", "status": "pending", "source": "R3_DESKTOP"},
                ],
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "execution.confirmed_live.us_equity_deferred_intents.list_pending_r3_intents",
        return_value=[
            {"instrument": "STX", "status": "pending"},
            {"instrument": "SPY", "status": "pending"},
        ],
    ):
        st = _collect_deferred_package_status(tmp_path, {"STX", "SPY"})
    assert st.get("active") is True
    assert st.get("complete") is True
    assert st.get("pending_count") == 2


def test_mirror_state_includes_deferred(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    for name in (
        "r3_stock_orders_latest.json",
        "r3_freigabe_latest.json",
        "r3_order_batch_latest.json",
        "r3_t212_bond_latest.json",
        "r3_snapshot_latest.json",
        "r3_plan_latest.json",
        "r3_reeval_latest.json",
        "r3_king_follow_on_latest.json",
        "r3_trading_cycle_latest.json",
        "r3_closed_loop_latest.json",
        "r3_background_engine_latest.json",
        "r3_kreis_score_latest.json",
        "r3_refresh_latest.json",
        "stack_integrity_latest.json",
    ):
        (tmp_path / "evidence" / name).write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/r3_stock_orders_latest.json").write_text(
        json.dumps(
            {
                "stocks": [{"symbol": "STX", "side": "BUY", "notional_eur": 100.0}],
                "initial_package": {"active": True, "notional_eur": 100.0},
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_mirror_state._collect_deferred_package_status",
        return_value={
            "active": True,
            "pending_count": 1,
            "want_count": 1,
            "complete": True,
            "headline_de": "Vorbestellt 1/1",
        },
    ):
        doc = build_exec_mirror_state(tmp_path)
    assert doc.get("deferred_package", {}).get("active") is True
    assert doc.get("execution_package", {}).get("deferred_status", {}).get("complete") is True
