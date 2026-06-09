from __future__ import annotations

import json
from pathlib import Path

from analytics.hub_launch_ui import embed_launch_into_preview, render_launch_embed_strip
from analytics.preview_hub_page import load_hub_preview_report, render_hub_launch_page


def test_embed_launch_into_preview_contains_cockpit():
    preview = """<!DOCTYPE html><html><head><title>R3 · Cockpit</title><style></style></head>
<body><div class="page"><section id="cockpit">Handel heute</section></div></body></html>"""
    launch = {
        "overall_pct": 42,
        "headline_de": "Test",
        "updated_at_utc": "2026-01-01T00:00:00+00:00",
        "h1": {"status": "RUNNING", "progress_pct": 42, "detail_de": "läuft"},
        "milestones": [{"label_de": "Setup", "done": True}],
        "blockers_de": [],
        "tiles": [
            {
                "label_de": "Hub",
                "value_de": "Online",
                "detail_de": ":17890",
                "ok": True,
            }
        ],
    }
    out = embed_launch_into_preview(preview, launch)
    assert "world-launch" in out or "wl-hero" in out
    assert "lb-tiles" in out
    assert "preview-embed" in out
    assert "Handel heute" in out
    assert "r3-nav" in out


def test_render_launch_embed_strip():
    html = render_launch_embed_strip({"overall_pct": 10, "headline_de": "H", "h1": {}, "milestones": []})
    assert "launch-board" in html
    assert "10%" in html


def test_load_hub_preview_report(tmp_path: Path):
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps({"passed": 1, "total": 2, "overall_pass": True, "backend_steps": []}),
        encoding="utf-8",
    )
    doc = load_hub_preview_report(tmp_path, port=17890, live_cockpit=False)
    assert doc.get("passed") == 1
    assert doc.get("hub_port") == 17890


def test_render_hub_launch_page(tmp_path: Path):
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text(
        json.dumps(
            {
                "passed": 9,
                "total": 10,
                "overall_pass": True,
                "mode": "stable",
                "generated_at_utc": "2026-06-06T12:00:00+00:00",
                "backend_steps": [],
                "chat_steps": [],
                "gui_steps": [],
                "cockpit": {
                    "traffic": "GRUEN",
                    "traffic_class": "ok",
                    "today_action_de": "OK",
                    "cash_de": "100 €",
                    "n_positions": 0,
                    "hub_note_de": "Note",
                    "actions": [],
                    "rebalance": {"summary_de": "—", "recorded_days": 0, "every_days": 5},
                    "portfolio_orders": {"summary_de": "—", "lines_de": []},
                    "warnings": {"headline_de": "—", "critical_count": 0},
                    "learning": {"grade": "B"},
                    "deferred_de": "—",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_governance_status.json").write_text(
        json.dumps({"status": "RUNNING", "sealed": False, "progress_pct": 50, "detail_de": "x"}),
        encoding="utf-8",
    )
    html = render_hub_launch_page(tmp_path, port=17890).decode("utf-8")
    assert "launch-board" in html
    assert "Handel heute" in html
    assert "Systemcheck" in html
