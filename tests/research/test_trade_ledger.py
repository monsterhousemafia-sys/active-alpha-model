"""Trade ledger completeness tests."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.ledger.trade_ledger import build_trade_ledger, validate_trade_ledger

ROOT = Path(__file__).resolve().parents[2]


def test_trade_ledger_includes_sells():
    weights_path = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/rebalance_weights.csv"
    if not weights_path.is_file():
        return
    weights = pd.read_csv(weights_path)
    ledger = build_trade_ledger(weights, strategy_identity_hash="test")
    val = validate_trade_ledger(ledger)
    assert val["ok"]
    assert val["sell_rows"] > 0
    assert val["sell_and_liquidation_present"]


def test_no_only_buy_bug():
    weights_path = ROOT / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12/rebalance_weights.csv"
    if not weights_path.is_file():
        return
    weights = pd.read_csv(weights_path)
    ledger = build_trade_ledger(weights, strategy_identity_hash="test")
    val = validate_trade_ledger(ledger)
    assert not val.get("only_buy_bug_detected", True)
