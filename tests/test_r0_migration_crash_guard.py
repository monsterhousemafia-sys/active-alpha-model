"""M1 crash / stale-lock recovery."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_cleanup_stale_batch_lock_no_file(tmp_path: Path):
    from aa_runtime_profile import cleanup_stale_batch_lock

    r = cleanup_stale_batch_lock(tmp_path)
    assert r["removed"] is False
    assert r["reason"] == "no_lock"


def test_cleanup_stale_batch_lock_dead_pid(tmp_path: Path):
    from aa_runtime_profile import BATCH_LOCK_FILE, cleanup_stale_batch_lock

    lock = tmp_path / BATCH_LOCK_FILE
    lock.write_text("99999999 dead_test 2026-01-01T00:00:00+00:00\n", encoding="utf-8")
    r = cleanup_stale_batch_lock(tmp_path)
    assert r["removed"] is True
    assert not lock.is_file()


def test_append_matrix_log_session_appends(tmp_path: Path):
    from tools.r0_migration_crash_guard import append_matrix_log_session

    log = append_matrix_log_session(tmp_path, ["python", "test.py"], session="t1")
    append_matrix_log_session(tmp_path, ["python", "test2.py"], session="t2")
    text = log.read_text(encoding="utf-8")
    assert "session t1" in text
    assert "session t2" in text
    assert "test.py" in text and "test2.py" in text


def test_resolve_matrix_job_incomplete_without_returns(tmp_path: Path):
    from tools.r0_migration_crash_guard import resolve_matrix_job_status

    r = resolve_matrix_job_status(tmp_path, returncode=1)
    assert r["status"] in ("INCOMPLETE", "CRASHED")
    assert r["returns_ok"] is False


def test_crash_recovery_written(tmp_path: Path):
    from tools.r0_migration_crash_guard import write_crash_recovery_snapshot

    out = write_crash_recovery_snapshot(tmp_path, actions=[])
    path = tmp_path / "evidence" / "r0_migration" / "crash_recovery.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["schema_version"] == 1
    assert "resume_hint" in data


def test_ensure_m1_unblocked_on_repo():
    from tools.r0_migration_crash_guard import ensure_m1_unblocked

    result = ensure_m1_unblocked(ROOT)
    assert "snapshot" in result
    assert (ROOT / "evidence" / "r0_migration" / "crash_recovery.json").is_file()
