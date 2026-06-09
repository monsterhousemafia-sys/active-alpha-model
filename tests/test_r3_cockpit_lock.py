"""R3 Cockpit Single-Instance."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import os

from analytics.r3_cockpit_lock import (
    clear_cockpit_pid,
    clear_cockpit_pid_if_self,
    is_cockpit_running,
    launch_cockpit_once,
    read_cockpit_pid,
    write_cockpit_pid,
)


def test_pid_roundtrip(tmp_path: Path, monkeypatch) -> None:
    share = tmp_path / "r3-os"
    share.mkdir()
    monkeypatch.setattr("analytics.r3_cockpit_lock._share_dir", lambda: share)
    write_cockpit_pid(4242)
    assert read_cockpit_pid() == 4242
    clear_cockpit_pid()
    assert read_cockpit_pid() is None


def test_clear_pid_only_for_self(tmp_path: Path, monkeypatch) -> None:
    share = tmp_path / "r3-os"
    share.mkdir()
    monkeypatch.setattr("analytics.r3_cockpit_lock._share_dir", lambda: share)
    write_cockpit_pid(4242)
    clear_cockpit_pid_if_self()
    assert read_cockpit_pid() == 4242
    write_cockpit_pid(os.getpid())
    clear_cockpit_pid_if_self()
    assert read_cockpit_pid() is None


def test_launch_lock_prevents_parallel_start(tmp_path: Path, monkeypatch) -> None:
    share = tmp_path / "r3-os"
    share.mkdir()
    monkeypatch.setattr("analytics.r3_cockpit_lock._share_dir", lambda: share)
    from analytics.r3_cockpit_lock import _cockpit_launch_lock

    with _cockpit_launch_lock() as first:
        assert first is True
        with _cockpit_launch_lock() as second:
            assert second is False


def test_launch_skips_when_running(tmp_path: Path, monkeypatch) -> None:
    share = tmp_path / "r3-os"
    share.mkdir()
    monkeypatch.setattr("analytics.r3_cockpit_lock._share_dir", lambda: share)
    monkeypatch.setattr("analytics.r3_cockpit_lock.is_cockpit_running", lambda: True)
    monkeypatch.setattr("analytics.r3_cockpit_lock.read_cockpit_pid", lambda: 99)
    doc = launch_cockpit_once(tmp_path)
    assert doc.get("already_running") is True
    assert doc.get("ok") is True
