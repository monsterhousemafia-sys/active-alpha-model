"""Operational setup (scheduler fallback, watch-loop pid)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_operational_setup_json_written():
    from tools.r0_migration_operational_setup import run_operational_setup

    result = run_operational_setup(ROOT, start_watch_loop=False)
    path = ROOT / "evidence" / "r0_migration" / "operational_setup.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "steps" in data
    assert "blockers_remaining" in result


def test_watch_loop_singleton_module():
    from tools.run_r0_migration_watch_loop import PID_FILE

    assert PID_FILE.parent.name == "r0_migration"
