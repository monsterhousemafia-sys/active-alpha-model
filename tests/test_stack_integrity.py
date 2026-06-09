from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.stack_integrity import (
    build_integrity_report,
    ensure_hub_reliable,
    persist_integrity_report,
    repair_stack,
    verify_or_repair,
)


def test_build_integrity_report_fail_closed_offline(tmp_path: Path) -> None:
    doc = build_integrity_report(tmp_path, port=1, desktop_session=False)
    assert doc.get("stack_ok") is False
    assert doc.get("hub_ok") is False
    assert doc.get("failures_de")


def test_desktop_makes_cockpit_critical(tmp_path: Path) -> None:
    doc = build_integrity_report(tmp_path, port=1, desktop_session=True)
    cockpit = next(c for c in doc["checks"] if c["id"] == "r3_cockpit")
    surface = next(c for c in doc["checks"] if c["id"] == "r3_surface_page")
    assert not cockpit.get("warn_only")
    assert not surface.get("warn_only")
    assert doc.get("stack_ok") is False
    assert any("r3_cockpit" in f for f in doc.get("failures_de") or [])


@patch("analytics.stack_integrity.is_healthy", return_value=True)
@patch("analytics.stack_integrity.hub_health")
@patch("analytics.stack_integrity.r3_health")
@patch("analytics.stack_integrity._exec_mirror_primary", return_value=True)
def test_exec_mirror_makes_cockpit_warning_only(
    _mirror_mode, mock_r3, mock_hub, _healthy, tmp_path: Path
) -> None:
    mock_hub.return_value = {"online": True, "ok": True, "route_login_ok": True}
    mock_r3.return_value = {
        "mirror_api_ok": True,
        "mirror_state_ok": True,
        "surface_page_ok": True,
        "cockpit_running": False,
    }
    doc = build_integrity_report(tmp_path, port=17890, desktop_session=True)
    cockpit = next(c for c in doc["checks"] if c["id"] == "r3_cockpit")
    assert cockpit.get("warn_only") is True
    assert doc.get("exec_mirror_only") is True
    assert doc.get("stack_ok") is True
    assert doc.get("r3_ok") is True
    assert any("r3_cockpit" in w for w in doc.get("warnings_de") or [])


def test_headless_cockpit_is_warning_only(tmp_path: Path) -> None:
    doc = build_integrity_report(tmp_path, port=1, desktop_session=False)
    cockpit = next(c for c in doc["checks"] if c["id"] == "r3_cockpit")
    assert cockpit.get("warn_only") is True
    assert doc.get("warnings_de")  # cockpit not running → warning not failure


@patch("analytics.stack_integrity.ensure_hub_reliable", return_value=17890)
@patch("analytics.stack_integrity.ensure_surface_ready", return_value=True)
@patch("analytics.stack_integrity.ensure_mirror_ready", return_value=True)
@patch("analytics.stack_integrity.build_integrity_report")
def test_repair_stack_hub_ok(mock_report, _mirror, _surface, _hub, tmp_path: Path) -> None:
    mock_report.return_value = {
        "stack_ok": True,
        "hub_ok": True,
        "r3_ok": True,
        "checks": [],
    }
    doc = repair_stack(tmp_path, persist=False)
    assert doc.get("repaired") is True
    assert any(s.get("step") == "ensure_hub" and s.get("ok") for s in doc.get("steps") or [])


@patch("analytics.stack_integrity.repair_stack")
@patch("analytics.stack_integrity.build_integrity_report")
def test_verify_or_repair_skips_when_ok(mock_build, mock_repair, tmp_path: Path) -> None:
    mock_build.return_value = {"stack_ok": True, "hub_ok": True, "r3_ok": True}
    doc = verify_or_repair(tmp_path, auto_repair=True, persist=False)
    assert doc.get("stack_ok") is True
    mock_repair.assert_not_called()


@patch("analytics.stack_integrity.repair_stack", return_value={"stack_ok": False})
@patch("analytics.stack_integrity.build_integrity_report", return_value={"stack_ok": False})
def test_verify_or_repair_calls_repair(mock_build, mock_repair, tmp_path: Path) -> None:
    doc = verify_or_repair(tmp_path, auto_repair=True, persist=False)
    mock_repair.assert_called_once()
    assert doc.get("stack_ok") is False


def test_persist_integrity_report(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True)
    doc = {"stack_ok": False, "schema_version": 1}
    path = persist_integrity_report(tmp_path, doc)
    assert path.is_file()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded.get("schema_version") == 1


@patch("analytics.stack_integrity.ensure_running", side_effect=[17890, 17890])
@patch("analytics.stack_integrity.is_healthy", side_effect=[False, True])
def test_ensure_hub_reliable_retries(_healthy, _run, tmp_path: Path) -> None:
    port = ensure_hub_reliable(tmp_path, port=17890, attempts=2)
    assert port == 17890
    assert _run.call_count == 2
