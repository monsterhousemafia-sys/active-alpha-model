from __future__ import annotations

import json
from pathlib import Path

from analytics.gui_32b_registry import (
    build_32b_gui_mandate,
    build_gui_32b_audit,
    load_gui_manifest,
)


def test_gui_manifest_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = load_gui_manifest(root)
    surfaces = doc.get("surfaces") or []
    assert len(surfaces) >= 8
    ids = {s["id"] for s in surfaces if isinstance(s, dict)}
    assert "hub_desktop" in ids
    assert "qt_order_desk" in ids


def test_gui_audit_and_mandate(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "analytics").mkdir(parents=True)
    (tmp_path / "analytics/preview_hub_page.py").write_text("# hub\nrender_desktop_shell_page\n", encoding="utf-8")
    (tmp_path / "control/gui_32b_rebuild_manifest.json").write_text(
        json.dumps(
            {
                "headline_de": "GUI Test",
                "surfaces": [
                    {
                        "id": "hub_desktop",
                        "tier": "hub",
                        "label_de": "Desktop",
                        "path": "/desktop",
                        "modules": ["analytics/preview_hub_page.py"],
                    }
                ],
                "tests_de": ["tests/test_preview_hub.py"],
            }
        ),
        encoding="utf-8",
    )
    audit = build_gui_32b_audit(tmp_path, persist=True)
    assert audit["ok_count"] == 1
    mandate = build_32b_gui_mandate(tmp_path)
    assert "König-Mandat" in mandate
    assert (tmp_path / "evidence/king_32b_gui_rebuild_mandate.txt").is_file()
