"""Dashboard controls must stay operable while data loads."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ui.live_trading_dashboard import service as dash


def test_refresh_snapshot_timeout_keeps_partial_state(tmp_path: Path) -> None:
    def slow(_root: Path, *, force_quotes: bool = True, force_sync: bool = True) -> dict:
        time.sleep(2.0)
        return {"live_enabled": True, "traffic": "GRUEN", "broker": {"cash_eur": 100.0}}

    with patch.object(dash, "_refresh_snapshot_impl", side_effect=slow):
        snap = dash.refresh_snapshot(tmp_path, timeout_s=0.2)
    assert snap.get("warning") or snap.get("error")
    assert snap.get("broker", {}).get("cash_eur") == 100.0


def test_window_refresh_does_not_disable_buttons_in_source() -> None:
    src = (Path(__file__).resolve().parents[1] / "ui" / "live_trading_dashboard" / "window.py").read_text(
        encoding="utf-8"
    )
    assert "_set_action_busy" in src
    assert "_ensure_controls_operable" in src
    assert "action_finished" in src
    assert "refresh_finished" in src
    refresh_block = src.split("def _refresh_ui", 1)[1].split("def _apply_snapshot", 1)[0]
    assert "setEnabled(not busy)" not in refresh_block
    assert "setEnabled(False)" not in refresh_block
