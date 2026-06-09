from __future__ import annotations

import json
from pathlib import Path

from analytics.federation_assignments import build_assignment_status
from analytics.federation_compute import enqueue_task, pull_task_for_worker


def _setup(root: Path) -> None:
    (root / "control").mkdir(parents=True, exist_ok=True)
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    (root / "control/preview_federation.json").write_text(
        json.dumps({"enabled": True, "stale_after_s": 900, "join_token": "tok"}),
        encoding="utf-8",
    )
    (root / "evidence/preview_federation.json").write_text(
        json.dumps(
            {
                "workers": {
                    "w-a": {
                        "role": "compute",
                        "worker_id": "w-a",
                        "cpus": 8,
                        "hostname": "test",
                        "last_seen_utc": "2099-01-01T00:00:00+00:00",
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_assignment_status_shows_accepted_task(tmp_path: Path) -> None:
    _setup(tmp_path)
    enqueue_task(
        tmp_path,
        {"kind": "compute_pulse", "requires": ["pulse"], "priority": 1, "seconds": 10},
    )
    task = pull_task_for_worker(tmp_path, worker_id="w-a", capabilities=["pulse"], cpus=4)
    assert task is not None
    doc = build_assignment_status(tmp_path, reclaim_stale=False)
    assert doc["active_assignments"]
    assert doc["active_assignments"][0]["accepted"] is True
    assert doc["active_assignments"][0]["worker_id"] == "w-a"
    assert any(c["id"] == "tasks_accepted" and c["ok"] for c in doc["assurance_checks"])
