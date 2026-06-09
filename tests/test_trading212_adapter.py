"""Trading 212 broker adapter tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from research.p13.broker_adapter import get_broker_adapter
from research.p13.brokers.trading212_adapter import Trading212BrokerAdapter
from research.p13.brokers.trading212_config import Trading212Config


@pytest.fixture
def t212_config() -> Trading212Config:
    return Trading212Config(
        api_key="test-key",
        api_secret="test-secret",
        environment="demo",
        read_only=True,
        allow_live_orders=False,
    )


def test_trading212_read_only_blocks_post(t212_config: Trading212Config, tmp_path: Path) -> None:
    adapter = Trading212BrokerAdapter(tmp_path, t212_config)
    with patch.object(adapter.client, "get_account_summary", return_value={"currency": "EUR", "totalValue": 500.0}):
        with patch.object(adapter.client, "get_positions", return_value=[]):
            with patch.object(adapter.client, "get_account_cash", return_value={"free": 500.0}):
                state = adapter.read_only_account_state()
    assert state["account_connected"] is True
    assert state["read_only"] is True
    result = adapter.submit_order({"ticker": "AAPL_US_EQ", "side": "BUY", "shares": 1, "notional_eur": 50, "portfolio_value_eur": 500})
    assert result.routed is False
    assert "READ_ONLY" in result.reason or "KILL_SWITCH" in result.reason


def test_trading212_client_auth_header(t212_config: Trading212Config) -> None:
    from research.p13.brokers.trading212_client import Trading212Client

    client = Trading212Client(t212_config)
    hdr = client._auth_header()
    assert hdr.startswith("Basic ")


def test_get_broker_adapter_without_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TRADING212_API_KEY", raising=False)
    monkeypatch.delenv("TRADING212_API_SECRET", raising=False)
    adapter = get_broker_adapter(tmp_path)
    assert adapter.adapter_name() == "DISABLED_BROKER_ADAPTER_V1"
