from __future__ import annotations

from pathlib import Path

from analytics.r3_ops_gates import run_pilot_test_suite, start_h1_monitor


def test_pilot_test_suite_runs() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = run_pilot_test_suite(root)
    assert "ok" in doc
    assert doc.get("exit_code") is not None


def test_h1_monitor_start() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = start_h1_monitor(root)
    assert "ok" in doc
