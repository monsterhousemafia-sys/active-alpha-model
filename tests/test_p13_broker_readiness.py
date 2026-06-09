"""P13 disabled broker adapter and readiness tests."""
from __future__ import annotations

from pathlib import Path

from research.p13.broker_adapter import DisabledBrokerAdapter, adapter_status, dry_run_order_validation
from research.p13.constants import BROKER_ADAPTER_ENABLED, REAL_MONEY_ENABLED, REAL_ORDER_ROUTING_ENABLED
from research.p13.credentials import assess_credential_isolation
from research.p13.kill_switch import is_trading_blocked, load_kill_switch
from research.p13.readiness import run_readiness_assessment


def test_p13_broker_adapter_disabled_by_default() -> None:
    st = adapter_status(".")
    assert st["broker_adapter_implemented"] is True
    assert st["real_order_routing_enabled"] is False
    assert st["real_money_enabled"] is False
    assert REAL_ORDER_ROUTING_ENABLED is False
    assert REAL_MONEY_ENABLED is False


def test_p13_kill_switch_blocks_routing(tmp_path: Path) -> None:
    ks = load_kill_switch(tmp_path)
    assert ks.get("active") is True
    assert is_trading_blocked(tmp_path) is True
    result = dry_run_order_validation(tmp_path, {"ticker": "SPY", "side": "BUY", "notional_eur": 50, "portfolio_value_eur": 500})
    assert result.routed is False


def test_p13_credential_isolation(tmp_path: Path) -> None:
    iso = assess_credential_isolation(tmp_path)
    assert iso["isolated_by_default"] is True


def test_p13_readiness_assessment(tmp_path: Path) -> None:
    out = run_readiness_assessment(tmp_path)
    assert out["real_order_attempt_blocked"] is True
    assert out["dry_run_oversize_rejected"] is True
    assert out["broker_order_sent"] is False


def test_p13_disabled_adapter_no_submit(tmp_path: Path) -> None:
    adapter = DisabledBrokerAdapter(tmp_path)
    assert adapter.enabled is False
    acct = adapter.read_only_account_state()
    assert acct["account_connected"] is False
    assert acct["balance_eur"] == 0.0
