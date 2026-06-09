"""R3 Desktop-Icon — PNG + Qt-Fenstericon."""
from __future__ import annotations

import os
from pathlib import Path

from analytics.r3_desktop_icon import ensure_home_file_owned, install_r3_desktop_icons, resolve_r3_icon_path


def test_install_r3_desktop_icons(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    root = Path(__file__).resolve().parents[1]
    doc = install_r3_desktop_icons(root)
    assert doc.get("ok") is True
    assert int(doc.get("png_sizes_ok") or 0) >= 4
    icon = resolve_r3_icon_path(root=root)
    assert icon is not None
    assert icon.is_file()


def test_ensure_home_file_owned_user_writeable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "analytics.r3_desktop_icon.home_dir_owner",
        lambda: (os.getuid(), os.getgid()),
    )
    target = tmp_path / ".local/share/icons/hicolor/scalable/apps/r3-os.svg"
    target.parent.mkdir(parents=True)
    target.write_text("<svg/>", encoding="utf-8")
    assert ensure_home_file_owned(target) is True
