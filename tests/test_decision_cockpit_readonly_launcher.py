"""Tests for read-only Decision Cockpit standalone launcher (V5R) and smoke hook."""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "tools" / "decision_cockpit_readonly_launcher.py"

FORBIDDEN = frozenset(
    {
        "tools.active_alpha_launcher",
        "aa_ops",
        "aa_ops_refresh",
        "aa_paper_startup",
        "paper_trading_engine",
        "aa_configured_backtest",
        "aa_auto_promotion",
        "aa_shadow_champion",
    }
)


@pytest.fixture(autouse=True)
def _offscreen_qt(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication

        inst = QApplication.instance()
        if inst is None:
            QApplication([])
    except Exception:
        pass
    yield


def _launcher_source() -> str:
    return LAUNCHER.read_text(encoding="utf-8")


def test_launcher_has_no_forbidden_imports():
    tree = ast.parse(_launcher_source())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name.split(".")[0])
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module)
                imported.add(node.module.split(".")[0])
    for name in FORBIDDEN:
        assert name not in imported, f"forbidden import {name}"


def test_launcher_no_subprocess_or_shell_paths():
    src = _launcher_source().lower()
    assert "subprocess" not in src
    assert "popen" not in src
    assert "startfile" not in src
    assert "os.system" not in src


def test_launcher_main_uses_snapshot_and_gui():
    src = _launcher_source()
    assert "load_review_snapshot" in src
    assert "create_decision_cockpit_widget_from_data" in src


def test_smoke_hook_inactive_without_environment(monkeypatch):
    monkeypatch.delenv("AA_DECISION_COCKPIT_SMOKE_TEST", raising=False)
    from tools.decision_cockpit_readonly_launcher import smoke_test_enabled

    assert smoke_test_enabled() is False


def test_smoke_hook_only_active_for_exact_flag(monkeypatch):
    from tools.decision_cockpit_readonly_launcher import smoke_test_enabled

    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "1")
    assert smoke_test_enabled() is True
    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "8000")
    assert smoke_test_enabled() is False
    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "true")
    assert smoke_test_enabled() is False


def test_interactive_cockpit_disabled_for_v5r_smoke(monkeypatch):
    from tools.decision_cockpit_readonly_launcher import interactive_cockpit_enabled, smoke_test_enabled

    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "1")
    monkeypatch.delenv("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", raising=False)
    assert smoke_test_enabled() is True
    assert interactive_cockpit_enabled() is False


def test_interactive_cockpit_enabled_for_interactive_smoke(monkeypatch):
    from tools.decision_cockpit_readonly_launcher import interactive_cockpit_enabled

    monkeypatch.delenv("AA_DECISION_COCKPIT_SMOKE_TEST", raising=False)
    monkeypatch.setenv("AA_INTERACTIVE_COCKPIT_SMOKE_TEST", "1")
    assert interactive_cockpit_enabled() is True


def test_smoke_mode_self_exit_writes_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "1")
    (tmp_path / "control" / "review_snapshot").mkdir(parents=True)
    (tmp_path / "control" / "review_snapshot" / "v5r_decision_cockpit_snapshot.json").write_text(
        json.dumps(
            {
                "banners": ["READ-ONLY REVIEW SNAPSHOT"],
                "cockpit_data": {
                    "gui_read_only": True,
                    "operative_ui_actions_allowed": False,
                    "source_health": {"fail_closed": True, "blocked_for_safety": True},
                    "safety_automation": {
                        "AUTO_RESEARCH": False,
                        "AUTO_PROMOTE_PAPER": False,
                        "AUTO_PROMOTE_SIGNAL": False,
                        "AUTO_EXECUTE_REAL_MONEY": False,
                    },
                    "banners": ["READ-ONLY DECISION COCKPIT"],
                    "executive_overview": {"evidence_stage": "BACKTESTED"},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")

    from tools.decision_cockpit_readonly_launcher import main

    code = main()
    assert code == 0
    evidence = tmp_path / "evidence" / "v5r_exe_smoke_test_result.json"
    assert evidence.is_file()
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["smoke_test_mode"] is True
    assert payload["result"] == "PASS_SELF_EXIT"
    assert payload["operative_jobs_executed"] is False
    assert payload["read_only_verified"] is True


def test_smoke_mode_failure_non_zero_exit(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AA_DECISION_COCKPIT_SMOKE_TEST", "1")
    (tmp_path / "control" / "review_snapshot").mkdir(parents=True)
    (tmp_path / "control" / "review_snapshot" / "v5r_decision_cockpit_snapshot.json").write_text(
        json.dumps(
            {
                "banners": ["READ-ONLY"],
                "cockpit_data": {
                    "gui_read_only": False,
                    "operative_ui_actions_allowed": True,
                    "source_health": {},
                    "safety_automation": {},
                    "banners": [],
                    "executive_overview": {},
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")

    from tools.decision_cockpit_readonly_launcher import main

    code = main()
    assert code != 0
    payload = json.loads((tmp_path / "evidence" / "v5r_exe_smoke_test_result.json").read_text(encoding="utf-8"))
    assert payload["result"] == "FAIL_SELF_EXIT"


def test_normal_mode_does_not_auto_enable_smoke(monkeypatch):
    monkeypatch.delenv("AA_DECISION_COCKPIT_SMOKE_TEST", raising=False)
    from tools.decision_cockpit_readonly_launcher import smoke_test_enabled

    assert smoke_test_enabled() is False


def test_fail_closed_self_exit_writes_runtime_evidence(tmp_path: Path, monkeypatch):
    from aa_decision_cockpit_readonly_snapshot import build_v5r_fail_closed_test_snapshot

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AA_FAIL_CLOSED_TEST_SELF_EXIT", "1")
    monkeypatch.delenv("AA_DECISION_COCKPIT_SMOKE_TEST", raising=False)
    snap_dir = tmp_path / "control" / "review_snapshot"
    snap_dir.mkdir(parents=True)
    (snap_dir / "v5r_decision_cockpit_snapshot.json").write_text(
        json.dumps(build_v5r_fail_closed_test_snapshot()), encoding="utf-8"
    )
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")

    from tools.decision_cockpit_readonly_launcher import fail_closed_self_exit_enabled, main

    snap = json.loads((snap_dir / "v5r_decision_cockpit_snapshot.json").read_text(encoding="utf-8"))
    assert fail_closed_self_exit_enabled(snap) is True
    code = main()
    assert code == 0
    evidence = tmp_path / "evidence" / "v5r_fail_closed_runtime_test_result.json"
    assert evidence.is_file()
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload["fail_closed_test_self_exit_mode"] is True
    assert payload["invalid_evidence_condition_confirmed"] is True
    assert payload["fail_closed_state_verified_in_executable_path"] is True
    assert payload["result"] == "PASS_SELF_EXIT"


def test_smoke_subprocess_no_operative_imports(monkeypatch):
    py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        py = Path(sys.executable)
    env = os.environ.copy()
    env["AA_DECISION_COCKPIT_SMOKE_TEST"] = "1"
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [str(py), str(LAUNCHER)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    evidence = ROOT / "evidence" / "v5r_exe_smoke_test_result.json"
    assert evidence.is_file(), proc.stderr
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert payload.get("operative_import_path_found") is False
    assert payload.get("operative_jobs_executed") is False
    assert proc.returncode == 0
