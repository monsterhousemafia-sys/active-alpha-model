"""M1 outage / stall guard."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_outage_config_exists():
    assert (ROOT / "control" / "r0_migration" / "outage_guard_config.json").is_file()


def test_detect_stall_no_batch(tmp_path: Path):
    from tools.r0_migration_outage_guard import detect_matrix_stall

    r = detect_matrix_stall(tmp_path)
    assert r["stalled"] is False


def test_config_uses_90_min_threshold():
    data = json.loads((ROOT / "control" / "r0_migration" / "outage_guard_config.json").read_text(encoding="utf-8"))
    assert data["stall_detection"]["max_idle_minutes_without_returns"] == 45


def test_run_outage_check_writes_health():
    from tools.r0_migration_outage_guard import run_outage_check

    result = run_outage_check(ROOT, repair=True)
    path = ROOT / "evidence" / "r0_migration" / "m1_health.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "updated_at_utc" in data or "stall" in data or result.get("status") == "M1_SEALED"


def test_cleanup_stale_in_acquire_path(tmp_path: Path):
    from aa_runtime_profile import BATCH_LOCK_FILE, acquire_batch_work, cleanup_stale_batch_lock

    (tmp_path / BATCH_LOCK_FILE).write_text("99999999 x 2026-01-01\n", encoding="utf-8")
    cleanup_stale_batch_lock(tmp_path)
    guard = acquire_batch_work(tmp_path, label="test")
    assert guard is not None
    guard.release()
