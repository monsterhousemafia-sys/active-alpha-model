"""Post-Login — ~/.local-Besitz nach Cursor-Sandbox."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from analytics.r3_home_ownership import (
    _needs_fix,
    fix_r3_home_ownership,
    r3_home_ownership_targets,
    run_post_login_hook,
)


@pytest.fixture
def home_owner(monkeypatch: pytest.MonkeyPatch) -> tuple[int, int]:
    uid, gid = os.getuid(), os.getgid()
    monkeypatch.setattr(
        "analytics.r3_home_ownership._resolve_home_owner",
        lambda: (uid, gid),
    )
    return uid, gid


def test_targets_include_r3_desktop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    names = {p.name for p in r3_home_ownership_targets()}
    assert "R3.desktop" in names
    assert "r3-os-session.desktop" in names


def test_needs_fix_detects_wrong_owner(tmp_path: Path) -> None:
    f = tmp_path / "x"
    f.write_text("a", encoding="utf-8")
    assert _needs_fix(f, os.getuid()) is False
    if os.getuid() == 0:
        return
    # als Nicht-Root: fremder Besitz nicht simulierbar ohne root


def test_fix_ok_when_already_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home_owner: tuple[int, int]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    apps = tmp_path / ".local/share/applications"
    apps.mkdir(parents=True)
    desktop = apps / "R3.desktop"
    desktop.write_text("[Desktop Entry]\n", encoding="utf-8")
    doc = fix_r3_home_ownership(tmp_path)
    assert doc.get("ok") is True
    assert doc.get("fixed_count") == 0


def test_fix_calls_chown_when_needed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home_owner: tuple[int, int]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    uid, gid = home_owner
    icons = tmp_path / ".local/share/icons/hicolor"
    icons.mkdir(parents=True)
    fixed: list[Path] = []

    pending_fix = {icons}

    def _needs(path: Path, target_uid: int) -> bool:
        return path in pending_fix

    def _fake_chown_and_clear(path: Path, u: int, g: int) -> bool:
        fixed.append(path)
        pending_fix.discard(path)
        return True

    monkeypatch.setattr("analytics.r3_home_ownership._needs_fix", _needs)
    monkeypatch.setattr("analytics.r3_home_ownership._chown_as_root", _fake_chown_and_clear)
    monkeypatch.setattr("analytics.r3_home_ownership.os.getuid", lambda: 0)

    doc = fix_r3_home_ownership(tmp_path)
    assert fixed == [icons]
    assert doc.get("ok") is True
    assert doc.get("fixed_count") == 1


def test_post_login_hook_writes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home_owner: tuple[int, int]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    doc = run_post_login_hook(tmp_path)
    assert doc.get("ok") is True
    assert (tmp_path / "evidence/r3_home_ownership_latest.json").is_file()
