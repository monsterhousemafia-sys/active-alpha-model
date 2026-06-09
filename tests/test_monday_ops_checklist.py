from __future__ import annotations

import json
from pathlib import Path

from analytics.monday_ops_checklist import checklist_items_de, write_monday_checklist_to_activity_log


def test_checklist_writes_activity(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    items = checklist_items_de(tmp_path)
    assert any("Rebalance" in x for x in items)
    report = write_monday_checklist_to_activity_log(tmp_path)
    assert report["ok"] is True
    log_path = tmp_path / "live_pilot/activity/activity_log.jsonl"
    assert log_path.is_file()
    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["action"] == "Montag-Vorbereitung"
