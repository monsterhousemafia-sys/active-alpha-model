from __future__ import annotations

import json
from pathlib import Path

from execution.linux_nvme_storage import migrate_dir_names, repair_migrated_symlinks, storage_status


def test_storage_status_shape(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/linux_nvme_storage.json").write_text(
        json.dumps({"enabled": False, "mount_candidates": []}),
        encoding="utf-8",
    )
    status = storage_status(tmp_path)
    assert status["enabled"] is False
    assert status["mount"] is None


def test_migrate_dir_names_from_config(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/linux_nvme_storage.json").write_text(
        json.dumps({"migrate_dirs": ["validation_runs", "runs"]}),
        encoding="utf-8",
    )
    assert migrate_dir_names(tmp_path) == ["validation_runs", "runs"]


def test_repair_broken_symlink_local_fallback(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/linux_nvme_storage.json").write_text(
        json.dumps({"enabled": True, "mount_candidates": [], "migrate_dirs": ["validation_runs"]}),
        encoding="utf-8",
    )
    broken = tmp_path / "validation_runs"
    broken.symlink_to("/nonexistent/nvme/validation_runs")
    report = repair_migrated_symlinks(tmp_path)
    assert (tmp_path / "validation_runs").is_dir()
    assert report["repaired"][0]["action"] == "local_fallback"
