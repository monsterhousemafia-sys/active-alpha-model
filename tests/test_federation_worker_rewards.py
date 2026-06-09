from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from analytics.federation_compute import complete_task, enqueue_task, pull_task_for_worker
from analytics.federation_worker_rewards import (
    apply_task_reward_credit,
    build_rewards_summary,
    grant_join_stipend,
    load_rewards_policy,
    worker_has_active_task,
)
from analytics.preview_federation import upsert_worker


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _base(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "join_token": "tok", "stale_after_s": 900}),
        encoding="utf-8",
    )
    (tmp_path / "control/FEDERATION_LEGION.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/FEDERATION_WORKER_REWARDS.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "join_stipend_cpu_seconds": 50,
                "min_cpu_seconds_per_task": {"compute_pulse": 20},
            }
        ),
        encoding="utf-8",
    )


def test_apply_task_reward_credit_floor(tmp_path: Path) -> None:
    _base(tmp_path)
    credited = apply_task_reward_credit(tmp_path, kind="compute_pulse", cpu_seconds=2.0, ok=True)
    assert credited == 20.0


def test_grant_join_stipend(tmp_path: Path) -> None:
    _base(tmp_path)
    doc = grant_join_stipend(tmp_path, worker_id="w-new", is_new=True)
    assert doc.get("granted") is True
    assert doc.get("cpu_seconds") == 50.0


def test_upsert_worker_grants_join_stipend(tmp_path: Path) -> None:
    _base(tmp_path)
    out = upsert_worker(
        tmp_path,
        {"worker_id": "w-join", "role": "compute", "cpus": 4, "join_token": "tok", "hostname": "remote"},
    )
    assert out.get("ok") is True
    assert out.get("join_stipend", {}).get("granted") is True
    assert "entlohnung_de" in (out.get("legion") or {})


def test_worker_has_active_task() -> None:
    active = {"t1": {"worker_id": "w-a"}}
    assert worker_has_active_task(active, "w-a") is True
    assert worker_has_active_task(active, "w-b") is False


def test_complete_task_applies_minimum_credit(tmp_path: Path) -> None:
    _base(tmp_path)
    enqueue_task(tmp_path, {"kind": "compute_pulse", "requires": ["pulse"], "priority": 1})
    task = pull_task_for_worker(tmp_path, worker_id="w1", capabilities=["pulse"], cpus=2)
    assert task
    complete_task(tmp_path, task_id=str(task["id"]), worker_id="w1", ok=True, result={"cpu_seconds": 1.0})
    from analytics.federation_legion import load_legion_stats

    stats = load_legion_stats(tmp_path).get("workers") or {}
    assert float(stats.get("w1", {}).get("cpu_seconds") or 0) >= 20.0


def test_build_rewards_summary(tmp_path: Path) -> None:
    _base(tmp_path)
    now = _now()
    (tmp_path / "evidence/preview_federation.json").write_text(
        json.dumps(
            {
                "workers": {
                    "w1": {
                        "worker_id": "w1",
                        "role": "compute",
                        "cpus": 4,
                        "hostname": "a",
                        "first_seen_utc": now,
                        "last_seen_utc": now,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    grant_join_stipend(tmp_path, worker_id="w1", is_new=True)
    doc = build_rewards_summary(tmp_path)
    assert doc.get("ok") is True
    assert doc.get("legionnaires") >= 1
