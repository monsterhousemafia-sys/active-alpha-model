"""Tests every interactive cockpit function (same code path as Marktanalyse.exe)."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def cockpit_win(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    monkeypatch.setenv("AA_OFFLINE_COCKPIT_TEST", "1")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow

    QApplication.instance() or QApplication([])
    return InteractiveCockpitWindow(tmp_path)


def test_full_function_matrix(cockpit_win):
    from ui.interactive_cockpit.exe_function_test_harness import run_full_function_matrix

    report = run_full_function_matrix(cockpit_win)
    assert report["overall"] == "PASS", report.get("failures")
    assert report["passed"] == report["total"]
    assert report["nav_view_count"] == len(__import__("ui.interactive_cockpit.main_window", fromlist=["NAV_ITEMS"]).NAV_ITEMS)
