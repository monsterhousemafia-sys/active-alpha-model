"""Worker bundle export must not rsync project into itself."""
from __future__ import annotations

from pathlib import Path

import pytest

from analytics.worker_export_sync import (
    WORKER_BUNDLE_RSYNC_EXCLUDES,
    validate_worker_export_dest,
)


def test_validate_worker_export_dest_accepts_outside_project(tmp_path: Path) -> None:
    root = tmp_path / "active_alpha_model"
    root.mkdir()
    dest = tmp_path / "active_alpha_worker_FULL"
    assert validate_worker_export_dest(root, dest) == dest.resolve()


def test_validate_worker_export_dest_rejects_inside_project(tmp_path: Path) -> None:
    root = tmp_path / "active_alpha_model"
    root.mkdir()
    bad = root / "active_alpha_worker_FULL"
    with pytest.raises(ValueError, match="outside project root"):
        validate_worker_export_dest(root, bad)


def test_validate_worker_export_dest_rejects_project_root(tmp_path: Path) -> None:
    root = tmp_path / "active_alpha_model"
    root.mkdir()
    with pytest.raises(ValueError, match="outside project root"):
        validate_worker_export_dest(root, root)


def test_worker_bundle_excludes_nested_worker_dirs() -> None:
    joined = " ".join(WORKER_BUNDLE_RSYNC_EXCLUDES)
    assert "active_alpha_worker_FULL/" in joined
    assert ".venv/" in joined
