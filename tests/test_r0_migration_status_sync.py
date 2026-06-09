"""M1 status artifact sync."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sync_m1_status_artifacts():
    from tools.r0_migration_status_sync import sync_m1_status_artifacts

    result = sync_m1_status_artifacts(ROOT)
    path = ROOT / "evidence" / "r0_migration" / "m1_completion_summary.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["phase"] == "M1"
    assert data["status"] in ("IN_PROGRESS", "READY_TO_SEAL", "SEALED", "COMPLETE_WITH_BLOCKER")
    assert result.get("phase_status_m1", {}).get("status") == data["status"]
    assert result.get("program_focus", {}).get("current_execution_phase") in ("M1", "M2")
