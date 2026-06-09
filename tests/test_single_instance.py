"""Tests for single-instance guard."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aa_single_instance import (
    APP_MUTEX_PREFIX,
    SingleInstanceGuard,
    _mutex_name,
    _try_file_lock,
    acquire_single_instance,
)


def test_mutex_name_stable(tmp_path: Path):
    a = _mutex_name(tmp_path)
    b = _mutex_name(tmp_path)
    assert a == b
    assert a.startswith(APP_MUTEX_PREFIX)


def test_acquire_allows_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AA_SINGLE_INSTANCE", "0")
    guard = acquire_single_instance(tmp_path)
    assert guard is not None
    guard.release()


def test_file_lock_blocks_second_holder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AA_SINGLE_INSTANCE", "1")
    monkeypatch.setattr("aa_single_instance._try_windows_mutex", lambda _name: (None, False))

    first = _try_file_lock(tmp_path)
    assert first is not None
    second = _try_file_lock(tmp_path)
    assert second is None
    first.unlink(missing_ok=True)


def test_second_process_gets_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("AA_SINGLE_INSTANCE", "1")
    monkeypatch.setenv("AA_SINGLE_INSTANCE_MUTEX", "0")
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "0")
    guard = acquire_single_instance(tmp_path.resolve())
    assert guard is not None
    project_root = Path(__file__).resolve().parents[1]
    resolved = str(tmp_path.resolve())
    code = (
        "import os, sys; "
        f"os.chdir({resolved!r}); "
        f"sys.path.insert(0, {str(project_root)!r}); "
        "from aa_single_instance import acquire_single_instance; "
        "from pathlib import Path; "
        f"g = acquire_single_instance(Path({resolved!r})); "
        "raise SystemExit(0 if g is None else 2)"
    )
    env = os.environ.copy()
    env["AA_SINGLE_INSTANCE"] = "1"
    env["AA_SINGLE_INSTANCE_MUTEX"] = "0"
    env["AA_ALLOW_MULTI_INSTANCE"] = "0"
    proc = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    guard.release()
