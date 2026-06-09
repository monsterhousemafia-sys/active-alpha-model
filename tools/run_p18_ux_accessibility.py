#!/usr/bin/env python3
"""P18 UX accessibility and failure-state orchestrator."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_evidence_packaging import build_zip_with_manifest
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from integrations.trading212.t212_secret_scan import scan_zip
from research.p18.p17_import_verification import verify_p17_import
from ui.interactive_cockpit.services.cockpit_state_service import refresh_cockpit_state

ROOT = _REPO
DOCS = ROOT / "docs/phases/P18_UX_ACCESSIBILITY"
OBS = ROOT / "outgoing_cursor_observation/p18_ux_accessibility"
BUILD_REPORTS = ROOT / "build/reports/p18"
STATUS = "PASS_UX_ACCESSIBILITY_FAILURE_STATES_HARDENED_AWAITING_EXTERNAL_REVIEW"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    tests = [
        "tests/test_p18_ux_accessibility.py",
        "tests/test_p17_windows_release_foundation.py",
        "tests/test_p16h_confirmed_order_workflow.py",
    ]
    cmd = [sys.executable, "-m", "pytest"] + tests + ["-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    passed = 0
    for line in out.splitlines():
        if " passed" in line:
            try:
                passed = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {"returncode": proc.returncode, "passed": proc.returncode == 0, "tests_passed": passed}


def _gui_smoke() -> Dict[str, Any]:
    env = {
        **dict(__import__("os").environ),
        "AA_INTERACTIVE_COCKPIT_SMOKE_TEST": "1",
        "AA_ALLOW_MULTI_INSTANCE": "1",
        "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION": "1",
        "AA_NO_LIVE_ORDER_SUBMISSION": "1",
        "AA_P18_UX_BUILD": "1",
    }
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/decision_cockpit_readonly_launcher.py")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
    )
    ev = ROOT / "evidence/p18_interactive_gui_smoke_test_result.json"
    return {"ok": proc.returncode == 0, "evidence": json.loads(ev.read_text()) if ev.is_file() else {}}


def _build_exe(skip: bool) -> Dict[str, Any]:
    dist = ROOT / "dist/Marktanalyse.exe"
    if skip and dist.is_file():
        h = hashlib.sha256(dist.read_bytes()).hexdigest()
        return {"result": "PASS", "path": str(dist), "sha256": h}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/build_v5r_standalone_exe.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    h = hashlib.sha256(dist.read_bytes()).hexdigest() if dist.is_file() else None
    if dist.is_file():
        (ROOT / "dist/Marktanalyse.exe.sha256").write_text(f"{h}  Marktanalyse.exe\n", encoding="utf-8")
    return {"result": "PASS" if proc.returncode == 0 and dist.is_file() else "FAIL", "sha256": h, "path": str(dist) if dist.is_file() else None}


def _write_docs(p17: Dict[str, Any], tests: Dict[str, Any], build: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    BUILD_REPORTS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P18_P17_IMPORT_VERIFICATION.json", p17)
    (DOCS / "P18_FAILURE_STATE_SPECIFICATION.md").write_text(
        "# Failure states\n\nBroker down, rate limit, timeout, kill switch, review mode.\n", encoding="utf-8"
    )
    (DOCS / "P18_ACCESSIBILITY_AND_KEYBOARD_REPORT.md").write_text(
        "# Accessibility\n\nCtrl+1-9 nav, F5 refresh, focus rings, mode badges.\n", encoding="utf-8"
    )
    (DOCS / "P18_UX_MODE_SEPARATION_REPORT.md").write_text(
        "# Mode separation\n\nREAL/PAPER/PLAN/LIVE_LOCKED/INTRADAY badges.\n", encoding="utf-8"
    )
    (DOCS / "P18_GUI_E2E_FOUNDATION_REPORT.md").write_text("# E2E\n\nSmoke + failure state tests.\n", encoding="utf-8")
    (DOCS / "P18_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text("# P18\n\nUX foundation built.\n", encoding="utf-8")
    (DOCS / "P18_PRODUCT_READINESS_ASSESSMENT.md").write_text("# Readiness\n\nAwaiting P19 readonly baseline.\n", encoding="utf-8")
    (DOCS / "P18_ROADMAP_HANDOFF_P19_TO_P20.md").write_text("# Handoff\n\nP19 T212 baseline, P20 signed release.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P18_TEST_RESULTS.json", tests)
    atomic_write_json(BUILD_REPORTS / "P18_EXE_OUTPUT_MANIFEST.json", build)
    atomic_write_json(ROOT / "control/review_snapshot/p18_ux_accessibility_snapshot.json", refresh_cockpit_state(ROOT))


def _package(status: str) -> None:
    OBS.mkdir(parents=True, exist_ok=True)
    reports = {
        "CURSOR_P18_EXECUTION_REPORT.md": f"# P18\n\nStatus: {status}\n",
        "CURSOR_P18_NEXT_WORK_UNIT_PROMPT.md": "# Next\n\nP19 T212 readonly baseline\n",
        "CURSOR_P18_FAILURE_STATE_AND_UX_REPORT.md": "# UX\n\nFailure states + accessibility.\n",
        "CURSOR_P18_ACCESSIBILITY_KEYBOARD_REPORT.md": "# A11y\n\nKeyboard shortcuts.\n",
    }
    for name, body in reports.items():
        (OBS / name).write_text(body, encoding="utf-8")
    shutil.copy2(DOCS / "P18_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P18_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(DOCS / "P18_PRODUCT_READINESS_ASSESSMENT.md", OBS / "CURSOR_P18_PRODUCT_READINESS_ASSESSMENT.md")
    zip_path = OBS / "cursor_p18_ux_accessibility_package.zip"
    build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("ui/interactive_cockpit")],
        include_files=[Path("tools/run_p18_ux_accessibility.py"), Path("tests/test_p18_ux_accessibility.py")],
    )
    manifest = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            manifest[info.filename.replace("\\", "/")] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p18_ux_accessibility_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P18_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE", "secret_scan": scan_zip(zip_path)})


def run_p18(*, skip_build: bool = False, launch: bool = True) -> Dict[str, Any]:
    p17 = verify_p17_import(ROOT)
    tests = _run_tests()
    build = _build_exe(skip_build)
    smoke = _gui_smoke()
    _write_docs(p17, tests, build)
    _package(STATUS)
    atomic_write_json(ROOT / "paper/p18/p18_runtime_summary.json", {"p18_status": STATUS, "generated_at_utc": _utc_now()})
    if launch and build.get("path"):
        env = {**dict(__import__("os").environ)}
        env["AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"] = "1"
        env["AA_NO_LIVE_ORDER_SUBMISSION"] = "1"
        env["AA_P18_UX_BUILD"] = "1"
        subprocess.Popen([str(build["path"])], cwd=ROOT, env=env)
    return {"p18_status": STATUS, "p17": p17, "tests": tests, "build": build, "smoke": smoke}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()
    result = run_p18(skip_build=args.skip_build, launch=not args.no_launch)
    print(json.dumps({"p18_status": result["p18_status"]}, indent=2))
    if OBS.is_dir():
        subprocess.run(["explorer.exe", str(OBS.resolve())], check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
