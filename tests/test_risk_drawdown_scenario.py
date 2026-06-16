"""Risk drawdown scenario — read-only simulation."""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.risk_drawdown_scenario import run_risk_drawdown_scenario


def test_drawdown_scenario_with_returns(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    csv = out / "strategy_daily_returns.csv"
    csv.write_text(
        "date,strategy_return\n"
        "2024-01-02,0.01\n"
        "2024-01-03,-0.02\n"
        "2024-01-04,0.005\n"
        "2024-01-05,-0.03\n"
        "2024-01-08,0.01\n",
        encoding="utf-8",
    )
    doc = run_risk_drawdown_scenario(tmp_path)
    assert doc["ok"] is True
    assert doc["historical_max_drawdown"] < 0
    assert len(doc.get("hypothetical_shocks") or []) == 3
