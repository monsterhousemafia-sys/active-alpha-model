"""R3 Desktop Fusion — Apple × Microsoft Schritt A."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_desktop_fusion import (
    build_fusion_status,
    fusion_search,
    launch_power_action,
    load_fusion_config,
    render_fusion_chrome,
)


def test_load_fusion_config_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_fusion_config(root)
    assert cfg.get("phase") == "A"
    assert len(cfg.get("power_actions") or []) >= 4
    assert len(cfg.get("pinned_apps") or []) >= 3


def test_fusion_search_files(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_ubuntu_shell.json").write_text(
        json.dumps(
            {
                "features": [
                    {"id": "files", "label_de": "Dateien", "detail_de": "Ordner", "category": "werkzeug"}
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_os_fusion.json").write_text(
        json.dumps({"power_actions": [{"id": "lock", "label_de": "Sperren", "exec": ["true"]}]}),
        encoding="utf-8",
    )
    hits = fusion_search(tmp_path, "datei")
    assert any(r.get("id") == "files" for r in hits.get("results") or [])


def test_render_fusion_chrome() -> None:
    root = Path(__file__).resolve().parents[1]
    from analytics.r3_ubuntu_shell import load_ubuntu_shell

    html = render_fusion_chrome(root, shell_cfg=load_ubuntu_shell(root), fusion_doc=build_fusion_status(root))
    assert "r3-fusion-spotlight" in html
    assert "r3-fusion-dock" in html
    assert "r3-fusion-power-menu" in html
    assert "Fusion" in html


def test_launch_unknown_power(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_os_fusion.json").write_text("{}", encoding="utf-8")
    doc = launch_power_action(tmp_path, "nope")
    assert doc.get("ok") is False
