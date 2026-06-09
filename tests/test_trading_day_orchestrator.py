"""Trading-day orchestrator."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from analytics.trading_day_orchestrator import run_trading_day_orchestrator


def test_orchestrator_full_writes_cockpit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    snap = {
        "traffic": "GELB",
        "today_action_de": "Test",
        "rebalance_status": {"is_due": True},
        "broker": {"cash_eur": 1000},
        "quote_coverage": {"ok": False, "quote_coverage_label_de": "4/12"},
    }
    monkeypatch.setattr(
        "analytics.live_trading_operations.run_daily_live_cycle",
        lambda *a, **k: {"ok": True, "sync_ok": True, "daily_mark": {"recorded": True}, "summary_de": "Mark OK"},
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.service._refresh_snapshot_impl",
        lambda *a, **k: snap,
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.service.write_dashboard_txt",
        lambda *a, **k: tmp_path / "dash.txt",
    )
    monkeypatch.setattr(
        "analytics.monday_ops_checklist.write_monday_checklist_to_activity_log",
        lambda *a, **k: {"ok": True, "items": ["1. test"]},
    )
    monkeypatch.setattr(
        "analytics.pilot_trading_day_warnings.collect_trading_day_warnings",
        lambda *a, **k: {"count": 1, "critical_count": 1, "must_resolve_before_trading": True},
    )
    monkeypatch.setattr(
        "analytics.h1_governance_status.sync_h1_governance_status",
        lambda *a, **k: {"status": "RUNNING", "banner_de": "H1 test"},
    )
    monkeypatch.setattr("analytics.operator_public_status.publish_public_status", MagicMock())
    monkeypatch.setattr("analytics.linux_operator_scope.log_operator_action", MagicMock())
    monkeypatch.setattr(
        "ui.live_trading_dashboard.activity_log.log_dashboard_activity",
        lambda *a, **k: {"id": "1"},
    )
    monkeypatch.setattr("execution.linux_security_boundary.apply_native_app_env", MagicMock())
    monkeypatch.setattr("execution.linux_nvme_storage.apply_nvme_storage_env", MagicMock())

    report = run_trading_day_orchestrator(tmp_path, phase="full")
    assert report.get("ok")
    assert (tmp_path / "evidence/trading_day_latest.json").is_file()
    assert (tmp_path / "evidence/trading_day_orchestrator_latest.json").is_file()
    assert report.get("next_step_de")
