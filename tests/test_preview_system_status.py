"""Unified system status for Preview Command Center."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.preview_status_visual import render_system_status_section
from analytics.preview_system_status import build_preview_system_status


def test_build_preview_system_status_minimal(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"passed": 18, "total": 21, "overall_pass": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_governance_status.json").write_text(
        json.dumps(
            {
                "status": "RUNNING",
                "sealed": False,
                "progress_pct": 42,
                "banner_de": "H1: RUNNING ~42%",
                "detail_de": "Pfad-Sim",
            }
        ),
        encoding="utf-8",
    )
    doc = build_preview_system_status(tmp_path)
    assert doc["composite_pct"] >= 0
    assert len(doc["tiles"]) >= 4
    assert doc["h1"]["progress_pct"] == 42
    assert doc["preview"]["passed"] == 18


def test_render_system_status_section() -> None:
    html = render_system_status_section(
        {
            "headline_de": "Test Headline",
            "composite_pct": 55,
            "updated_at_utc": "2026-06-06T12:00:00+00:00",
            "tiles": [
                {
                    "id": "h1",
                    "label_de": "H1",
                    "value_de": "42%",
                    "detail_de": "läuft",
                    "ok": False,
                    "status_class": "warn",
                }
            ],
            "operator": {},
        }
    )
    assert "system-status" in html
    assert "55%" in html
    assert "Test Headline" in html
