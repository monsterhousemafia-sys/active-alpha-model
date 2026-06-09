"""R3 surface — no legacy Linux words in UI copy."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_surface_theme import friendly_status, load_surface_identity, sanitize_surface_text


def test_sanitize_removes_linux_words() -> None:
    t = sanitize_surface_text("Ubuntu Linux systemd Command Center Active Alpha")
    assert "Linux" not in t
    assert "Ubuntu" not in t
    assert "Cockpit" in t or "Alpha Model" in t


def test_friendly_status_tiles(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps(
            {
                "product": "R3",
                "tile_labels": {"kernel": {"label_de": "R3 Kern", "value_ok_de": "Aktiv"}},
            }
        ),
        encoding="utf-8",
    )
    doc = friendly_status(
        {
            "headline_de": "Cognitive Kernel v2 — Cursor",
            "tiles": [{"id": "kernel", "ok": True, "value_de": "v2", "detail_de": "Linux test"}],
        },
        tmp_path,
    )
    assert doc["tiles"][0]["label_de"] == "R3 Kern"
    assert "Linux" not in doc["tiles"][0]["detail_de"]


def test_load_surface_identity_project() -> None:
    root = Path(__file__).resolve().parents[1]
    ident = load_surface_identity(root)
    assert ident.get("product") == "R3"
