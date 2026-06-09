"""Snapshot freshness stamp."""
from __future__ import annotations

from pathlib import Path

from analytics.snapshot_freshness import is_snapshot_fresh, mark_snapshot_fresh, should_skip_headless_refresh


def test_mark_and_fresh(tmp_path: Path) -> None:
    assert not is_snapshot_fresh(tmp_path)
    mark_snapshot_fresh(tmp_path, source="test")
    assert is_snapshot_fresh(tmp_path)


def test_skip_headless_when_fresh(tmp_path: Path, monkeypatch) -> None:
    mark_snapshot_fresh(tmp_path, source="test")
    monkeypatch.setattr("analytics.snapshot_freshness.is_dashboard_process_running", lambda: False)
    skip, reason = should_skip_headless_refresh(tmp_path, mode="snapshot")
    assert skip is True
    assert "frisch" in reason


def test_orchestrator_never_skips_fresh(tmp_path: Path) -> None:
    mark_snapshot_fresh(tmp_path, source="test")
    skip, _ = should_skip_headless_refresh(tmp_path, mode="full")
    assert skip is False
