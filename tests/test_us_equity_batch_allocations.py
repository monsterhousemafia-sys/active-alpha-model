"""Batch enqueue / execute all champion plan allocations."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from execution.confirmed_live.us_equity_deferred_intents import (
    allocations_for_batch,
    enqueue_all_allocations_from_plan,
    list_pending_intents,
    save_policy,
)
from execution.confirmed_live.us_equity_deferred_intents import default_policy


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    save_policy(tmp_path, default_policy())
    return tmp_path


def _multi_plan() -> dict:
    return {
        "champion_id": "R3_w075_q065_noexit",
        "signal_date": "2026-06-01",
        "primary_action": {"symbol": "INTC", "target_eur": 40.0},
        "allocations": [
            {"symbol": "INTC", "target_eur": 40.0},
            {"symbol": "WDC", "target_eur": 50.0},
            {"symbol": "STX", "target_eur": 45.0},
        ],
    }


def test_allocations_for_batch_dedupes() -> None:
    rows = allocations_for_batch(_multi_plan())
    assert [r["symbol"] for r in rows] == ["INTC", "WDC", "STX"]


def test_enqueue_all_outside_session(root: Path) -> None:
    quotes = {
        "executable_prices_eur": {"INTC": 20.0, "WDC": 30.0, "STX": 25.0},
        "freshness": {"status": "FRESH"},
    }
    with patch(
        "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
        return_value={"open": False},
    ):
        with patch(
            "integrations.trading212.t212_fee_economics.is_notional_worth_trading",
            return_value=(True, ""),
        ):
            r = enqueue_all_allocations_from_plan(
                root,
                plan=_multi_plan(),
                quote_snapshot=quotes,
                source="TEST",
            )
    assert r["ok"] is True
    assert r["enqueued"] == 3
    pending = list_pending_intents(root)
    assert len(pending) == 3
    assert {p["instrument"] for p in pending} == {"INTC", "WDC", "STX"}
