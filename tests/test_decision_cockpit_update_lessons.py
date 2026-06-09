"""Lessons aus Decision-Cockpit-Update."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.decision_cockpit_update_lessons import record_update_lessons


def test_record_update_lessons(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/series_readiness_latest.json").write_text(
        json.dumps({"series_ready": True, "readiness_pct": 100, "warnings_de": ["Linux-Potenzial"]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_operational_checklist_latest.json").write_text(
        json.dumps({"checklist_ok": True, "items_ok": 37, "items_total": 37, "partial_de": ["Einzel-Verkauf"]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_local_growth_latest.json").write_text(
        json.dumps({"capabilities": [{"id": "king_local", "ok": True}]}),
        encoding="utf-8",
    )
    update_doc = {"ok": True, "steps": []}

    doc = record_update_lessons(tmp_path, trigger_de="test", update_doc=update_doc)

    assert doc.get("ok") is True
    assert len(doc.get("lessons_de") or []) >= 8
    assert any("86 %" in str(x.get("lesson_de", "")) for x in doc["lessons_de"])
    assert (tmp_path / "evidence/decision_cockpit_update_lessons_latest.json").is_file()
    assert doc.get("snapshot_de", {}).get("series_ready") is True
