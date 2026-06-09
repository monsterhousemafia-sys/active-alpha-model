from __future__ import annotations

from pathlib import Path

from analytics.r3_dev_trail import build_dev_trail, record_dev_change, render_dev_trail_section


def test_build_dev_trail_has_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = build_dev_trail(root)
    assert doc.get("paths", {}).get("project_root")
    assert "r3-os" in str(doc.get("paths", {}).get("r3_share") or "")
    assert doc.get("next_de")


def test_render_dev_trail_section() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_dev_trail_section(build_dev_trail(root))
    assert "dev-trail" in html
    assert "dt-project-root" in html
    assert "Neues Betriebssystem" in html


def test_record_dev_change(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    entry = record_dev_change(root, title_de="Test", detail_de="Detail", status="active")
    assert entry.get("title_de") == "Test"
