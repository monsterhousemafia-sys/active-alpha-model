"""Autonomous research observation package tests."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OBS = ROOT / "outgoing_cursor_observation/autonomous_research_acceleration"


def test_observation_package_files():
    required = [
        "cursor_autonomous_research_acceleration_package.zip",
        "CURSOR_AUTONOMOUS_NEXT_ACTION_QUEUE.json",
    ]
    if not OBS.is_dir():
        return
    for name in required:
        assert (OBS / name).is_file(), name


def test_next_action_queue_schema():
    path = OBS / "CURSOR_AUTONOMOUS_NEXT_ACTION_QUEUE.json"
    if not path.is_file():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "tasks" in data
    assert data["tasks"][0].get("can_execute_autonomously") is True
