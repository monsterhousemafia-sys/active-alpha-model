"""R3 Vorbestellung — atomar, idempotent, fail-closed."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_stock_orders import (
    _enqueue_r3_package_deferred,
    submit_r3_initial_package,
)
from execution.confirmed_live.us_equity_deferred_intents import (
    cancel_pending_intents,
    default_policy,
    enqueue_intent_for_symbol,
    list_pending_r3_intents,
    r3_package_pending_status,
    save_policy,
)
from tests.r3_order_fixtures import seed_orders_stack


def _seed(tmp_path: Path) -> None:
    seed_orders_stack(tmp_path)
    save_policy(tmp_path, default_policy())
    (tmp_path / "paper/p16d/fx_observation_ledger").mkdir(parents=True, exist_ok=True)
    (tmp_path / "paper/p16d/fx_observation_ledger/fx_observations.jsonl").write_text(
        json.dumps({"usd_to_eur_rate": 0.86, "usd_fx_quality_gate": "PASS"}) + "\n",
        encoding="utf-8",
    )


def test_atomic_rollback_on_partial_enqueue(tmp_path: Path) -> None:
    _seed(tmp_path)
    rows = [
        {"symbol": "STX", "side": "BUY", "notional_eur": 320.0},
        {"symbol": "SPY", "side": "BUY", "notional_eur": 320.0},
    ]
    plan = {
        "champion_id": "R3",
        "signal_date": "2026-06-05",
        "allocations": [
            {"symbol": "STX", "target_eur": 320.0},
            {"symbol": "SPY", "target_eur": 320.0},
        ],
    }

    def _enqueue(root, **kwargs):
        sym = kwargs.get("symbol")
        if sym == "STX":
            return {
                "ok": True,
                "symbol": sym,
                "intent": {"intent_id": "id-stx", "instrument": sym, "status": "PENDING"},
            }
        return {"ok": False, "symbol": sym, "error": "NO_DEFERRED_LIMIT"}

    with patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_deferred",
        return_value=40.0,
    ), patch(
        "analytics.r3_stock_orders._plan_for_deferred",
        return_value=plan,
    ), patch(
        "execution.confirmed_live.us_equity_deferred_intents.enqueue_intent_for_symbol",
        side_effect=_enqueue,
    ), patch(
        "execution.confirmed_live.us_equity_deferred_intents.cancel_pending_intents",
        wraps=cancel_pending_intents,
    ) as mock_cancel:
        out = _enqueue_r3_package_deferred(tmp_path, rows, quote_snapshot={})

    assert out["ok"] is False
    assert out.get("atomic_abort") is True
    mock_cancel.assert_called_once()
    assert list_pending_r3_intents(tmp_path) == []


def test_idempotent_reenqueue_when_complete(tmp_path: Path) -> None:
    _seed(tmp_path)
    plan = {
        "champion_id": "R3",
        "signal_date": "2026-06-05",
        "allocations": [{"symbol": "STX", "target_eur": 320.0}],
    }
    enqueue_intent_for_symbol(
        tmp_path,
        plan=plan,
        symbol="STX",
        target_notional_eur=320.0,
        limit_price_eur=40.0,
        source="R3_DESKTOP",
    )
    rows = [{"symbol": "STX", "side": "BUY", "notional_eur": 320.0}]
    with patch(
        "analytics.r3_stock_orders._plan_for_deferred",
        return_value=plan,
    ), patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_deferred",
        return_value=40.0,
    ):
        out = _enqueue_r3_package_deferred(tmp_path, rows, quote_snapshot={})
    assert out["ok"] is True
    assert out.get("already_queued") is True
    assert len(list_pending_r3_intents(tmp_path)) == 1


def test_execute_deferred_requires_live_submit(tmp_path: Path) -> None:
    _seed(tmp_path)
    plan = {"allocations": [{"symbol": "STX", "target_eur": 320.0}], "signal_date": "2026-06-05"}
    enqueue_intent_for_symbol(
        tmp_path,
        plan=plan,
        symbol="STX",
        target_notional_eur=320.0,
        limit_price_eur=40.0,
        source="R3_DESKTOP",
    )
    from execution.confirmed_live.us_equity_deferred_intents import execute_pending_r3_deferred_intents

    with patch("analytics.r3_mirror_state.resolve_submission_mode", return_value={"live_submit": False}):
        out = execute_pending_r3_deferred_intents(tmp_path, symbols={"STX"})
    assert out["ok"] is False
    assert out.get("error") == "LIVE_SUBMIT_BLOCKED"


def test_package_status_exact_match(tmp_path: Path) -> None:
    _seed(tmp_path)
    plan = {
        "allocations": [
            {"symbol": "STX", "target_eur": 320.0},
            {"symbol": "SPY", "target_eur": 320.0},
        ],
        "signal_date": "2026-06-05",
    }
    enqueue_intent_for_symbol(
        tmp_path, plan=plan, symbol="STX", target_notional_eur=320.0, limit_price_eur=40.0, source="R3_DESKTOP"
    )
    st = r3_package_pending_status(tmp_path, {"STX", "SPY"})
    assert st["complete"] is False
    assert "SPY" in st["missing_symbols"]


@patch("analytics.r3_freigabe.auto_prepare_freigabe_for_desktop", return_value={"package_ready": True})
@patch("analytics.r3_stock_orders._try_execute_pending_r3_deferred", return_value=None)
@patch("analytics.r3_stock_orders._live_submit_ready", return_value=False)
@patch("analytics.r3_stock_orders._precheck_order_rows", return_value={"ok": False, "failures": [], "quote_snapshot": {}})
@patch("execution.confirmed_live.us_equity_deferred_intents.limit_price_for_deferred", return_value=42.0)
def test_submit_writes_deferred_evidence(
    _mock_price,
    _mock_precheck,
    _mock_live,
    _mock_exec,
    _mock_auto,
    tmp_path: Path,
) -> None:
    from analytics.r3_trading_functions import build_r3_trading_functions
    from analytics.r3_stock_orders import refresh_stock_order_evidence

    _seed(tmp_path)
    build_r3_trading_functions(tmp_path, persist=True)
    refresh_stock_order_evidence(tmp_path)
    out = submit_r3_initial_package(tmp_path, confirmed=True)
    assert out["ok"] is True
    assert (tmp_path / "evidence/r3_package_deferred_latest.json").is_file()
