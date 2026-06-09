from __future__ import annotations

import json
from pathlib import Path

from analytics.operator_visibility import (
    build_visibility_snapshot,
    load_operator_action_lines,
    load_scheduled_timers,
)


def test_visibility_snapshot(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/linux_operator_scope.json").write_text(
        json.dumps({"approved_levels": ["A", "B", "C", "D"], "max_level": "D", "levels": {}}),
        encoding="utf-8",
    )
    (tmp_path / "control/linux_operator_timers.json").write_text(
        json.dumps({"timers": [{"label_de": "Learn", "schedule_de": "22:20", "command": "learn"}]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/linux_operator_actions.jsonl").write_text(
        json.dumps({"at_utc": "2026-06-06T10:00:00", "level": "A", "action": "test", "result": "OK", "agent": "Auto"})
        + "\n",
        encoding="utf-8",
    )
    snap = build_visibility_snapshot(tmp_path)
    assert snap.get("headline_de")
    assert load_scheduled_timers(tmp_path)
    assert load_operator_action_lines(tmp_path)
