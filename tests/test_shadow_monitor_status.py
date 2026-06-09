"""Tests for aa_shadow_monitor_status."""
from __future__ import annotations

from pathlib import Path

from aa_shadow_monitor_status import build_shadow_monitor_status, export_shadow_monitor_status
from tests.test_monitoring_readiness import _minimal_root


def test_shadow_blocked_without_v3s(tmp_path: Path):
    root = _minimal_root(tmp_path)
    status = build_shadow_monitor_status(root)
    assert status["activation_status"] == "BLOCKED"
    assert status["activation_externally_approved"] is False
    assert status["operative_jobs_started"] is False
    assert status["shadow_collection_started"] is False
    assert "SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED" in status["active_blockers"]


def test_shadow_no_prediction_artifacts(tmp_path: Path):
    root = _minimal_root(tmp_path)
    export_shadow_monitor_status(root)
    assert not list(root.rglob("*prediction*"))
    assert not list(root.rglob("*outcome*order*"))


def test_shadow_eligibility_false(tmp_path: Path):
    status = build_shadow_monitor_status(_minimal_root(tmp_path))
    assert status["paper_eligible"] is False
    assert status["real_money_eligible"] is False
    assert status["promotion_allowed"] is False
