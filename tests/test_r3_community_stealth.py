"""Community-Stealth — unauffälliger Linux-Autostart."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import analytics.r3_community_stealth as stealth_mod
import analytics.r3_desktop_os as desktop_os_mod
from analytics.r3_community_stealth import (
    install_community_stealth,
    scan_community_stealth,
    session_autostart_filename,
    session_autostart_path,
)
from analytics.r3_desktop_os import install_session_autostart, load_desktop_os


def _stealth_cfg(base: Dict[str, Any] | None = None) -> Dict[str, Any]:
    doc = dict(base or load_desktop_os(Path(__file__).resolve().parents[1]))
    doc["community_stealth"] = {
        "enabled": True,
        "autostart_desktop_id": "xdg-user-session.desktop",
        "generic_name_de": "Benutzer-Sitzung",
        "generic_comment_de": "Lokale Sitzungsdienste nach Anmeldung",
        "hidden_from_menus": True,
        "hub_only_default": True,
        "systemd_user_session": False,
    }
    return doc


def test_session_autostart_stealth_filename(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(desktop_os_mod, "load_desktop_os", lambda _r: _stealth_cfg())
    monkeypatch.setattr(stealth_mod, "load_community_stealth", lambda _r: _stealth_cfg()["community_stealth"])
    assert session_autostart_filename(root) == "xdg-user-session.desktop"


def test_install_session_autostart_stealth(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(desktop_os_mod, "load_desktop_os", lambda _r: _stealth_cfg())

    doc = install_session_autostart(root)
    assert doc.get("ok") is True
    assert doc.get("community_stealth") is True

    dest = session_autostart_path(root)
    assert dest.is_file()
    text = dest.read_text(encoding="utf-8")
    assert "Hidden=true" in text
    assert "NoDisplay=true" in text
    assert "Name=Benutzer-Sitzung" in text
    assert "R3_SESSION_HUB_ONLY=1" in text
    assert not (tmp_path / ".config/autostart/r3-os-session.desktop").exists()


def test_install_community_stealth_scan(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setattr(desktop_os_mod, "load_desktop_os", lambda _r: _stealth_cfg())

    doc = install_community_stealth(root, persist=False)
    assert doc.get("ok") is True
    scan = scan_community_stealth(root)
    assert scan.get("autostart_installed") is True
    assert scan.get("hidden_from_menus") is True
    assert scan.get("no_display") is True
