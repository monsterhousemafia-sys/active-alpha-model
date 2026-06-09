"""Apple-style GUI preview HTML."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.gui_preview_visual import render_gui_preview_html, write_gui_preview_html


def test_render_contains_apple_stack(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    report = {
        "generated_at_utc": "2026-06-06T12:00:00+00:00",
        "passed": 18,
        "total": 20,
        "overall_pass": True,
        "mode": "stable",
        "backend_steps": [
            {"id": "circle_score", "pass": True, "label_de": "Kreis", "detail_de": "Kreis-Score 1/6 grün (17%)"},
        ],
        "chat_steps": [],
        "gui_steps": [],
        "chat_evolution": {"chat_reply_de": "3) NÄCHSTER SCHRITT: learn", "next_step_de": "learn"},
        "system_status": {
            "headline_de": "System OK",
            "composite_pct": 72,
            "updated_at_utc": "2026-06-06T12:00:00+00:00",
            "tiles": [
                {
                    "id": "preview",
                    "label_de": "Preview",
                    "value_de": "18/20",
                    "detail_de": "90%",
                    "ok": True,
                    "status_class": "ok",
                }
            ],
            "operator": {},
        },
        "cockpit": {
            "traffic": "GRUEN",
            "traffic_class": "ok",
            "today_action_de": "Test",
            "cash_de": "1.000 €",
            "n_positions": 1,
            "hub_note_de": "Test",
            "actions": [{"id": "daily-mark", "label_de": "Mark", "detail_de": "x", "tier": "primary"}],
            "rebalance": {"summary_de": "—", "recorded_days": 0, "every_days": 5, "is_due": False},
            "portfolio_orders": {"summary_de": "—", "lines_de": []},
            "warnings": {"headline_de": "—", "critical_count": 0},
            "learning": {"grade": "A"},
            "deferred_de": "—",
        },
    }
    html = render_gui_preview_html(report)
    assert "-apple-system" in html
    assert "R3" in html
    assert "Linux" not in html
    assert "Handel heute" in html
    assert "system-status" in html
    assert "Kreis" in html
    paths = write_gui_preview_html(tmp_path, report)
    assert Path(paths["html"]).is_file()
