from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.federation_compute import complete_task, enqueue_task, pull_task_for_worker
from analytics.federation_legion import (
    build_legion_leaderboard,
    build_legion_summary,
    legion_welcome_for_worker,
    rank_for_cpu_seconds,
    record_legion_contribution,
)
from analytics.preview_federation import upsert_worker


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def test_rank_for_cpu_seconds(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/FEDERATION_LEGION.json").write_text(
        json.dumps({"ranks": [{"name_de": "Tiro", "min_cpu_seconds": 0}, {"name_de": "Miles", "min_cpu_seconds": 300}]}),
        encoding="utf-8",
    )
    assert rank_for_cpu_seconds(tmp_path, 0)["name_de"] == "Tiro"
    assert rank_for_cpu_seconds(tmp_path, 500)["name_de"] == "Miles"


def test_record_and_leaderboard(tmp_path: Path) -> None:
    now = _now()
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/preview_federation.json").write_text(
        json.dumps(
            {
                "workers": {
                    "w1": {
                        "worker_id": "w1",
                        "role": "compute",
                        "cpus": 8,
                        "hostname": "host-a",
                        "first_seen_utc": now,
                        "last_seen_utc": now,
                    },
                    "w2": {
                        "worker_id": "w2",
                        "role": "compute",
                        "cpus": 4,
                        "hostname": "host-b",
                        "first_seen_utc": now,
                        "last_seen_utc": now,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    record_legion_contribution(tmp_path, worker_id="w1", ok=True, kind="compute_pulse", cpu_seconds=120.0)
    record_legion_contribution(tmp_path, worker_id="w2", ok=True, kind="hub_verify", cpu_seconds=5.0)
    board = build_legion_leaderboard(tmp_path)
    assert len(board) == 2
    assert board[0]["worker_id"] == "w1"
    assert board[0]["cpu_seconds"] == 120.0
    assert board[0]["legion_number"] == 1


def test_upsert_worker_returns_legion(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "join_token": "tok"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    out = upsert_worker(
        tmp_path,
        {"worker_id": "legion-a", "role": "compute", "cpus": 16, "join_token": "tok", "hostname": "test"},
    )
    assert out["ok"] is True
    assert "legion" in out
    assert "Legionär" in out["legion"]["welcome_de"] or "Legion" in out["legion"]["welcome_de"]


def test_complete_task_updates_legion_stats(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    enqueue_task(tmp_path, {"kind": "compute_pulse", "requires": ["pulse"], "priority": 1, "seconds": 1})
    task = pull_task_for_worker(tmp_path, worker_id="w-leg", capabilities=["pulse"], cpus=2)
    assert task
    complete_task(tmp_path, task_id=str(task["id"]), worker_id="w-leg", ok=True, result={"cpu_seconds": 42.5})
    welcome = legion_welcome_for_worker(tmp_path, "w-leg")
    assert welcome.get("cpu_seconds") == 42.5 or "Willkommen" in welcome.get("welcome_de", "")


def test_build_legion_summary(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/FEDERATION_LEGION.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True)
    summary = build_legion_summary(tmp_path)
    assert summary["enabled"] is True
    assert "headline_de" in summary
