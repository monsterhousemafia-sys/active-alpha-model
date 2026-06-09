from __future__ import annotations

import json
from pathlib import Path

from analytics.king_weg_b import (
    build_recruit_package,
    is_orchestrate_only,
    reclaim_offline_active_tasks,
    update_orchestrator_weg_b,
)


def test_is_orchestrate_only_env(monkeypatch):
    monkeypatch.delenv("AA_WEG_B", raising=False)
    monkeypatch.delenv("AA_KING_ORCHESTRATE_ONLY", raising=False)
    assert is_orchestrate_only() is False
    monkeypatch.setenv("AA_WEG_B", "1")
    assert is_orchestrate_only() is True


def test_reclaim_offline_active_tasks(tmp_path: Path):
    queue = tmp_path / "evidence/federation_compute_queue.json"
    queue.parent.mkdir(parents=True)
    queue.write_text(
        json.dumps(
            {
                "pending": [],
                "active": {
                    "t1": {
                        "kind": "h1_naive_prep_chunk",
                        "worker_id": "ghost-worker",
                        "assigned_at_utc": "2026-06-07T18:00:00+00:00",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence/preview_federation.json").write_text(
        json.dumps({"workers": {}}),
        encoding="utf-8",
    )
    log = reclaim_offline_active_tasks(tmp_path)
    assert log
    doc = json.loads(queue.read_text(encoding="utf-8"))
    assert doc["active"] == {}
    assert len(doc["pending"]) == 1


def test_update_orchestrator_weg_b(tmp_path: Path):
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/H1_FEDERATION_DISPATCH.json").write_text("{}", encoding="utf-8")
    out = update_orchestrator_weg_b(tmp_path)
    assert out["ok"]
    orch = json.loads((tmp_path / "control/h1_orchestrator_model.json").read_text(encoding="utf-8"))
    assert orch.get("weg_b_active") is True
    assert orch["mom_1_benchmark_lane"]["scope"] == "federation"


def test_build_recruit_package():
    pkg = build_recruit_package(
        Path("/tmp"),
        world={"join_url": "https://x/join", "public_base_url": "https://x"},
        full_export={"full_zip": "/tmp/FULL.zip"},
    )
    assert "https://x/join" in pkg["whatsapp_de"]
    assert any("Full" in s for s in pkg["steps_de"])
