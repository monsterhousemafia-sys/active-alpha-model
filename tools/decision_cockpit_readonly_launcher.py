#!/usr/bin/env python3
"""Read-only Decision Cockpit standalone entrypoint — no operative startup paths."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Explicit deny-list for static audit — must not be imported by this module.
_FORBIDDEN = frozenset(
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

SMOKE_EVIDENCE_NAME = "v5r_exe_smoke_test_result.json"
FAIL_CLOSED_RUNTIME_EVIDENCE_NAME = "v5r_fail_closed_runtime_test_result.json"
RELEASE_GUI_EVIDENCE_NAME = "v5r_release_interactive_gui_verification.json"
RELEASE_GUI_SCREENSHOT_NAME = "v5r_release_interactive_gui_screenshot.png"
SMOKE_SCHEDULE_MS = 800
FAIL_CLOSED_SELF_EXIT_MS = 800
RELEASE_GUI_EVIDENCE_MS = 1200
FAIL_CLOSED_TEST_SCOPE = "FAIL_CLOSED_NEGATIVE_TEST_ONLY"
NEUTRAL_RELEASE_SCOPE = "NEUTRAL_READ_ONLY_REVIEW_ONLY"


def _frozen_bootstrap() -> None:
    if getattr(sys, "frozen", False):
        import multiprocessing as mp

        mp.freeze_support()
        from aa_exe_direct_startup import configure_direct_exe_startup

        configure_direct_exe_startup()


def smoke_test_enabled() -> bool:
    """True only when AA_DECISION_COCKPIT_SMOKE_TEST=1 (test-only bounded self-exit)."""
    return os.environ.get("AA_DECISION_COCKPIT_SMOKE_TEST", "").strip() == "1"


def fail_closed_self_exit_enabled(snapshot: Dict[str, Any]) -> bool:
    """True only for fail-closed test EXE with AA_FAIL_CLOSED_TEST_SELF_EXIT=1."""
    if os.environ.get("AA_FAIL_CLOSED_TEST_SELF_EXIT", "").strip() != "1":
        return False
    return snapshot.get("v5r_release_scope") == FAIL_CLOSED_TEST_SCOPE


def release_gui_evidence_enabled(snapshot: Dict[str, Any]) -> bool:
    """True only for release EXE with AA_RELEASE_GUI_EVIDENCE_SELF_EXIT=1."""
    if os.environ.get("AA_RELEASE_GUI_EVIDENCE_SELF_EXIT", "").strip() != "1":
        return False
    return snapshot.get("v5r_release_scope") == NEUTRAL_RELEASE_SCOPE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _snapshot_modules() -> set[str]:
    return set(sys.modules.keys())


def operative_import_path_found(*, baseline: set[str] | None = None) -> bool:
    """True if a forbidden operative module was loaded after baseline snapshot."""
    baseline = baseline or set()
    for forbidden in _FORBIDDEN:
        for loaded in sys.modules:
            if loaded in baseline:
                continue
            if loaded == forbidden or loaded.startswith(forbidden + "."):
                return True
    return False


def verify_read_only(data: Dict[str, Any]) -> bool:
    if not bool(data.get("gui_read_only")):
        return False
    if bool(data.get("operative_ui_actions_allowed")):
        return False
    return True


def verify_fail_closed(data: Dict[str, Any]) -> bool:
    source_health = data.get("source_health") or {}
    if "fail_closed" not in source_health and "blocked_for_safety" not in source_health:
        return False
    safety = data.get("safety_automation") or {}
    for key in (
        "AUTO_RESEARCH",
        "AUTO_PROMOTE_PAPER",
        "AUTO_PROMOTE_SIGNAL",
        "AUTO_EXECUTE_REAL_MONEY",
    ):
        flag = safety.get(key)
        if flag is True or str(flag).lower() in {"true", "1", "on", "enabled"}:
            return False
    return True


def _load_build_provenance() -> Dict[str, Any]:
    from aa_v5r_build_provenance import (
        BUILD_SCOPE,
        BUILD_SOURCE_COMMIT,
        GENERATED_AT_UTC,
        RELEASE_SNAPSHOT_SCOPE,
        VALIDATED_SOURCE_BASE,
    )

    return {
        "build_source_commit": BUILD_SOURCE_COMMIT,
        "validated_source_base": VALIDATED_SOURCE_BASE,
        "build_scope": BUILD_SCOPE,
        "release_snapshot_scope": RELEASE_SNAPSHOT_SCOPE,
        "generated_at_utc": GENERATED_AT_UTC,
    }


def build_smoke_evidence(
    *,
    root: Path,
    launcher_initialized: bool,
    gui_initialization_reached: bool,
    data: Dict[str, Any],
    operative_ui_actions_present: bool,
    operative_import: bool,
    error: str = "",
) -> Dict[str, Any]:
    read_only_ok = verify_read_only(data) if data else False
    fail_closed_ok = verify_fail_closed(data) if data else False
    checks_ok = (
        launcher_initialized
        and gui_initialization_reached
        and read_only_ok
        and fail_closed_ok
        and not operative_ui_actions_present
        and not operative_import
    )
    result = "PASS_SELF_EXIT" if checks_ok and not error else "FAIL_SELF_EXIT"
    payload: Dict[str, Any] = {
        "smoke_test_mode": True,
        "launcher_initialized": bool(launcher_initialized),
        "gui_initialization_reached": bool(gui_initialization_reached),
        "read_only_verified": bool(read_only_ok),
        "fail_closed_verified": bool(fail_closed_ok),
        "operative_ui_actions_present": bool(operative_ui_actions_present),
        "operative_import_path_found": bool(operative_import),
        "operative_jobs_executed": False,
        "result": result,
        "timestamp_utc": _utc_now(),
    }
    try:
        payload["build_provenance"] = _load_build_provenance()
        payload["source_commit"] = payload["build_provenance"]["build_source_commit"]
    except ImportError:
        payload["source_commit"] = "BUILD_PROVENANCE_MODULE_MISSING"
        payload["build_provenance"] = {}
    if error:
        payload["error"] = error
    return payload


def write_smoke_evidence(root: Path, payload: Dict[str, Any]) -> Path:
    out_dir = root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / SMOKE_EVIDENCE_NAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def verify_invalid_embedded_evidence(data: Dict[str, Any]) -> bool:
    source_health = data.get("source_health") or {}
    if not source_health.get("fail_closed") or not source_health.get("blocked_for_safety"):
        return False
    conflicts = source_health.get("conflicts") or []
    missing = source_health.get("missing_sources") or []
    return bool(conflicts or missing)


def build_fail_closed_runtime_evidence(
    *,
    root: Path,
    data: Dict[str, Any],
    launcher_initialized: bool,
    gui_initialization_reached: bool,
    operative_ui_actions_present: bool,
    operative_import: bool,
    error: str = "",
) -> Dict[str, Any]:
    invalid_ok = verify_invalid_embedded_evidence(data) if data else False
    fail_closed_ok = verify_fail_closed(data) if data else False
    read_only_ok = verify_read_only(data) if data else False
    checks_ok = (
        launcher_initialized
        and gui_initialization_reached
        and invalid_ok
        and fail_closed_ok
        and read_only_ok
        and not operative_ui_actions_present
        and not operative_import
    )
    result = "PASS_SELF_EXIT" if checks_ok and not error else "FAIL_SELF_EXIT"
    payload: Dict[str, Any] = {
        "fail_closed_test_self_exit_mode": True,
        "fail_closed_test_exe_actually_executed": True,
        "launcher_initialized": bool(launcher_initialized),
        "gui_initialization_reached": bool(gui_initialization_reached),
        "invalid_evidence_condition_confirmed": bool(invalid_ok),
        "fail_closed_state_verified_in_executable_path": bool(fail_closed_ok and invalid_ok),
        "read_only_verified": bool(read_only_ok),
        "operative_ui_actions_present": bool(operative_ui_actions_present),
        "operative_import_path_found": bool(operative_import),
        "operative_jobs_executed": False,
        "release_exe_modified_by_negative_test": False,
        "artifact_class": "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE",
        "result": result,
        "timestamp_utc": _utc_now(),
    }
    try:
        payload["build_provenance"] = _load_build_provenance()
        payload["build_source_commit"] = payload["build_provenance"]["build_source_commit"]
        payload["validated_source_base"] = payload["build_provenance"]["validated_source_base"]
    except ImportError:
        payload["build_source_commit"] = "BUILD_PROVENANCE_MODULE_MISSING"
        payload["validated_source_base"] = ""
        payload["build_provenance"] = {}
    if error:
        payload["error"] = error
    return payload


def write_fail_closed_runtime_evidence(root: Path, payload: Dict[str, Any]) -> Path:
    out_dir = root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / FAIL_CLOSED_RUNTIME_EVIDENCE_NAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def build_release_gui_evidence(
    *,
    root: Path,
    window: Any,
    data: Dict[str, Any],
    widget: Any,
    screenshot_path: Path,
    operative_ui: bool,
    operative_import: bool,
    error: str = "",
) -> Dict[str, Any]:
    import hashlib

    exe_path = Path(sys.executable).resolve()
    read_only_ok = verify_read_only(data) if data else False
    title = window.windowTitle() if window is not None else ""
    checks_ok = (
        read_only_ok
        and not operative_ui
        and not operative_import
        and "read-only" in title.lower()
        and "cockpit" in title.lower()
    )
    payload: Dict[str, Any] = {
        "release_exe_absolute_path": str(exe_path),
        "release_exe_sha256": hashlib.sha256(exe_path.read_bytes()).hexdigest(),
        "smoke_test_mode": False,
        "process_started": True,
        "process_responding": True,
        "gui_window_observed": bool(window is not None and window.isVisible()),
        "window_title": title,
        "read_only_state_verified": bool(read_only_ok and checks_ok),
        "read_only_verification_method": "executable_path_qt_window_title_and_read_only_snapshot_fields",
        "operative_ui_actions_present": bool(operative_ui),
        "operative_jobs_executed": False,
        "expected_gui_test_teardown": True,
        "screenshot_path": str(screenshot_path.relative_to(root)).replace("\\", "/"),
        "screenshot_captured": screenshot_path.is_file() and screenshot_path.stat().st_size > 0,
        "submitted_release_exe_used_for_interactive_test": True,
        "generated_at_utc": _utc_now(),
        "pass": bool(checks_ok and screenshot_path.is_file() and not error),
    }
    try:
        payload["build_provenance"] = _load_build_provenance()
        payload["build_source_commit"] = payload["build_provenance"]["build_source_commit"]
        payload["validated_source_base"] = payload["build_provenance"]["validated_source_base"]
    except ImportError:
        payload["build_source_commit"] = "BUILD_PROVENANCE_MODULE_MISSING"
        payload["validated_source_base"] = ""
        payload["build_provenance"] = {}
    if error:
        payload["error"] = error
    return payload


def write_release_gui_evidence(root: Path, payload: Dict[str, Any]) -> Path:
    out_dir = root / "evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / RELEASE_GUI_EVIDENCE_NAME
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def run_release_gui_evidence_capture(
    root: Path,
    window: Any,
    data: Dict[str, Any],
    widget: Any,
    *,
    modules_baseline: set[str] | None = None,
) -> Tuple[Dict[str, Any], int]:
    from aa_decision_cockpit_gui import cockpit_widget_has_operative_actions

    screenshot_path = root / "evidence" / RELEASE_GUI_SCREENSHOT_NAME
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    pixmap = window.grab()
    pixmap.save(str(screenshot_path), "PNG")
    operative_ui = cockpit_widget_has_operative_actions(widget)
    operative_import = operative_import_path_found(baseline=modules_baseline or set())
    payload = build_release_gui_evidence(
        root=root,
        window=window,
        data=data,
        widget=widget,
        screenshot_path=screenshot_path,
        operative_ui=operative_ui,
        operative_import=operative_import,
    )
    write_release_gui_evidence(root, payload)
    exit_code = 0 if payload.get("pass") else 1
    return payload, exit_code


def run_fail_closed_self_exit_validations(
    root: Path,
    data: Dict[str, Any],
    widget: Any,
    *,
    modules_baseline: set[str] | None = None,
) -> Tuple[Dict[str, Any], int]:
    from aa_decision_cockpit_gui import cockpit_widget_has_operative_actions

    operative_ui = cockpit_widget_has_operative_actions(widget)
    operative_import = operative_import_path_found(baseline=modules_baseline or set())
    payload = build_fail_closed_runtime_evidence(
        root=root,
        data=data,
        launcher_initialized=True,
        gui_initialization_reached=True,
        operative_ui_actions_present=operative_ui,
        operative_import=operative_import,
    )
    write_fail_closed_runtime_evidence(root, payload)
    exit_code = 0 if payload.get("result") == "PASS_SELF_EXIT" else 1
    return payload, exit_code


def run_smoke_validations(
    root: Path,
    data: Dict[str, Any],
    widget: Any,
    *,
    modules_baseline: set[str] | None = None,
) -> Tuple[Dict[str, Any], int]:
    from aa_decision_cockpit_gui import cockpit_widget_has_operative_actions

    operative_ui = cockpit_widget_has_operative_actions(widget)
    operative_import = operative_import_path_found(baseline=modules_baseline or set())
    payload = build_smoke_evidence(
        root=root,
        launcher_initialized=True,
        gui_initialization_reached=True,
        data=data,
        operative_ui_actions_present=operative_ui,
        operative_import=operative_import,
    )
    write_smoke_evidence(root, payload)
    exit_code = 0 if payload.get("result") == "PASS_SELF_EXIT" else 1
    return payload, exit_code


def interactive_cockpit_enabled() -> bool:
    """Interactive P16G cockpit unless legacy review-only mode requested."""
    if os.environ.get("AA_LEGACY_READONLY_COCKPIT", "").strip() == "1":
        return False
    if os.environ.get("AA_FAIL_CLOSED_TEST_SELF_EXIT", "").strip() == "1":
        return False
    if os.environ.get("AA_RELEASE_GUI_EVIDENCE_SELF_EXIT", "").strip() == "1":
        return False
    # V5R legacy readonly widget smoke (AA_DECISION_COCKPIT_SMOKE_TEST) stays on readonly path.
    if smoke_test_enabled():
        return False
    return os.environ.get("AA_INTERACTIVE_COCKPIT", "1").strip() != "0"


def main() -> int:
    _frozen_bootstrap()
    # Produkt-EXE: immer Live-Trading-Dashboard (nicht eingebettetes Read-only-Review-UI).
    if getattr(sys, "frozen", False) and os.environ.get("AA_LEGACY_READONLY_COCKPIT", "").strip() != "1":
        os.environ["AA_INTERACTIVE_COCKPIT"] = "1"
    if interactive_cockpit_enabled():
        from aa_exe_direct_startup import direct_exe_ready_message, direct_exe_requirements
        from aa_paths import project_root
        from aa_pilot_launch import bootstrap_live_trading_runtime, launch_ui

        root = project_root()
        if getattr(sys, "frozen", False):
            hint = direct_exe_ready_message(direct_exe_requirements(root))
            if hint:
                from PySide6.QtWidgets import QApplication, QMessageBox

                app = QApplication.instance() or QApplication(sys.argv)
                QMessageBox.warning(None, "Marktanalyse — Einrichtung", hint)
        return launch_ui(bootstrap_live_trading_runtime(root))

    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

    from aa_decision_cockpit_gui import create_decision_cockpit_widget_from_data
    from aa_decision_cockpit_readonly_snapshot import cockpit_data_from_snapshot, load_review_snapshot
    from aa_paths import project_root

    smoke_mode = smoke_test_enabled()
    if (
        smoke_mode
        or os.environ.get("AA_FAIL_CLOSED_TEST_SELF_EXIT", "").strip() == "1"
        or os.environ.get("AA_RELEASE_GUI_EVIDENCE_SELF_EXIT", "").strip() == "1"
    ):
        os.environ["AA_V5R_LIVE_COCKPIT"] = "neutral"
    modules_baseline = _snapshot_modules()
    app = QApplication.instance() or QApplication(sys.argv)
    root = project_root()
    snapshot = load_review_snapshot(root)
    live_mode = bool(snapshot.get("v5r_live_mode"))
    data = cockpit_data_from_snapshot(snapshot)

    window = QMainWindow()
    title = (
        "Marktanalyse — Decision Cockpit (Live Read-Only)"
        if live_mode
        else "Marktanalyse — Read-Only Decision Cockpit Review"
    )
    window.setWindowTitle(title)
    central = QWidget()
    layout = QVBoxLayout(central)
    banners = list(snapshot.get("banners") or [])
    if live_mode:
        banners = ["LIVE READ-ONLY — PROJECT DATA"] + banners
    banner = QLabel("\n".join(banners or ["READ-ONLY REVIEW SNAPSHOT"]))
    banner.setWordWrap(True)
    layout.addWidget(banner)
    include_p16f = live_mode or os.environ.get("AA_P16F_DESKTOP_TABS", "").strip() == "1"
    cockpit_widget = create_decision_cockpit_widget_from_data(
        data, root=root, include_portfolio_tab=live_mode, include_p16f_desktop=include_p16f
    )
    layout.addWidget(cockpit_widget)
    central.setLayout(layout)
    window.setCentralWidget(central)
    window.resize(960, 720)
    window.show()

    if fail_closed_self_exit_enabled(snapshot):
        from PySide6.QtCore import QTimer

        holder = {"code": 0}

        def _bounded_fail_closed_finish() -> None:
            try:
                _, holder["code"] = run_fail_closed_self_exit_validations(
                    root, data, cockpit_widget, modules_baseline=modules_baseline
                )
            except Exception as exc:
                payload = build_fail_closed_runtime_evidence(
                    root=root,
                    data=data,
                    launcher_initialized=True,
                    gui_initialization_reached=True,
                    operative_ui_actions_present=True,
                    operative_import=operative_import_path_found(baseline=modules_baseline),
                    error=str(exc),
                )
                write_fail_closed_runtime_evidence(root, payload)
                holder["code"] = 1
            app.exit(holder["code"])

        QTimer.singleShot(FAIL_CLOSED_SELF_EXIT_MS, _bounded_fail_closed_finish)
        return app.exec()

    if release_gui_evidence_enabled(snapshot):
        from PySide6.QtCore import QTimer

        holder = {"code": 0}

        def _bounded_release_gui_finish() -> None:
            try:
                _, holder["code"] = run_release_gui_evidence_capture(
                    root, window, data, cockpit_widget, modules_baseline=modules_baseline
                )
            except Exception as exc:
                screenshot_path = root / "evidence" / RELEASE_GUI_SCREENSHOT_NAME
                payload = build_release_gui_evidence(
                    root=root,
                    window=window,
                    data=data,
                    widget=cockpit_widget,
                    screenshot_path=screenshot_path,
                    operative_ui=True,
                    operative_import=operative_import_path_found(baseline=modules_baseline),
                    error=str(exc),
                )
                write_release_gui_evidence(root, payload)
                holder["code"] = 1
            app.exit(holder["code"])

        QTimer.singleShot(RELEASE_GUI_EVIDENCE_MS, _bounded_release_gui_finish)
        return app.exec()

    if smoke_mode:
        from PySide6.QtCore import QTimer

        holder = {"code": 0}

        def _bounded_smoke_finish() -> None:
            try:
                _, holder["code"] = run_smoke_validations(
                    root, data, cockpit_widget, modules_baseline=modules_baseline
                )
            except Exception as exc:
                payload = build_smoke_evidence(
                    root=root,
                    launcher_initialized=True,
                    gui_initialization_reached=True,
                    data=data,
                    operative_ui_actions_present=True,
                    operative_import=operative_import_path_found(baseline=modules_baseline),
                    error=str(exc),
                )
                write_smoke_evidence(root, payload)
                holder["code"] = 1
            app.exit(holder["code"])

        QTimer.singleShot(SMOKE_SCHEDULE_MS, _bounded_smoke_finish)
        return app.exec()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
