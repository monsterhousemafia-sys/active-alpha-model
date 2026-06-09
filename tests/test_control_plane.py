"""Control plane: safe IO, job locks, health, recovery."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from aa_control_plane import load_pipeline, sync_control_plane, write_next_cursor_prompt
from aa_health_check import health_is_production_ready, run_health_check
from aa_job_lock import JobLock, pid_alive
from aa_recovery import build_last_known_good_snapshot, restore_last_known_good, save_last_known_good
from aa_safe_io import atomic_write_json, atomic_write_yaml


def test_atomic_write_json(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.json"
    atomic_write_json(target, {"a": 1})
    assert target.is_file()
    assert json.loads(target.read_text(encoding="utf-8"))["a"] == 1


def test_atomic_write_yaml(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "state.yaml"
    atomic_write_yaml(target, {"key": "value"})
    assert target.is_file()
    assert "key:" in target.read_text(encoding="utf-8")


def test_job_lock_exclusive(tmp_path: Path) -> None:
    lock = JobLock(tmp_path, "test_job")
    assert lock.acquire()
    lock2 = JobLock(tmp_path, "test_job")
    assert not lock2.acquire()
    lock.release()
    assert lock2.acquire()
    lock2.release()


def test_load_pipeline_json(tmp_path: Path) -> None:
    (tmp_path / "DEVELOPMENT_PIPELINE.json").write_text(
        '{"version": 1, "current_stage": "phase1", "stages": {}}',
        encoding="utf-8",
    )
    pipeline = load_pipeline(tmp_path)
    assert pipeline["current_stage"] == "phase1"


def test_sync_control_plane_pass(tmp_path: Path) -> None:
    root = tmp_path
    out_dir = root / "model_output_test"
    run_dir = root / "runs" / "r1"
    run_dir.mkdir(parents=True)
    out_dir.mkdir()
    (root / "DEVELOPMENT_PIPELINE.json").write_text(
        json.dumps({"version": 1, "current_stage": "phase1", "stages": {}}),
        encoding="utf-8",
    )
    (out_dir / "latest_validated_run.json").write_text(
        json.dumps(
            {
                "run_id": "r1",
                "run_dir": str(run_dir.resolve()),
                "integrity_status": "PASS",
                "variant_id": "R3",
            }
        ),
        encoding="utf-8",
    )
    (out_dir / "integrity_status.json").write_text(
        json.dumps({"status": "PASS"}),
        encoding="utf-8",
    )
    (run_dir / "integrity_report.json").write_text(
        json.dumps({"status": "PASS", "errors": []}),
        encoding="utf-8",
    )
    (run_dir / "strategy_daily_returns.csv").write_text("date,return\n2020-01-01,0.0\n", encoding="utf-8")
    (run_dir / "backtest_report.txt").write_text("ok", encoding="utf-8")
    (run_dir / "latest_target_portfolio.csv").write_text("ticker,weight\nSPY,1.0\n", encoding="utf-8")
    health, _ = sync_control_plane(root, out_dir, run_id="r1")
    assert (root / "control" / "system_health.json").is_file()
    assert health_is_production_ready(health)
    assert (root / "control" / "last_known_good_state.json").is_file()
    prompt = write_next_cursor_prompt(root)
    assert prompt.is_file()


def test_restore_last_known_good(tmp_path: Path) -> None:
    root = tmp_path
    src = root / "model_output_src"
    dst = root / "model_output_dst"
    src.mkdir()
    dst.mkdir()
    (src / "model_status.json").write_text('{"integrity_status": "PASS"}', encoding="utf-8")
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
    ok, msg = restore_last_known_good(root, dst)
    assert ok
    assert (dst / "model_status.json").is_file()


def test_pid_alive_current_process() -> None:
    assert pid_alive(os.getpid())
