from __future__ import annotations

import json
from pathlib import Path

from analytics.federation_compute import enqueue_task, pull_task_for_worker, worker_capabilities
from analytics.h1_federation_dispatch import (
    build_dispatch_plan,
    build_h1_asset_manifest,
    h1_worker_capable,
    inspect_h1_run,
    plan_path_chunks,
    prepare_h1_dispatch,
    sync_h1_federation_tasks,
)


def _seed_h1_run(tmp_path: Path) -> Path:
    run = tmp_path / "validation_runs/20260606T000000Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "features.parquet").write_bytes(b"x" * 1024)
    (run / "run_config_snapshot.txt").write_text("rebalance_every=1\n", encoding="utf-8")
    (run / "validation_run.log").write_text("PROGRESS\n" * 200, encoding="utf-8")
    return run


def test_plan_path_chunks_statuses() -> None:
    chunks = plan_path_chunks(last_n=30, total_steps=100, chunk_size=25, king_active_end=50)
    assert len(chunks) == 4
    assert chunks[0]["status"] == "done"
    assert chunks[1]["status"] == "king_active"
    assert chunks[2]["status"] == "pending"
    assert chunks[0]["depends_on"] is None
    assert chunks[1]["depends_on"] == chunks[0]["id"]


def test_build_h1_asset_manifest(tmp_path: Path) -> None:
    run = _seed_h1_run(tmp_path)
    rel = str(run.relative_to(tmp_path)).replace("\\", "/")
    manifest = build_h1_asset_manifest(tmp_path, rel)
    assert manifest["ready"] is True
    assert manifest["total_bytes"] >= 1024
    assert any(f["name"] == "features.parquet" for f in manifest["files"])


def test_prepare_h1_dispatch_plan_only_no_enqueue(tmp_path: Path) -> None:
    _seed_h1_run(tmp_path)
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/H1_FEDERATION_DISPATCH.json").write_text(
        json.dumps({"enabled": True, "mode": "plan_only", "enqueue_tasks": False}),
        encoding="utf-8",
    )
    (tmp_path / "tools").mkdir(parents=True)
    (tmp_path / "tools/ai_kernel.py").write_text("# k\n", encoding="utf-8")
    (tmp_path / "evidence").mkdir(parents=True)

    plan = prepare_h1_dispatch(tmp_path, sync_tasks=True)
    assert plan["chunks_total"] >= 1
    assert "features.parquet" in str(plan.get("asset_manifest") or "")
    assert sync_h1_federation_tasks(tmp_path) == []

    caps = worker_capabilities(tmp_path, bundle_kind="full")
    assert "h1" not in caps
    assert "preview" in caps


def test_h1_worker_capable_respects_config(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/H1_FEDERATION_DISPATCH.json").write_text(
        json.dumps({"enabled": False}),
        encoding="utf-8",
    )
    assert h1_worker_capable(tmp_path) is False


def test_inspect_h1_run_missing(tmp_path: Path) -> None:
    inspect = inspect_h1_run(tmp_path)
    assert inspect["status"] == "MISSING"
