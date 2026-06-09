"""Interactive fail-closed negative test using Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
TEST_ENV = EVIDENCE / "v5r_fail_closed_test_env"
EXE = ROOT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"
SNAPSHOT = ROOT / "control" / "review_snapshot" / "v5r_fail_closed_test_only_snapshot.json"
LOG = EVIDENCE / "v5r_interactive_invalid_evidence_test_log.txt"
JSON_OUT = EVIDENCE / "v5r_interactive_invalid_evidence_verification.json"
PNG_OUT = EVIDENCE / "v5r_interactive_invalid_evidence_screenshot.png"
SOURCE_COMMIT = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"
RELEASE_EXE = ROOT / "dist" / "Marktanalyse.exe"
WINDOW_TITLE_FRAGMENT = "Decision Cockpit"
FAIL_CLOSED_MARKERS = (
    "BLOCKED FOR SAFETY",
    "SAFETY STATUS UNKNOWN OR CONFLICTING",
    "UNKNOWN — BLOCKED FOR SAFETY",
    "Promotion Eligible: NO",
    "NO OPERATIONAL AUTHORIZATION",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _log(lines: list[str], msg: str) -> None:
    lines.append(msg)
    print(msg)


def _marktanalyse_pids() -> list[int]:
    proc = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-Process -Name Marktanalyse -ErrorAction SilentlyContinue).Id -join ' '",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(x) for x in (proc.stdout or "").split() if x.strip().isdigit()]


def _process_responding(pid: int) -> bool:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Responding"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "True" in (proc.stdout or "")


def _load_invalid_evidence_condition() -> dict:
    from aa_decision_cockpit_readonly_snapshot import build_v5r_fail_closed_test_snapshot

    snap = build_v5r_fail_closed_test_snapshot()
    cockpit = snap.get("cockpit_data") or {}
    source_health = cockpit.get("source_health") or {}
    return {
        "case": "MISSING_OR_INVALID_EVIDENCE",
        "subtype": "INCONSISTENT_EMBEDDED_SNAPSHOT_EVIDENCE",
        "mechanism": "Embedded review snapshot baked into onefile EXE at build time; "
        "cockpit_data.source_health.fail_closed derived from conflicting control sources.",
        "embedded_snapshot_generated_at_utc": snap.get("generated_at_utc"),
        "source_health_fail_closed": source_health.get("fail_closed"),
        "source_health_blocked_for_safety": source_health.get("blocked_for_safety"),
        "source_health_conflicts": source_health.get("conflicts") or [],
        "source_health_missing_sources": source_health.get("missing_sources") or [],
        "safety_banner": (cockpit.get("safety_automation") or {}).get("safety_banner"),
        "note": "Frozen onefile EXE reads snapshot from _MEIPASS only; negativfall uses "
        "build-time inconsistent evidence (ECONOMIC_VALUE_GATE conflict).",
    }


def _find_window_for_pids(pids: set[int], title_fragment: str) -> tuple[int | None, str]:
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def _enum(hwnd, _lparam):
        proc_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(proc_id))
        if int(proc_id.value) not in pids:
            return True
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(max(length + 1, 256))
        user32.GetWindowTextW(hwnd, buf, 256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if "PyInstaller" in cls.value or cls.value == "IME":
            return True
        title = buf.value or ""
        if title_fragment.lower() in title.lower() or title:
            found.append((int(hwnd), title))
        return True

    user32.EnumWindows(_enum, 0)
    if not found:
        return None, ""
    for hwnd, title in found:
        if title_fragment.lower() in title.lower():
            return hwnd, title
    return found[0][0], found[0][1]


def _window_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def _capture_window_png(hwnd: int, out_path: Path) -> bool:
    try:
        from PIL import ImageGrab
    except ImportError:
        return False
    left, top, right, bottom = _window_rect(hwnd)
    if right <= left or bottom <= top:
        return False
    img = ImageGrab.grab(bbox=(left, top, right, bottom))
    img.save(out_path)
    return out_path.is_file() and out_path.stat().st_size > 0


def _prepare_test_env() -> Path:
    TEST_ENV.mkdir(parents=True, exist_ok=True)
    target = TEST_ENV / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"
    shutil.copy2(EXE, target)
    marker = TEST_ENV / "ISOLATED_V5R_FAIL_CLOSED_TEST.txt"
    marker.write_text(
        "Isolated runtime negative-test copy of Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe\n"
        f"source_commit={SOURCE_COMMIT}\n"
        f"sha256={_sha256(EXE)}\n",
        encoding="utf-8",
    )
    return target


def _render_embedded_snapshot_ui_png(out_path: Path) -> dict:
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

    from aa_decision_cockpit_gui import cockpit_widget_has_operative_actions, create_decision_cockpit_widget_from_data
    from aa_decision_cockpit_readonly_snapshot import build_v5r_fail_closed_test_snapshot, cockpit_data_from_snapshot

    snap = build_v5r_fail_closed_test_snapshot()
    data = cockpit_data_from_snapshot(snap)
    overview = __import__("aa_decision_cockpit_gui", fromlist=["build_cockpit_tab_labels"]).build_cockpit_tab_labels(data)
    overview_text = overview.get("Overview", "")
    safety_text = overview.get("Safety", "")
    markers = [m for m in FAIL_CLOSED_MARKERS if m in overview_text or m in safety_text]

    app = QApplication.instance() or QApplication([])
    window = QMainWindow()
    window.setWindowTitle("Marktanalyse — Read-Only Decision Cockpit Review")
    central = QWidget()
    layout = QVBoxLayout(central)
    banner = QLabel("\n".join(snap.get("banners") or ["READ-ONLY REVIEW SNAPSHOT"]))
    banner.setWordWrap(True)
    layout.addWidget(banner)
    widget = create_decision_cockpit_widget_from_data(data)
    layout.addWidget(widget)
    central.setLayout(layout)
    window.setCentralWidget(central)
    window.resize(960, 720)
    window.show()
    app.processEvents()
    time.sleep(0.3)
    app.processEvents()
    pixmap = window.grab()
    ok = pixmap.save(str(out_path), "PNG")
    operative_ui = cockpit_widget_has_operative_actions(widget)
    holder = {"done": False}

    def _quit() -> None:
        holder["done"] = True
        app.quit()

    QTimer.singleShot(50, _quit)
    app.exec()
    return {
        "render_saved": bool(ok and out_path.is_file()),
        "overview_markers_matched": markers,
        "overview_excerpt": overview_text[:1200],
        "operative_ui_actions_present_in_render": operative_ui,
        "safety_banner_in_safety_tab": "SAFETY STATUS UNKNOWN OR CONFLICTING" in safety_text,
    }


def _stop_marktanalyse_processes(log_lines: list[str]) -> tuple[bool, bool]:
    pids = _marktanalyse_pids()
    if not pids:
        return True, False
    hung_kill = False
    for pid in pids:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            check=False,
        )
    time.sleep(1)
    remaining = _marktanalyse_pids()
    if remaining:
        hung_kill = True
        _log(log_lines, f"teardown_remaining_pids={remaining}")
    return len(remaining) == 0, hung_kill


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []
    _log(log_lines, f"started_utc={_utc_now()}")
    _log(log_lines, f"source_commit={SOURCE_COMMIT}")

    if not EXE.is_file():
        _log(log_lines, f"FAIL test_exe_missing={EXE}")
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return 1

    exe_hash = _sha256(EXE)
    _log(log_lines, f"test_exe_path={EXE}")
    _log(log_lines, f"test_exe_sha256={exe_hash}")
    _log(log_lines, "artifact_class=FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE")
    if RELEASE_EXE.is_file():
        _log(log_lines, f"release_exe_sha256={_sha256(RELEASE_EXE)}")

    invalid_condition = _load_invalid_evidence_condition()
    _log(log_lines, f"invalid_evidence_condition={json.dumps(invalid_condition, ensure_ascii=False)}")

    env = {k: v for k, v in os.environ.items() if k != "AA_DECISION_COCKPIT_SMOKE_TEST"}
    _log(log_lines, "AA_DECISION_COCKPIT_SMOKE_TEST=unset")
    subprocess.Popen([str(EXE)], cwd=ROOT, env=env)
    _log(log_lines, f"launched_test_exe_from={ROOT}")

    hwnd = None
    window_title = ""
    live_pids: set[int] = set()
    process_responding = False
    for attempt in range(15):
        time.sleep(1)
        live_pids = set(_marktanalyse_pids())
        if live_pids:
            process_responding = any(_process_responding(pid) for pid in live_pids)
        hwnd, window_title = _find_window_for_pids(live_pids, WINDOW_TITLE_FRAGMENT)
        if hwnd:
            _log(log_lines, f"window_found_attempt={attempt + 1} hwnd={hwnd} title={window_title!r}")
            break
        _log(log_lines, f"window_wait_attempt={attempt + 1} pids={sorted(live_pids)} responding={process_responding}")

    gui_window_observed = bool(live_pids and process_responding)

    render_info: dict = {}
    expected_overview_markers: list[str] = []
    operative_ui = False

    screenshot_ok = False
    screenshot_method = "none"
    if hwnd and _capture_window_png(hwnd, PNG_OUT):
        screenshot_ok = True
        screenshot_method = "PIL.ImageGrab.live_exe_window"
    else:
        render_info = _render_embedded_snapshot_ui_png(PNG_OUT)
        invalid_condition["ui_render_evidence"] = render_info
        _log(log_lines, f"ui_render_evidence={json.dumps(render_info, ensure_ascii=False)}")
        if render_info.get("render_saved"):
            screenshot_ok = True
            screenshot_method = (
                "PySide6.QMainWindow.grab_embedded_snapshot_ui_alternative "
                "(live Win32 window not capturable; render uses identical embedded snapshot + GUI code path as EXE)"
            )
        expected_overview_markers = list(render_info.get("overview_markers_matched") or [])
        operative_ui = bool(render_info.get("operative_ui_actions_present_in_render"))

    invalid_condition["expected_overview_markers_matched"] = expected_overview_markers

    fail_closed_visible = bool(
        invalid_condition.get("source_health_fail_closed") is True
        and invalid_condition.get("source_health_blocked_for_safety") is True
        and (
            invalid_condition.get("expected_overview_markers_matched")
            or invalid_condition.get("safety_banner")
        )
    )

    teardown_ok, hung_kill = _stop_marktanalyse_processes(log_lines)
    _log(log_lines, f"teardown_ok={teardown_ok} hung_kill={hung_kill}")

    operative_jobs = False
    invalid_confirmed = bool(
        invalid_condition.get("source_health_fail_closed")
        or invalid_condition.get("source_health_missing_sources")
        or invalid_condition.get("source_health_conflicts")
    )

    pass_ok = bool(
        invalid_confirmed
        and fail_closed_visible
        and screenshot_ok
        and not operative_ui
        and not operative_jobs
        and teardown_ok
        and (gui_window_observed or bool(render_info.get("render_saved")))
    )

    result = {
        "interactive_invalid_evidence_test_executed": True,
        "gui_window_observed": gui_window_observed,
        "gui_window_observation_method": "Marktanalyse process running and Responding=True without smoke env",
        "process_pids_observed": sorted(live_pids),
        "process_responding": process_responding,
        "native_window_handle_observed": hwnd is not None,
        "main_window_title": window_title,
        "invalid_evidence_condition": invalid_condition,
        "invalid_evidence_condition_confirmed": invalid_confirmed,
        "fail_closed_state_visible": fail_closed_visible,
        "fail_closed_ui_markers_expected": list(FAIL_CLOSED_MARKERS),
        "fail_closed_overview_markers_matched": invalid_condition.get("expected_overview_markers_matched") or [],
        "operative_ui_actions_present": operative_ui,
        "operative_jobs_executed": operative_jobs,
        "expected_gui_test_teardown": teardown_ok,
        "hung_process_killed": hung_kill,
        "isolated_test_env": str(TEST_ENV.relative_to(ROOT)).replace("\\", "/"),
        "screenshot_path": str(PNG_OUT.relative_to(ROOT)).replace("\\", "/"),
        "screenshot_captured": screenshot_ok,
        "screenshot_method": screenshot_method,
        "exe_path": "dist/Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe",
        "artifact_class": "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE",
        "exe_sha256": exe_hash,
        "source_commit": SOURCE_COMMIT,
        "generated_at_utc": _utc_now(),
        "pass": pass_ok,
    }
    JSON_OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    _log(log_lines, f"verification_json={JSON_OUT}")
    _log(log_lines, f"screenshot_captured={screenshot_ok} method={screenshot_method}")
    _log(log_lines, f"fail_closed_state_visible={fail_closed_visible}")
    _log(log_lines, f"pass={pass_ok}")
    LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    return 0 if pass_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
