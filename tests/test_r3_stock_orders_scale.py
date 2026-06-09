"""R3 Stock-Orders — Budget-Skalierung auch ohne vorbefüllte notional_eur."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_stock_orders import build_initial_package, build_optimal_stock_actions
from tests.test_r3_stock_orders import _write_flat_context


def test_kernel_rows_without_notional_scale_to_t212_budget(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "investable_eur": 640.93,
                "cash_eur": 674.66,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {"symbol": "STX", "side": "BUY", "sanctioned": True, "priority_score": 9.5},
                    {"symbol": "SPY", "side": "BUY", "sanctioned": True, "priority_score": 8.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = build_optimal_stock_actions(tmp_path)
    buy_sum = sum(float(r["notional_eur"]) for r in rows if r["side"] == "BUY")
    assert abs(buy_sum - 640.93) < 2.0
    pkg = build_initial_package(tmp_path, stocks=rows)
    assert pkg["active"] is True
    assert float(pkg["notional_eur"]) > 0
    assert abs(float(pkg["notional_eur"]) - 640.93) < 2.0
