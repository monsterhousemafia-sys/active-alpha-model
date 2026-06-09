from __future__ import annotations

import json
from pathlib import Path

import time

from analytics.federation_compute import (
    build_utilization_summary,
    complete_task,
    enqueue_task,
    pull_task_for_worker,
    purge_h1_compute_tasks,
    run_compute_pulse,
    sync_compute_demand,
    worker_capabilities,
)


def test_worker_capabilities_full(tmp_path: Path) -> None:
    (tmp_path / "tools").mkdir(parents=True)
    (tmp_path / "tools/ai_kernel.py").write_text("# k\n", encoding="utf-8")
    caps = worker_capabilities(tmp_path, bundle_kind="lite")
    assert "preview" in caps


def test_pull_and_complete_pulse(tmp_path: Path) -> None:
    enqueue_task(
        tmp_path,
        {"kind": "compute_pulse", "requires": ["pulse"], "priority": 1, "seconds": 1},
    )
    task = pull_task_for_worker(tmp_path, worker_id="w1", capabilities=["pulse"], cpus=2)
    assert task and task.get("kind") == "compute_pulse"
    out = complete_task(tmp_path, task_id=str(task["id"]), worker_id="w1", ok=True, result={"cpu_seconds": 2})
    assert out["ok"] is True


def test_sync_compute_demand(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/gui_preview_latest.json").write_text("{}", encoding="utf-8")
    log = sync_compute_demand(tmp_path)
    assert log


def test_compute_pulse_short() -> None:
    out = run_compute_pulse(seconds=1, cpus=1)
    assert out["ok"] is True
    assert out["cpu_seconds"] >= 0


def test_compute_pulse_uses_multiple_cpus() -> None:
    import os

    cpus = min(4, os.cpu_count() or 1)
    if cpus < 2:
        return
    t0 = time.perf_counter()
    out = run_compute_pulse(seconds=3, cpus=cpus)
    wall = time.perf_counter() - t0
    assert out["ok"] is True
    assert float(out["cpu_seconds"]) > wall * 1.2


def test_purge_h1_compute_tasks(tmp_path: Path) -> None:
    enqueue_task(tmp_path, {"kind": "h1_path_chunk", "requires": ["h1"], "priority": 45})
    enqueue_task(tmp_path, {"kind": "compute_pulse", "requires": ["pulse"], "priority": 1})
    assert purge_h1_compute_tasks(tmp_path) == 1
    task = pull_task_for_worker(tmp_path, worker_id="w1", capabilities=["pulse"], cpus=1)
    assert task and task.get("kind") == "compute_pulse"


def test_utilization_uses_cpu_seconds(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/federation_compute_stats.json").write_text(
        json.dumps({"cpu_seconds": 120.5, "tasks_ok": 3}),
        encoding="utf-8",
    )
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/preview_federation.json").write_text(
        json.dumps(
            {
                "workers": {
                    "w1": {
                        "role": "compute",
                        "cpus": 8,
                        "worker_id": "w1",
                        "last_seen_utc": now,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    summary = build_utilization_summary(tmp_path)
    assert summary["cpu_seconds_total"] == 120.5
    assert summary["measurement"] == "cpu_seconds"
    assert "CPU-Sekunden" in summary["headline_de"]
