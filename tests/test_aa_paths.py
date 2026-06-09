"""Tests for project root and Marktanalyse bundle path resolution."""
from __future__ import annotations

import sys
from pathlib import Path

from aa_paths import (
    CANONICAL_MARKTANALYSE_EXE,
    bundle_size_bytes,
    canonical_marktanalyse_exe,
    frozen_user_data_root,
    marktanalyse_internal_dir,
    project_root,
    resolve_marktanalyse_exe,
)


def test_project_root_from_cwd(tmp_path: Path, monkeypatch):
    (tmp_path / "active_alpha_model.py").write_text("#", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert project_root() == tmp_path


def test_project_root_frozen_root_exe(tmp_path: Path, monkeypatch):
    (tmp_path / "active_alpha_model.py").write_text("#", encoding="utf-8")
    exe = tmp_path / "Marktanalyse.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == tmp_path


def test_project_root_frozen_onedir_subfolder(tmp_path: Path, monkeypatch):
    (tmp_path / "active_alpha_model.py").write_text("#", encoding="utf-8")
    bundle = tmp_path / "Marktanalyse"
    bundle.mkdir()
    (bundle / "_internal").mkdir()
    exe = bundle / "Marktanalyse.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == tmp_path


def test_project_root_frozen_dist_subfolder(tmp_path: Path, monkeypatch):
    (tmp_path / "active_alpha_model.py").write_text("#", encoding="utf-8")
    dist = tmp_path / "dist"
    dist.mkdir()
    exe = dist / "Marktanalyse.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == tmp_path


def test_project_root_frozen_operational_live_pilot(tmp_path: Path, monkeypatch):
    operational = tmp_path / "operational"
    operational.mkdir()
    (operational / "live_pilot").mkdir()
    exe = operational / "Marktanalyse.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert project_root() == operational


def test_project_root_frozen_portable_fallback(tmp_path: Path, monkeypatch):
    portable = tmp_path / "Desktop"
    portable.mkdir()
    exe = portable / "Marktanalyse.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.chdir(portable)
    root = project_root()
    assert root == tmp_path / "AppData" / "Local" / "Marktanalyse" / "active_alpha_data"


def test_canonical_marktanalyse_exe_is_root_only(tmp_path: Path):
    root_exe = tmp_path / CANONICAL_MARKTANALYSE_EXE
    root_exe.write_bytes(b"only")
    bundle_exe = tmp_path / "Marktanalyse" / "Marktanalyse.exe"
    bundle_internal = tmp_path / "Marktanalyse" / "_internal"
    bundle_internal.mkdir(parents=True)
    bundle_exe.write_bytes(b"legacy")
    assert canonical_marktanalyse_exe(tmp_path) == root_exe
    assert resolve_marktanalyse_exe(tmp_path) == root_exe


def test_marktanalyse_internal_dir_root_junction(tmp_path: Path):
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "lib.dll").write_bytes(b"x" * 100)
    assert marktanalyse_internal_dir(tmp_path) == internal
    assert canonical_marktanalyse_exe(tmp_path).name == CANONICAL_MARKTANALYSE_EXE
    assert bundle_size_bytes(tmp_path) >= 100
