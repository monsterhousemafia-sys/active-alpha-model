"""Tests for aa_paper_monitor_status."""
from __future__ import annotations

from pathlib import Path

from aa_paper_monitor_status import build_paper_monitor_status, export_paper_monitor_status
from tests.test_monitoring_readiness import _minimal_root


def test_paper_blocked_without_v3p(tmp_path: Path):
    root = _minimal_root(tmp_path)
    status = build_paper_monitor_status(root)
    assert status["activation_status"] == "BLOCKED"
    assert status["activation_externally_approved"] is False
    assert status["operative_jobs_started"] is False
    assert status["paper_simulation_started"] is False
    assert status["paper_eligible"] is False
    assert "PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED" in status["active_blockers"]


def test_paper_no_broker_artifacts(tmp_path: Path):
    root = _minimal_root(tmp_path)
    export_paper_monitor_status(root)
    for pattern in ("*broker*", "*fill*", "*portfolio*"):
        assert not list(root.rglob(pattern))


def test_paper_blockers_include_cost_and_p9(tmp_path: Path):
    status = build_paper_monitor_status(_minimal_root(tmp_path))
    assert "COST_STRESS_GATE_NOT_PASSED" in status["active_blockers"] or "CHALLENGER_TURNOVER_NOT_VERIFIED" in status["active_blockers"]
    assert "P9_NOT_EXTERNALLY_REVIEWED" in status["active_blockers"]
