from __future__ import annotations

import json
from pathlib import Path

from analytics.kernel_activity_bridge import log_kernel_command


def test_kernel_log_writes_cursor_source(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/active_alpha_unified.json").write_text(
        json.dumps({"surfaces": {"r3_ki": {"label_de": "R3 KI (lokal)"}}}),
        encoding="utf-8",
    )
    log_kernel_command(tmp_path, command="status", result="ok", status="INFO")
    log_path = tmp_path / "live_pilot/activity/activity_log.jsonl"
    assert log_path.is_file()
    line = json.loads(log_path.read_text(encoding="utf-8").strip())
    assert line["source"] == "CURSOR"
    assert "ai_kernel status" in line["action"]
