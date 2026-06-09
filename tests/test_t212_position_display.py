"""Tests for T212 position display normalization."""
from __future__ import annotations

from integrations.trading212.t212_position_display import normalize_positions_payload, position_table_rows


def test_normalize_list_positions():
    rows = normalize_positions_payload(
        [{"ticker": "OXY_US_EQ", "quantity": 1.5, "currentPrice": 59.0, "currentValue": 88.5}]
    )
    assert rows[0]["symbol"] == "OXY"
    assert rows[0]["quantity"] == 1.5
    assert rows[0]["value_eur"] == 88.5


def test_position_table_rows():
    table = position_table_rows([{"symbol": "WDC", "quantity": 0.15, "value": 71.08, "status": "OK"}])
    assert table[0][0] == "WDC"
    assert "71,08" in table[0][2]
