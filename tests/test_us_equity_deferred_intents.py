"""US equity deferred intent queue — enqueue outside session, process at open."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from execution.confirmed_live.us_equity_deferred_intents import (
    capture_portfolio_change_intent,
    default_policy,
    enqueue_intent,
    list_pending_intents,
    load_policy,
    portfolio_fingerprint,
    process_deferred_intents_if_due,
    save_policy,
    set_user_armed_auto_open,
    try_enqueue_or_execute_now,
)
from integrations.trading212.t212_exchange_session import next_us_regular_session_open_utc


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    save_policy(tmp_path, default_policy())
    from analytics.pilot_day_trading_policy import load_unified_policy, save_unified_policy

    unified = load_unified_policy(tmp_path)
    for key in ("walkforward_mirror", "live_trading"):
        unified[key] = {**(unified.get(key) or {}), "enabled": False}
    save_unified_policy(tmp_path, unified)
    return tmp_path


def _plan(sym: str = "INTC", eur: float = 50.0) -> dict:
    return {
        "champion_id": "R3_w075_q065_noexit",
        "signal_date": "2026-05-30",
        "primary_action": {"symbol": sym, "target_eur": eur},
        "allocations": [{"symbol": sym, "model_weight_pct": 40.0, "target_eur": eur}],
    }


def test_enqueue_outside_session_sets_not_before(root: Path) -> None:
    now = datetime.now(timezone.utc)
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": False, "phase": "CLOSED"},
    ), patch(
        "integrations.trading212.t212_exchange_session.next_us_regular_session_open_utc",
        return_value=next_us_regular_session_open_utc(now=now),
    ):
        r = enqueue_intent(root, plan=_plan(), limit_price_eur=25.0, source="TEST")
    assert r["ok"] is True
    pending = list_pending_intents(root)
    assert len(pending) == 1
    assert pending[0]["instrument"] == "INTC"
    assert pending[0]["execute_not_before_utc"]


def test_portfolio_capture_dedupes_unchanged(root: Path) -> None:
    with patch(
        "analytics.champion_runtime_guard.verify_champion_runtime",
    ) as guard:
        guard.return_value = type(
            "G",
            (),
            {"champion_ok": True, "signals_ok": True},
        )()
        with patch(
            "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
            return_value={"open": False},
        ):
            p = _plan()
            fp = portfolio_fingerprint(p)
            snap_path = root / "live_pilot/confirmed_execution/us_equity_portfolio_snapshot.json"
            snap_path.parent.mkdir(parents=True, exist_ok=True)
            snap_path.write_text(
                json.dumps({"fingerprint": fp}) + "\n",
                encoding="utf-8",
            )
            r1 = capture_portfolio_change_intent(root, p, limit_price_eur=20.0)
            assert r1.get("skipped") == "UNCHANGED"


def test_process_skips_when_not_armed(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AA_ORDER_EXECUTION_TEST_BYPASS", "1")
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        with patch(
            "integrations.trading212.t212_exchange_session.is_within_us_open_execution_window",
            return_value=True,
        ):
            enqueue_intent(root, plan=_plan(), limit_price_eur=22.0, source="TEST")
            report = process_deferred_intents_if_due(root)
    assert "AUTO_EXECUTE_NOT_ARMED" in report.get("skipped", [])


def test_process_skips_auto_when_armed_without_gui_grant(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AA_ORDER_EXECUTION_TEST_BYPASS", "1")
    set_user_armed_auto_open(root, armed=True)
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": True, "phase": "OPEN"},
    ):
        with patch(
            "integrations.trading212.t212_exchange_session.is_within_us_open_execution_window",
            return_value=True,
        ):
            enqueue_intent(root, plan=_plan(), limit_price_eur=22.0, source="TEST")
            report = process_deferred_intents_if_due(root)
    assert "GUI_CONFIRMATION_REQUIRED" in report.get("skipped", [])
    assert report.get("executed", 0) == 0


def test_try_enqueue_mode_deferred_when_closed(root: Path) -> None:
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": False},
    ), patch(
        "execution.confirmed_live.us_equity_deferred_intents.limit_price_for_symbol",
        return_value=21.0,
    ):
        r = try_enqueue_or_execute_now(
            root,
            plan=_plan(),
            limit_price_eur=21.0,
            free_cash_eur=500.0,
        )
    assert r.get("mode") in (
        "deferred",
        "deferred_batch",
        "walkforward_mark_only",
        "mark_only",
        "live_enqueue",
        "live_rebalance",
    )
    assert r.get("ok") is True


def test_load_policy_defaults(root: Path) -> None:
    pol = load_policy(root)
    assert pol["enabled"] is True
    assert pol["user_armed_auto_open_execution"] is False
