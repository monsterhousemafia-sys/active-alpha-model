"""Background job scaffold tests (Phase C)."""
from __future__ import annotations

from pathlib import Path

from aa_background_jobs import JobLock, job_enabled, run_job


def test_job_disabled_by_default(tmp_path: Path):
    result = run_job("realtime_collect", tmp_path, env={})
    assert result.status == "DISABLED"
    assert result.exit_code == 0


def test_job_lock_blocks_concurrent(tmp_path: Path):
    lock1 = JobLock(tmp_path, "eod_finalize")
    lock2 = JobLock(tmp_path, "eod_finalize")
    assert lock1.acquire()
    try:
        assert not lock2.acquire()
    finally:
        lock1.release()


def test_rebalance_signal_requires_validated_run(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_JOB_REBALANCE_SIGNAL_ENABLED", "1")
    result = run_job("rebalance_signal", tmp_path, env={"AA_JOB_REBALANCE_SIGNAL_ENABLED": "1"})
    assert result.status == "FAIL"
    assert result.exit_code == 2


def test_job_enabled_env():
    from aa_background_jobs import JOB_SPECS

    spec = JOB_SPECS["feedback_update"]
    assert not job_enabled(spec, env={spec.env_var: "0"})
    assert job_enabled(spec, env={spec.env_var: "1"})
