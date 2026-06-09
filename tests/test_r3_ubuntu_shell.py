"""R3 System — Desktop-Funktionen im Cockpit."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_ubuntu_shell import (
    build_shell_status,
    launch_shell_feature,
    load_ubuntu_shell,
    render_ubuntu_shell_section,
)


def test_load_ubuntu_shell_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_ubuntu_shell(root)
    assert cfg.get("section_title_de") == "Handel"
    assert len(cfg.get("features") or []) == 1
    assert (cfg.get("features") or [])[0].get("id") == "aktien"
    assert not any(f.get("id") in ("bluetooth", "sound", "files", "terminal") for f in (cfg.get("features") or []))
    assert any(f.get("id") == "aktien" for f in (cfg.get("features") or []))


def test_render_shell_section(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps(
            {
                "section_title_de": "R3 System",
                "categories": [{"id": "werkzeug", "label_de": "Werkzeug"}],
                "features": [
                    {
                        "id": "files",
                        "category": "werkzeug",
                        "label_de": "Dateien",
                        "detail_de": "Ordner",
                        "exec": ["true"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    html = render_ubuntu_shell_section(tmp_path, build_shell_status(tmp_path))
    assert "R3 System" in html
    assert "Dateien" in html
    assert "r3LaunchDesktop" in html
    assert "r3-desk-ico" in html
    assert "Werkzeug" in html
    assert "r3-desk-wifi-val" in html
    assert "r3-fusion-spotlight" in html


def test_build_shell_status_includes_availability(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps(
            {
                "features": [
                    {"id": "files", "label_de": "Dateien", "exec": ["this-command-does-not-exist-xyz"]}
                ]
            }
        ),
        encoding="utf-8",
    )
    doc = build_shell_status(tmp_path)
    feats = doc.get("features") or []
    assert feats and feats[0].get("available") is False


def test_launch_unknown_feature(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text("{}", encoding="utf-8")
    doc = launch_shell_feature(tmp_path, "nope")
    assert doc.get("ok") is False
