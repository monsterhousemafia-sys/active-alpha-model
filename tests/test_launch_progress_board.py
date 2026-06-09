from __future__ import annotations

from pathlib import Path

from analytics.launch_progress_board import build_launch_status
from analytics.launch_progress_ui import render_launch_progress_page


def test_build_launch_status(tmp_path: Path):
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/h1_governance_status.json").write_text(
        '{"status":"RUNNING","sealed":false,"progress_pct":42,"detail_de":"Test"}',
        encoding="utf-8",
    )
    doc = build_launch_status(tmp_path, refresh_h1=False)
    assert doc.get("overall_pct") == 42
    assert doc.get("h1", {}).get("progress_pct") == 42
    assert "tiles" in doc
    assert any(t.get("id") == "preview" for t in doc.get("tiles") or [])
    assert doc.get("preview_url")


def test_build_launch_status_seal_optional_complete(tmp_path: Path):
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/h1_governance_status.json").write_text(
        '{"status":"COMPLETE","sealed":false,"progress_pct":100}',
        encoding="utf-8",
    )
    (tmp_path / "control/h1_seal_policy.json").write_text(
        '{"seal_required":false}',
        encoding="utf-8",
    )
    doc = build_launch_status(tmp_path, refresh_h1=False)
    assert doc.get("phase") == "h1_done"
    assert doc.get("blockers_de") == []


def test_render_launch_progress_page():
    html = render_launch_progress_page(
        {
            "overall_pct": 55,
            "headline_de": "Test",
            "updated_at_utc": "2026-01-01T00:00:00+00:00",
            "h1": {"status": "RUNNING", "progress_pct": 55, "detail_de": "läuft"},
            "remote": {"public_base_url": "https://example.com"},
            "join_url": "https://example.com/join",
            "tiles": [{"label_de": "Hub", "value_de": "Online", "ok": True, "detail_de": ":17890"}],
            "milestones": [{"label_de": "Setup", "done": True}],
            "blockers_de": [],
        }
    ).decode("utf-8")
    assert "Launch-Fortschritt" in html
    assert "55%" in html
