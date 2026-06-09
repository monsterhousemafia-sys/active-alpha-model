"""R3 OS Supremacy — Sitzungsübernahme."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_os_supremacy import decommission_foreign_autostart, load_supremacy, remove_ubuntu_background


def test_load_supremacy() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_supremacy(root)
    assert cfg.get("mode") == "takeover"
    assert "r3-os-session.desktop" in (cfg.get("autostart_allowlist") or [])


def test_decommission_foreign_autostart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    autostart = tmp_path / ".config/autostart"
    autostart.mkdir(parents=True)
    (autostart / "r3-os-session.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")
    (autostart / "active-alpha-preview.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")
    (autostart / "gnome-keyring-pkcs11.desktop").write_text("[Desktop Entry]\n", encoding="utf-8")

    root = Path(__file__).resolve().parents[1]
    doc = decommission_foreign_autostart(root)
    assert not (autostart / "active-alpha-preview.desktop").exists()
    assert (autostart / "active-alpha-preview.desktop.bak-r3").is_file()
    assert (autostart / "r3-os-session.desktop").is_file()
    assert (autostart / "gnome-keyring-pkcs11.desktop").is_file()
    assert len(doc.get("disabled") or []) == 1


def test_remove_ubuntu_background_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_supremacy(root)
    assert cfg.get("remove_ubuntu_background") is True
    assert cfg.get("desktop_background_color") == "#0a0a0f"


def test_remove_ubuntu_background_no_gsettings(monkeypatch) -> None:
    monkeypatch.setattr("analytics.r3_os_supremacy.shutil.which", lambda _name: None)
    assert remove_ubuntu_background() == []
