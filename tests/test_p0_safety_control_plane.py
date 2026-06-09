"""P0 Safety Control Plane gate tests (master prompt §9.5)."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from aa_branch_gate import assess_branch_safety
from aa_checkpoint import load_checkpoint, write_checkpoint
from aa_control_plane import load_pipeline, sync_control_plane
from aa_failsafe import activate_failsafe, clear_failsafe, is_failsafe_active, load_failsafe_state
from aa_health_check import build_system_health_record, health_is_production_ready
from aa_job_lock import JobLock, pid_alive, read_lock_owner
from aa_p0_paths import ensure_p0_directories, work_run_dir
from aa_recovery import build_last_known_good_snapshot, load_last_known_good, restore_last_known_good, save_last_known_good
from aa_safe_io import atomic_write_json


def test_atomic_write_all_or_nothing(tmp_path: Path) -> None:
    target = tmp_path / "control" / "state.json"
    atomic_write_json(target, {"ok": True})
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["ok"] is True
    assert not any(target.parent.glob(f".{target.name}.*"))


def test_lock_excludes_concurrent_writer(tmp_path: Path) -> None:
    a = JobLock(tmp_path, "publish")
    b = JobLock(tmp_path, "publish")
    assert a.acquire()
    try:
        assert not b.acquire()
    finally:
        a.release()
    assert b.acquire()
    b.release()


def test_stale_lock_cleanup(tmp_path: Path) -> None:
    lock_path = tmp_path / ".active_alpha_jobs" / "stale.lock"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("999999999 dead\n", encoding="utf-8")
    lock = JobLock(tmp_path, "stale")
    assert lock.acquire()
    lock.release()


def test_checkpoint_does_not_touch_lkg(tmp_path: Path) -> None:
    ensure_p0_directories(tmp_path)
    control = tmp_path / "control"
    lkg = control / "last_known_good_state.json"
    lkg.write_text('{"validated_run_id":"keep"}', encoding="utf-8")
    before = lkg.read_text(encoding="utf-8")
    write_checkpoint(tmp_path, "job1", {"step": 1})
    assert load_checkpoint(tmp_path, "job1") is not None
    assert lkg.read_text(encoding="utf-8") == before


def test_failed_job_does_not_overwrite_lkg(tmp_path: Path) -> None:
    root = tmp_path
    out_dir = root / "out_bad"
    out_dir.mkdir()
    control = root / "control"
    control.mkdir(parents=True)
    save_last_known_good(
        control,
        {"validated_run_id": "good", "integrity_status": "PASS", "artifacts": []},
    )
    before = load_last_known_good(control)
    activate_failsafe(root, reason="simulated_fail")
    health = build_system_health_record(root, out_dir)
    assert not health_is_production_ready(health)
    sync_control_plane(root, out_dir)
    after = load_last_known_good(control)
    assert after.get("validated_run_id") == before.get("validated_run_id")
    clear_failsafe(root)


def test_recovery_loads_last_known_good(tmp_path: Path) -> None:
    root = tmp_path
    src = root / "model_output_src"
    dst = root / "model_output_dst"
    src.mkdir()
    dst.mkdir()
    (src / "model_status.json").write_text('{"integrity_status":"PASS"}', encoding="utf-8")
    control = root / "control"
    control.mkdir()
    save_last_known_good(
        control,
        build_last_known_good_snapshot(
            out_dir=src,
            health={"checked_at_utc": "2026-01-01T00:00:00+00:00", "integrity_status": "PASS"},
            run_id="r1",
        ),
    )
    ok, _ = restore_last_known_good(root, dst)
    assert ok
    assert (dst / "model_status.json").is_file()


def test_failsafe_mode_persisted(tmp_path: Path) -> None:
    activate_failsafe(tmp_path, reason="test", critical_errors=["x"])
    assert is_failsafe_active(tmp_path)
    state = load_failsafe_state(tmp_path)
    assert state["pipeline_status"] == "FAILSAFE_MODE"
    health = build_system_health_record(tmp_path, tmp_path / "out")
    assert health["pipeline_status"] == "FAILSAFE_MODE"
    clear_failsafe(tmp_path)
    assert not is_failsafe_active(tmp_path)


def test_p0_gate_blocks_p1_start_in_pipeline(tmp_path: Path) -> None:
    pipeline = {
        "current_phase": "P1_INTEGRITY_FOUNDATION",
        "phases": [
            {"id": "P0_SAFETY_CONTROL_PLANE", "status": "FAILED"},
            {"id": "P1_INTEGRITY_FOUNDATION", "status": "NOT_STARTED"},
        ],
    }
    p0 = next(p for p in pipeline["phases"] if p["id"] == "P0_SAFETY_CONTROL_PLANE")
    assert p0["status"] != "PASS"


def test_branch_gate_assessment(tmp_path: Path) -> None:
    assessment = assess_branch_safety(tmp_path)
    assert assessment.is_safe or assessment.blocker == "AUTOPILOT_BRANCH_REQUIRED"


def test_work_run_isolated_directory(tmp_path: Path) -> None:
    wr = work_run_dir(tmp_path, "job-123")
    atomic_write_json(wr / "partial.json", {"status": "WORK"})
    assert (tmp_path / "work_runs" / "job-123" / "partial.json").is_file()


def test_system_health_schema_fields(tmp_path: Path) -> None:
    health = build_system_health_record(tmp_path, tmp_path / "missing")
    for key in (
        "operational_health",
        "analytical_validity",
        "active_signal_validity",
        "pipeline_status",
        "last_known_good_run_id",
        "last_updated_at_utc",
        "critical_errors",
    ):
        assert key in health
