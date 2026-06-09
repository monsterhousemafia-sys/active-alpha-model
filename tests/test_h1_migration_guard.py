"""H1-Migration-Guard — Dedup, Skip-Start, Evidence-Sync."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from analytics.h1_migration_guard import (
    ensure_h1_migration_healthy,
    h1_process_inventory,
    should_skip_h1_start,
)


def test_should_skip_when_running(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda root: {"status": "RUNNING", "run_dir": "validation_runs/x_DAILY_ALPHA_H1"},
    )
    monkeypatch.setattr(
        "analytics.live_profile_governance.is_h1_backtest_sealed",
        lambda root: False,
    )
    monkeypatch.setattr(
        "analytics.h1_migration_guard.h1_process_inventory",
        lambda root: {"backtest_count": 1, "monitor_count": 1, "starter_count": 0},
    )
    skip, reason = should_skip_h1_start(tmp_path)
    assert skip is True
    assert "läuft" in reason.lower()


def test_inventory_structure(tmp_path: Path) -> None:
    inv = h1_process_inventory(tmp_path)
    assert "monitor_count" in inv
    assert "backtest_count" in inv
    assert "duplicate_risk" in inv


def test_ensure_sealed_no_restart(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.live_profile_governance.is_h1_backtest_sealed",
        lambda root: True,
    )
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda root: {"status": "COMPLETE", "run_dir": "validation_runs/x_DAILY_ALPHA_H1"},
    )
    monkeypatch.setattr(
        "analytics.h1_governance_status.sync_h1_governance_status",
        lambda root, **kw: {"sealed": True},
    )
    doc = ensure_h1_migration_healthy(tmp_path, auto_fix=False)
    assert doc.get("action") == "sealed"
    assert (tmp_path / "evidence/daily_alpha_h1_pipeline_latest.json").is_file()


def test_running_syncs_evidence(tmp_path: Path, monkeypatch) -> None:
    run = tmp_path / "validation_runs/20260606T000000Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    monkeypatch.setattr(
        "analytics.live_profile_governance.is_h1_backtest_sealed",
        lambda root: False,
    )
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda root: {
            "status": "RUNNING",
            "run_dir": str(run.relative_to(tmp_path)).replace("\\", "/"),
            "detail_de": "Path-Simulation",
        },
    )
    monkeypatch.setattr(
        "analytics.h1_migration_guard.h1_process_inventory",
        lambda root: {"backtest_count": 1, "monitor_count": 1, "starter_count": 0, "monitors": [{"pid": 1}]},
    )
    monkeypatch.setattr(
        "analytics.h1_migration_guard._start_monitor",
        lambda root, poll_seconds=60: {"ok": True, "action": "monitor_exists"},
    )
    monkeypatch.setattr(
        "analytics.h1_governance_status.sync_h1_governance_status",
        lambda root, **kw: {"status": "RUNNING"},
    )
    doc = ensure_h1_migration_healthy(tmp_path, auto_fix=True)
    assert doc.get("action") == "running"
    ev = (tmp_path / "evidence/daily_alpha_h1_pipeline_latest.json").read_text(encoding="utf-8")
    assert "running" in ev
