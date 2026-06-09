"""Gas (Kaufen) + Sell — Steuerung und Gewinn-Hürde."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.gas_sell_steering import (
    apply_gas_sell_steering,
    order_sell_then_gas,
    steer_label,
)


def _base_row(symbol: str, side: str, eur: float, *, score: float = 5.0) -> dict:
    return {
        "symbol": symbol,
        "side": side,
        "notional_eur": eur,
        "priority_score": score,
        "limit_price_eur": 100.0,
        "is_new_position": side == "BUY",
        "sanctioned": True,
        "clickable": True,
        "action_de": "test",
    }


def test_steer_labels() -> None:
    assert steer_label("BUY", is_new=True) == "Gas"
    assert steer_label("BUY", is_new=False) == "Gas+"
    assert steer_label("SELL") == "Sell"


def test_sell_before_gas_order() -> None:
    rows = [
        _base_row("STX", "BUY", 50, score=9),
        _base_row("INTC", "SELL", 30, score=8),
        _base_row("AMD", "BUY", 40, score=7),
    ]
    ordered = order_sell_then_gas(rows)
    assert ordered[0]["symbol"] == "INTC"
    assert ordered[1]["symbol"] == "STX"


@patch("analytics.gas_sell_steering._profit_gate")
def test_apply_steering_marks_gas(mock_gate, tmp_path: Path) -> None:
    mock_gate.return_value = {"ok": True, "profit_ok": True}
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "blockers": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/gas_sell_steering_policy.json").write_text("{}", encoding="utf-8")
    rows = [_base_row("STX", "BUY", 48)]
    out = apply_gas_sell_steering(tmp_path, rows)
    assert out[0]["steering_mode"] == "Gas"
    assert out[0].get("profit_ok") is True
    assert (tmp_path / "evidence/gas_sell_steering_latest.json").is_file()


@patch("analytics.gas_sell_steering._profit_gate")
def test_blocks_when_prediction_not_ok(mock_gate, tmp_path: Path) -> None:
    mock_gate.return_value = {"ok": True, "profit_ok": True}
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": False, "blockers": ["signal_stale"]}),
        encoding="utf-8",
    )
    (tmp_path / "control/gas_sell_steering_policy.json").write_text(
        json.dumps({"require_prediction_ok": True}),
        encoding="utf-8",
    )
    out = apply_gas_sell_steering(tmp_path, [_base_row("STX", "BUY", 48)])
    assert out[0]["sanctioned"] is False
    assert out[0].get("profit_blocked") is True
