"""Paper trading engine unit tests (no live Yahoo)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from paper_trading_engine import load_state, load_target_portfolio, round_half_up_to_increment, safe_float, save_state


def test_round_half_up_to_increment():
    assert round_half_up_to_increment(1.24, 0.01) == 1.24
    assert round_half_up_to_increment(1.235, 0.01) == 1.24


def test_safe_float():
    assert safe_float("1.5") == 1.5
    assert safe_float(None, default=3.0) == 3.0


def test_paper_state_roundtrip(tmp_path: Path):
    paper = tmp_path / "paper"
    paper.mkdir()
    state = load_state(paper, initial_capital=10_000.0, reset=True)
    state["cash"] = 1234.5
    state["equity"] = 10_500.0
    save_state(paper, state)
    loaded = load_state(paper, initial_capital=10_000.0)
    assert float(loaded["cash"]) == 1234.5
    raw = json.loads((paper / "paper_state.json").read_text(encoding="utf-8"))
    assert raw["cash"] == 1234.5


def test_load_target_portfolio(tmp_path: Path):
    path = tmp_path / "latest_target_portfolio.csv"
    pd.DataFrame({"ticker": ["A", "B"], "target_weight": [0.25, 0.25], "signal_date": ["2026-05-29", "2026-05-29"]}).to_csv(path, index=False)
    df, _warnings = load_target_portfolio(path, max_gross_exposure=1.0)
    assert not df.empty
    assert abs(float(df["target_weight"].sum()) - 0.5) < 1e-9
