from __future__ import annotations

from pathlib import Path

from analytics.gui_preview_visual import render_gui_preview_html
from analytics.preview_manifest import load_preview_manifest


def test_manifest_loads(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/PREVIEW_MANIFEST_DE.json").write_text(
        '{"required_read": true, "title_de": "T", "sections": [], "storage_key": "k"}',
        encoding="utf-8",
    )
    doc = load_preview_manifest(tmp_path)
    assert doc.get("title_de") == "T"


def test_manifest_overlay_in_html() -> None:
    html = render_gui_preview_html(
        {
            "passed": 1,
            "total": 1,
            "overall_pass": True,
            "manifest": {
                "required_read": True,
                "title_de": "Mission",
                "one_liner_de": "Ziel",
                "sections": [{"headline_de": "H", "body_de": "B"}],
                "ack_button_de": "OK",
                "storage_key": "test_ack",
            },
        }
    )
    assert "manifest-overlay" in html
    assert "Mission" in html
