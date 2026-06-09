"""Tests for competition shadow snapshot."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analytics.competition_shadow import build_competition_shadow_snapshot, write_competition_shadow_snapshot


def test_competition_shadow_overlap(tmp_path: Path) -> None:
    out = tmp_path / "model_output_sp500_pit_t212"
    cache = out / "price_cache"
    cache.mkdir(parents=True)
    dates = pd.date_range("2026-05-28", periods=5, freq="B")
    rows = []
    for d in dates:
        for tk, base in (("AAA", 100.0), ("BBB", 50.0), ("CCC", 80.0)):
            rows.append({"date": d, "ticker": tk, "Close": base * (1.01 if tk == "AAA" else 1.0)})
    pd.DataFrame(rows).to_parquet(cache / "ohlcv_panel.parquet", index=False)
    port = out / "latest_target_portfolio.csv"
    pd.DataFrame(
        [
            {"signal_date": "2026-06-05", "ticker": "AAA", "target_weight": 0.5, "mu_hat": 0.01, "rank_score": 0.9},
            {"signal_date": "2026-06-05", "ticker": "BBB", "target_weight": 0.3, "mu_hat": 0.005, "rank_score": 0.5},
        ]
    ).to_csv(port, index=False)
    doc = build_competition_shadow_snapshot(tmp_path)
    assert doc["signal_date"] == "2026-06-05"
    assert doc["model"]["n_picks"] == 2
    assert "comparison" in doc
    written = write_competition_shadow_snapshot(tmp_path)
    assert (tmp_path / "evidence/competition_shadow_latest.json").is_file()
    assert written["model"]["n_picks"] == 2
