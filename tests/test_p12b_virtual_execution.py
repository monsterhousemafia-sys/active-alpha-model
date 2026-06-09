"""P12B virtual execution engine tests."""
from __future__ import annotations

from pathlib import Path

from research.p12b.audit_ledger import read_events, validate_lifecycle
from research.p12b.constants import PAPER_INITIAL_CAPITAL_EUR
from research.p12b.engine import run_virtual_engine_cycle
from research.p12b.portfolio import load_portfolio


def test_p12b_initial_capital_500eur(tmp_path: Path) -> None:
    out = run_virtual_engine_cycle(tmp_path)
    assert out["initial_capital_eur"] == PAPER_INITIAL_CAPITAL_EUR == 500.0
    assert out["simulation_only"] is True
    assert out["broker_order_routing"] is False


def test_p12b_virtual_fills_and_lifecycle(tmp_path: Path) -> None:
    out = run_virtual_engine_cycle(tmp_path)
    assert out["lifecycle"]["has_fill"] is True
    events = read_events(tmp_path)
    assert any(e.get("lifecycle_stage") == "VIRTUAL_FILL_SIMULATED" for e in events)
    assert all(e.get("broker_order_sent") is False for e in events)


def test_p12b_cash_reconciliation(tmp_path: Path) -> None:
    out = run_virtual_engine_cycle(tmp_path)
    assert out["cash_reconciliation"]["reconciled"] is True
    state = load_portfolio(tmp_path)
    assert state.cash_eur >= 0


def test_p12b_no_real_order_routing(tmp_path: Path) -> None:
    out = run_virtual_engine_cycle(tmp_path)
    assert out["broker_order_routing"] is False
    assert out["metrics"]["real_money"] is False
