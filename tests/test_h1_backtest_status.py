"""H1 backtest status — process-aware RUNNING detection."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from analytics.live_profile_governance import h1_backtest_status


def test_running_when_process_active(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "validation_runs/20260606T000000Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "features.parquet").write_bytes(b"x")
    (run / "validation_run.log").write_text("bootstrap\n", encoding="utf-8")
    monkeypatch.setattr(
        "analytics.live_profile_governance._h1_backtest_process_active",
        lambda root, r: True,
    )
    doc = h1_backtest_status(tmp_path)
    assert doc["status"] == "RUNNING"
    assert "Path-Simulation" in str(doc.get("detail_de") or "")


def test_complete_when_returns_exist(tmp_path: Path) -> None:
    run = tmp_path / "validation_runs/20260606T000000Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "strategy_daily_returns.csv").write_text("date,strategy_return\n", encoding="utf-8")
    doc = h1_backtest_status(tmp_path)
    assert doc["status"] == "COMPLETE"
