"""Headless dashboard refresh — window gating and safe modes."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from analytics.headless_dashboard_refresh import in_trading_refresh_window, run_headless_refresh


def test_in_trading_refresh_window_weekday_afternoon() -> None:
    dt = datetime(2026, 6, 8, 15, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Berlin"))
    assert in_trading_refresh_window(now=dt) is True


def test_in_trading_refresh_window_saturday() -> None:
    dt = datetime(2026, 6, 6, 15, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Berlin"))
    assert in_trading_refresh_window(now=dt) is False


def test_in_trading_refresh_window_before_14() -> None:
    dt = datetime(2026, 6, 9, 10, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Europe/Berlin"))
    assert in_trading_refresh_window(now=dt) is False


def test_snapshot_skipped_outside_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "analytics.headless_dashboard_refresh.in_trading_refresh_window",
        lambda **_: False,
    )
    report = run_headless_refresh(tmp_path, mode="snapshot")
    assert report["skipped"] is True
    assert (tmp_path / "evidence/headless_refresh_latest.json").is_file()


def test_boot_mode_calls_snapshot_impl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snap = {
        "traffic": "GELB",
        "today_action_de": "Test",
        "broker": {"cash_eur": 1000.0},
        "quote_coverage": {"ok": True, "quote_coverage_label_de": "12/12", "n_ok": 12, "n_total": 12},
    }
    monkeypatch.setattr(
        "ui.live_trading_dashboard.service._refresh_snapshot_impl",
        lambda *a, **k: snap,
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.service.write_dashboard_txt",
        lambda *a, **k: tmp_path / "dashboard.txt",
    )
    monkeypatch.setattr(
        "execution.linux_security_boundary.apply_native_app_env",
        MagicMock(),
    )
    monkeypatch.setattr(
        "execution.linux_nvme_storage.apply_nvme_storage_env",
        MagicMock(),
    )
    monkeypatch.setattr(
        "analytics.operator_public_status.publish_public_status",
        MagicMock(),
    )
    monkeypatch.setattr(
        "analytics.linux_operator_scope.log_operator_action",
        MagicMock(),
    )
    monkeypatch.setattr(
        "ui.live_trading_dashboard.activity_log.log_dashboard_activity",
        lambda *a, **k: {"id": "1"},
    )

    report = run_headless_refresh(tmp_path, mode="boot", skip_window_check=True)
    assert report["ok"] is True
    assert report["traffic"] == "GELB"
