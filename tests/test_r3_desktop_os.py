"""R3 Desktop OS installer."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_desktop_os import (
    install_desktop_os,
    install_r3_exec_mirror_app,
    load_desktop_os,
    purge_r3_local_apps,
)


def test_load_desktop_os_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_desktop_os(root)
    assert cfg.get("os_name") == "R3"


def test_install_desktop_os(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    doc = install_desktop_os(root, force=True)
    assert doc.get("ok") is True
    apps = tmp_path / ".local/share/applications"
    assert (apps / "Alpha-Model.desktop").is_file()
    assert not (apps / "R3-Cockpit.desktop").exists()
    assert not (apps / "R3-Assistent.desktop").exists()
    assert not (apps / "Alpha-Model-Agent.desktop").exists()
    assert not (apps / "R3-Order-Desk.desktop").exists()
    assert not (apps / "R3-Status.desktop").exists()
    cfg = load_desktop_os(root)
    stealth = cfg.get("community_stealth") or {}
    autostart_name = (
        str(stealth.get("autostart_desktop_id") or "xdg-user-session.desktop")
        if stealth.get("enabled")
        else "r3-os-session.desktop"
    )
    assert (tmp_path / ".config/autostart" / autostart_name).is_file()
    assert not (tmp_path / ".config/autostart/active-alpha-preview.desktop").exists()


def test_install_blocked_when_purged(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    blocked = install_desktop_os(root)
    assert blocked.get("blocked") is True
    assert blocked.get("error") == "LOCAL_APPS_PURGED"


def test_install_r3_exec_mirror_app(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    (root / "tools/r3_app.sh").chmod(0o755)
    doc = install_r3_exec_mirror_app(root)
    assert doc.get("ok") is True
    assert (tmp_path / ".local/share/applications/R3.desktop").is_file()
    assert (tmp_path / ".local/bin/r3").is_symlink()


def test_purge_r3_local_apps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    install_desktop_os(root, force=True)
    bin_dir = tmp_path / ".local/bin"
    assert (bin_dir / "r3-cockpit").exists()
    doc = purge_r3_local_apps(root)
    assert doc.get("ok") is True
    assert doc.get("removed_count", 0) >= 1
    assert not (bin_dir / "r3-cockpit").exists()
    assert not (tmp_path / ".local/share/applications/Alpha-Model.desktop").exists()
    assert not (tmp_path / ".config/autostart/r3-os-session.desktop").exists()
