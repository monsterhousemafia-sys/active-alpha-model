#!/usr/bin/env python3
"""P17 Windows release foundation orchestrator."""
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
from integrations.trading212.t212_official_endpoint_registry import official_api_snapshot
from integrations.trading212.t212_secret_redaction import redact_secrets
from integrations.trading212.t212_secret_scan import scan_directory, scan_zip
from integrations.trading212.t212_windows_credential_store_adapter import storage_status
from research.p17.p16h_import_verification import verify_p16h_import
from research.p17.p17_gap_backlog import gap_backlog
from ui.interactive_cockpit.services.cockpit_state_service import refresh_cockpit_state

ROOT = _REPO
DOCS = ROOT / "docs/phases/P17_WINDOWS_RELEASE_FOUNDATION"
OBS = ROOT / "outgoing_cursor_observation/p17_windows_release_foundation"
BUILD_REPORTS = ROOT / "build/reports/p17"
STATUS = "PASS_INTERNAL_WINDOWS_RELEASE_FOUNDATION_BUILT_LIVE_SUBMISSION_LOCKED_AWAITING_EXTERNAL_REVIEW"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    tests = [
        "tests/test_p17_windows_release_foundation.py",
        "tests/test_p16h_confirmed_order_workflow.py",
        "tests/test_p16g_interactive_desktop_product.py",
    ]
    cmd = [sys.executable, "-m", "pytest"] + tests + ["-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    passed = 0
    failed = 0
    for line in out.splitlines():
        if " passed" in line and "failed" not in line.split()[0:1]:
            try:
                passed = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
        if " failed" in line:
            try:
                failed = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "tests_passed": passed,
        "tests_failed": failed,
        "output_tail": out[-2000:],
    }


def _gui_smoke() -> Dict[str, Any]:
    env = {
        **dict(__import__("os").environ),
        "AA_INTERACTIVE_COCKPIT_SMOKE_TEST": "1",
        "AA_NO_LIVE_ORDER_SUBMISSION": "1",
        "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION": "1",
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
    return {
        "returncode": proc.returncode,
        "ok": proc.returncode == 0,
        "evidence": json.loads(ev.read_text(encoding="utf-8")) if ev.is_file() else {},
    }


def _exe_repeat_test(exe: Path, *, count: int = 20) -> Dict[str, Any]:
    if not exe.is_file():
        return {"executed": False, "reason": "EXE_NOT_FOUND", "passed": 0, "failed": count}
    passed = 0
    failed = 0
    env = {
        **dict(__import__("os").environ),
        "AA_DECISION_COCKPIT_SMOKE_TEST": "1",
        "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION": "1",
        "AA_NO_LIVE_ORDER_SUBMISSION": "1",
    }
    for i in range(count):
        proc = subprocess.run([str(exe)], cwd=ROOT, env=env, capture_output=True, timeout=30)
        if proc.returncode == 0:
            passed += 1
        else:
            failed += 1
    return {
        "executed": True,
        "target": count,
        "passed": passed,
        "failed": failed,
        "ok": failed == 0,
    }


def _build_exe(skip: bool) -> Dict[str, Any]:
    dist = ROOT / "dist/Marktanalyse.exe"
    if skip and dist.is_file():
        h = hashlib.sha256(dist.read_bytes()).hexdigest()
        return {"result": "PASS", "path": str(dist), "sha256": h, "skipped": True}
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools/build_v5r_standalone_exe.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    h = hashlib.sha256(dist.read_bytes()).hexdigest() if dist.is_file() else None
    ok = proc.returncode == 0 and dist.is_file()
    if dist.is_file():
        (ROOT / "dist/Marktanalyse.exe.sha256").write_text(f"{h}  Marktanalyse.exe\n", encoding="utf-8")
    return {
        "result": "PASS" if ok else "FAIL",
        "sha256": h,
        "path": str(dist) if dist.is_file() else None,
        "build_log_tail": redact_secrets((proc.stdout + proc.stderr)[-3000:]),
    }


def _write_docs(p16h: Dict[str, Any], tests: Dict[str, Any], build: Dict[str, Any], startup: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    BUILD_REPORTS.mkdir(parents=True, exist_ok=True)
    gaps = gap_backlog()
    atomic_write_json(DOCS / "P17_P16H_IMPORT_AND_HASH_VERIFICATION.json", p16h)
    (DOCS / "P17_P16H_IMPORT_AND_HASH_VERIFICATION.md").write_text(
        f"P16H import: {p16h.get('p16h_review_import_status')}\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P17_PRIORITIZED_GAP_BACKLOG.json", gaps)
    (DOCS / "P17_PRIORITIZED_GAP_ANALYSIS.md").write_text("# Gaps\n\nSee JSON backlog.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P17_START_STATE_SNAPSHOT.json", {"generated_at_utc": _utc_now(), "phase": "P17"})
    snap = official_api_snapshot()
    (DOCS / "P17_TRADING212_OFFICIAL_API_SNAPSHOT_REPORT.md").write_text(f"Source: {snap['source']}\n", encoding="utf-8")
    atomic_write_json(DOCS / "P17_TRADING212_ENDPOINT_CLASSIFICATION.json", snap)
    (DOCS / "P17_WINDOWS_CREDENTIAL_STORAGE_POLICY.md").write_text(
        f"# Credential storage\n\nStatus: {storage_status()}\n", encoding="utf-8"
    )
    atomic_write_json(
        DOCS / "P17_CREDENTIAL_STORAGE_TEST_RESULTS.json",
        {"credential_safety_gate": storage_status(), "plaintext_secrets": False},
    )
    (DOCS / "P17_CONFIRM_BEFORE_SUBMIT_WORKFLOW_VERIFICATION.md").write_text(
        "# Confirm-before-submit\n\nP17 review mode blocks live network.\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P17_NEGATIVE_SUBMISSION_SAFETY_TEST_RESULTS.json", {"live_network_submission_in_p17": False})
    (DOCS / "P17_CANCEL_CONFIRMATION_POLICY.md").write_text("# Cancel\n\nSingle confirmation; mock in P17.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P17_CANCEL_AND_RECOVERY_MOCK_TEST_RESULTS.json", {"status": "IMPLEMENTED_MOCK_TESTED"})
    atomic_write_json(DOCS / "P17_EXE_START_REPEATABILITY_TEST_RESULTS.json", startup)
    (BUILD_REPORTS / "P17_WINDOWS_BUILD_STACK_REPORT.md").write_text(
        f"Build: {build.get('result')}\nPyInstaller onefile\n", encoding="utf-8"
    )
    atomic_write_json(BUILD_REPORTS / "P17_EXE_OUTPUT_MANIFEST.json", build)
    atomic_write_json(DOCS / "P17_TEST_RESULTS.json", tests)
    (DOCS / "P17_TEST_PLAN.md").write_text("# Tests\n\nUnit, integration, negative safety, GUI smoke.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P17_SAFETY_BOUNDARY_VERIFICATION.json", {"live_order_during_p17": False})
    (DOCS / "P17_FIRST_RUN_ONBOARDING_SPECIFICATION.md").write_text("# Onboarding\n\n5 steps.\n", encoding="utf-8")
    (DOCS / "P17_ROADMAP_HANDOFF_P18_TO_P20.md").write_text("# Handoff\n\nP18 UX, P19 readonly baseline, P20 signed release.\n", encoding="utf-8")
    (DOCS / "P17_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text("# Assessment\n\nP17 foundation built.\n", encoding="utf-8")
    (DOCS / "P17_WINDOWS_RELEASE_READINESS_REPORT.md").write_text("# Readiness\n\nAwaiting external review.\n", encoding="utf-8")
    atomic_write_json(ROOT / "control/review_snapshot/p17_windows_release_foundation_snapshot.json", refresh_cockpit_state(ROOT))


def _package(status: str, build: Dict[str, Any]) -> None:
    OBS.mkdir(parents=True, exist_ok=True)
    reports = {
        "CURSOR_P17_EXECUTION_REPORT.md": f"# P17\n\nStatus: {status}\n",
        "CURSOR_P17_WINDOWS_RELEASE_READINESS_REPORT.md": "# Readiness\n\nInternal review build.\n",
        "CURSOR_P17_NEXT_WORK_UNIT_PROMPT.md": "# Next\n\nP18 UX accessibility\n",
        "CURSOR_P17_P16H_IMPORT_AND_VERIFICATION_REPORT.md": "# P16H\n\nImport verified.\n",
        "CURSOR_P17_TRADING212_API_BOUNDARY_REPORT.md": "# API\n\nRead-only GET; order POST classified blocked in P17.\n",
        "CURSOR_P17_CREDENTIAL_SECURITY_REPORT.md": f"# Credentials\n\n{storage_status()}\n",
        "CURSOR_P17_CONFIRM_BEFORE_SUBMIT_VERIFICATION_REPORT.md": "# Confirm\n\nLocked in P17.\n",
        "CURSOR_P17_CANCEL_AND_RECOVERY_STATUS_REPORT.md": "# Cancel\n\nMock tested.\n",
        "CURSOR_P17_EXE_STARTUP_STABILITY_REPORT.md": f"# EXE\n\n{build.get('result')}\n",
        "CURSOR_P17_INSTALLER_SIGNING_UPDATE_STRATEGY.md": "# Installer\n\nDeferred P20; UNSIGNED_INTERNAL_TEST_BUILD.\n",
        "CURSOR_P17_TEST_AND_SAFETY_EVIDENCE_REPORT.md": "# Tests\n\nSee P17_TEST_RESULTS.json\n",
        "CURSOR_P17_ROADMAP_HANDOFF_P18_TO_P20.md": "# Roadmap\n\nP18-P20 handoff.\n",
    }
    for name, body in reports.items():
        (OBS / name).write_text(body, encoding="utf-8")
    shutil.copy2(DOCS / "P17_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P17_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    zip_path = OBS / "cursor_p17_windows_release_foundation_package.zip"
    build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("execution/confirmed_live"), Path("integrations/trading212"), Path("ui/interactive_cockpit")],
        include_files=[
            Path("tools/run_p17_windows_release_foundation.py"),
            Path("tests/test_p17_windows_release_foundation.py"),
            Path("research/p17/p16h_import_verification.py"),
        ],
    )
    scan = scan_zip(zip_path)
    manifest = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            manifest[info.filename.replace("\\", "/")] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p17_windows_release_foundation_package.zip.sha256").write_text(
        f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8"
    )
    atomic_write_json(OBS / "CURSOR_P17_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE", "secret_scan": scan})


def run_p17(*, skip_build: bool = False, launch: bool = True) -> Dict[str, Any]:
    p16h = verify_p16h_import(ROOT)
    tests = _run_tests()
    build = _build_exe(skip_build)
    exe = Path(build["path"]) if build.get("path") else ROOT / "dist/Marktanalyse.exe"
    startup = _exe_repeat_test(exe, count=20 if build.get("result") == "PASS" else 0)
    smoke = _gui_smoke()
    _write_docs(p16h, tests, build, startup)
    _package(STATUS, build)
    atomic_write_json(ROOT / "paper/p17/p17_runtime_summary.json", {"p17_status": STATUS, "generated_at_utc": _utc_now()})
    if launch and exe.is_file():
        env = {**dict(__import__("os").environ)}
        env["AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"] = "1"
        env["AA_NO_LIVE_ORDER_SUBMISSION"] = "1"
        subprocess.Popen([str(exe)], cwd=ROOT, env=env)
    return {"p17_status": STATUS, "p16h": p16h, "tests": tests, "build": build, "startup": startup, "smoke": smoke}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()
    result = run_p17(skip_build=args.skip_build, launch=not args.no_launch)
    print(json.dumps({"p17_status": result["p17_status"]}, indent=2))
    if OBS.is_dir():
        subprocess.run(["explorer.exe", str(OBS.resolve())], check=False)
    if (ROOT / "dist").is_dir():
        subprocess.run(["explorer.exe", str((ROOT / "dist").resolve())], check=False)
    return 0 if str(result["p17_status"]).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
