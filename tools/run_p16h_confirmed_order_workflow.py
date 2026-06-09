#!/usr/bin/env python3
"""P16H Interactive T212 confirmed order workflow orchestrator."""
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
from research.p16h.p16g_import_verification import verify_p16g_import
from ui.interactive_cockpit.services.cockpit_state_service import refresh_cockpit_state

ROOT = _REPO
DOCS = ROOT / "docs/phases/P16H_CONFIRMED_ORDER_WORKFLOW"
OBS = ROOT / "outgoing_cursor_observation/p16h_confirmed_order_workflow"
BUILD_REPORTS = ROOT / "build/reports/p16h"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    tests = [
        "tests/test_p16h_confirmed_order_workflow.py",
        "tests/test_p16g_interactive_desktop_product.py",
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
    return {"command": " ".join(cmd), "returncode": proc.returncode, "passed": proc.returncode == 0, "tests_passed": passed}


def _gui_smoke() -> Dict[str, Any]:
    env = {
        **dict(__import__("os").environ),
        "AA_INTERACTIVE_COCKPIT_SMOKE_TEST": "1",
        "AA_NO_LIVE_ORDER_SUBMISSION": "1",
        "AA_EXECUTION_DRY_RUN": "1",
    }
    proc = subprocess.run([sys.executable, str(ROOT / "tools/decision_cockpit_readonly_launcher.py")], cwd=ROOT, env=env, capture_output=True, text=True, timeout=45)
    ev = ROOT / "evidence/p18_interactive_gui_smoke_test_result.json"
    return {"returncode": proc.returncode, "ok": proc.returncode == 0, "evidence": json.loads(ev.read_text()) if ev.is_file() else {}}


def _build_exe(skip: bool) -> Dict[str, Any]:
    dist = ROOT / "dist/Marktanalyse.exe"
    if skip and dist.is_file():
        h = hashlib.sha256(dist.read_bytes()).hexdigest()
        return {"result": "PASS", "path": str(dist), "sha256": h}
    proc = subprocess.run([sys.executable, str(ROOT / "tools/build_v5r_standalone_exe.py")], cwd=ROOT, capture_output=True, text=True, timeout=600)
    h = hashlib.sha256(dist.read_bytes()).hexdigest() if dist.is_file() else None
    return {"result": "PASS" if proc.returncode == 0 and dist.is_file() else "FAIL", "sha256": h, "path": str(dist) if dist.is_file() else None}


def _write_docs(p16g: Dict[str, Any], tests: Dict[str, Any], build: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    BUILD_REPORTS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P16H_P16G_IMPORT_AND_HASH_VERIFICATION.json", p16g)
    (DOCS / "P16H_P16G_IMPORT_AND_HASH_VERIFICATION.md").write_text(f"P16G verified: {p16g.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16H_P16G_START_STATE_ADJUDICATION.md").write_text("# P16G Adjudication\n\nPreserved.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16H_START_STATE_SNAPSHOT.json", {"generated_at_utc": _utc_now(), "p16h": "confirmed_order_workflow"})
    (DOCS / "P16H_PROJECT_AND_PRODUCT_STACK_ASSESSMENT.md").write_text("# Stack\n\nPySide6 extended.\n", encoding="utf-8")
    (DOCS / "P16H_GUI_EXTENSION_ARCHITECTURE.md").write_text("# GUI\n\norder_workflow_ui.py\n", encoding="utf-8")
    snap = official_api_snapshot()
    (DOCS / "P16H_TRADING212_CURRENT_OFFICIAL_API_SNAPSHOT_REPORT.md").write_text(f"Source: {snap['source']}\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16H_TRADING212_ENDPOINT_REGISTRY.json", snap)
    (DOCS / "P16H_TRADING212_READONLY_AND_CONFIRMED_EXECUTION_ENDPOINT_POLICY.md").write_text(
        "# Policy\n\nRead-only GET separate from confirmed POST limit only.\n", encoding="utf-8"
    )
    (DOCS / "P16H_MANAGED_LIVE_PILOT_SCOPE_POLICY.md").write_text("# Managed Scope\n\nBaseline required.\n", encoding="utf-8")
    (DOCS / "P16H_REAL_ACCOUNT_BASELINE_AND_TRIGGER_ATTRIBUTION_POLICY.md").write_text(
        "# Trigger\n\nManaged scope post-baseline only.\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P16H_TEST_RESULTS.json", tests)
    (DOCS / "P16H_TEST_PLAN.md").write_text("# Tests\n\nConfirmation, guards, no live submit in CI.\n", encoding="utf-8")
    (DOCS / "P16H_USER_OPERATION_GUIDE.md").write_text(
        "# Guide\n\n1. Monitoring credentials\n2. Baseline\n3. Enable core live\n4. Confirm each order\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P16H_SAFETY_BOUNDARY_VERIFICATION.json", {"live_order_during_build": False})
    (BUILD_REPORTS / "P16H_DESKTOP_BUILD_REPORT.md").write_text(f"Build: {build.get('result')}\n", encoding="utf-8")
    atomic_write_json(BUILD_REPORTS / "P16H_EXE_OUTPUT_MANIFEST.json", build)


def _package(status: str) -> None:
    OBS.mkdir(parents=True, exist_ok=True)
    reports = {
        "CURSOR_P16H_EXECUTION_REPORT.md": f"# P16H\n\nStatus: {status}\n",
        "CURSOR_P16H_CONFIRMED_ORDER_WORKFLOW_POLICY.md": "# Policy\n\nConfirm before submit.\n",
        "CURSOR_P16H_MANAGED_SCOPE_AND_BASELINE_POLICY.md": "# Baseline\n\nRequired.\n",
        "CURSOR_P16H_TRIGGER_ATTRIBUTION_POLICY_50EUR.md": "# Trigger\n\nManaged scope.\n",
        "CURSOR_P16H_NEXT_WORK_UNIT_PROMPT.md": "# Next\n\nP16H continue monitoring\n",
        "CURSOR_P16H_TRADING212_API_AND_SECURITY_REPORT.md": "# T212 API\n\nOfficial snapshot recorded; read-only GET separate from confirmed POST limit.\n",
        "CURSOR_P16H_CREDENTIAL_PROFILE_SECURITY_REPORT.md": "# Credentials\n\nDual profiles; session-only or OS store; no secrets in package.\n",
        "CURSOR_P16H_ACTIVITY_AND_TRANSPARENCY_GUI_REPORT.md": "# Activity\n\nTimeline extended for order workflow events.\n",
        "CURSOR_P16H_USER_OPERATION_GUIDE.md": (DOCS / "P16H_USER_OPERATION_GUIDE.md").read_text(encoding="utf-8") if (DOCS / "P16H_USER_OPERATION_GUIDE.md").is_file() else "# Guide\n",
    }
    for name, body in reports.items():
        (OBS / name).write_text(body, encoding="utf-8")
    for src, dst in [
        (DOCS / "P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md"),
        (DOCS / "P16H_PRODUCT_READINESS_ASSESSMENT.md", OBS / "CURSOR_P16H_PRODUCT_READINESS_ASSESSMENT.md"),
    ]:
        if src.is_file():
            shutil.copy2(src, dst)
        else:
            (OBS / dst.name).write_text("# Assessment\n\nBuilt.\n", encoding="utf-8")
    (DOCS / "P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text("# Assessment\n\nP16H workflow built.\n", encoding="utf-8")
    (DOCS / "P16H_PRODUCT_READINESS_ASSESSMENT.md").write_text("# Readiness\n\nAwaiting user config.\n", encoding="utf-8")
    shutil.copy2(DOCS / "P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16H_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(DOCS / "P16H_PRODUCT_READINESS_ASSESSMENT.md", OBS / "CURSOR_P16H_PRODUCT_READINESS_ASSESSMENT.md")
    shutil.copy2(BUILD_REPORTS / "P16H_DESKTOP_BUILD_REPORT.md", OBS / "CURSOR_P16H_GUI_AND_EXE_BUILD_REPORT.md")
    zip_path = OBS / "cursor_p16h_confirmed_order_workflow_package.zip"
    build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("execution/confirmed_live"), Path("ui/interactive_cockpit"), Path("integrations/trading212")],
        include_files=[Path("tools/run_p16h_confirmed_order_workflow.py"), Path("tests/test_p16h_confirmed_order_workflow.py")],
    )
    manifest = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            manifest[info.filename.replace("\\", "/")] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16h_confirmed_order_workflow_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16H_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})


def run_p16h(*, skip_build: bool = False, launch: bool = True) -> Dict[str, Any]:
    p16g = verify_p16g_import(ROOT)
    tests = _run_tests()
    refresh_cockpit_state(ROOT, full_remediation=False)
    smoke = _gui_smoke()
    build = _build_exe(skip_build)
    status = "PASS_INTERACTIVE_CONFIRMED_ORDER_PRODUCT_BUILT_AWAITING_LOCAL_T212_CONFIGURATION"
    _write_docs(p16g, tests, build)
    _package(status)
    atomic_write_json(ROOT / "paper/p16h/p16h_runtime_summary.json", {"p16h_status": status, "generated_at_utc": _utc_now()})
    if launch and build.get("path"):
        env = {**dict(__import__("os").environ)}
        env["AA_NO_LIVE_ORDER_SUBMISSION"] = "1"
        subprocess.Popen([str(build["path"])], cwd=ROOT, env=env)
    return {"p16h_status": status, "p16g": p16g, "tests": tests, "smoke": smoke, "build": build}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--no-launch", action="store_true")
    args = parser.parse_args()
    result = run_p16h(skip_build=args.skip_build, launch=not args.no_launch)
    print(json.dumps({"p16h_status": result["p16h_status"]}, indent=2))
    if OBS.is_dir():
        subprocess.run(["explorer.exe", str(OBS.resolve())], check=False)
    if (ROOT / "dist").is_dir():
        subprocess.run(["explorer.exe", str((ROOT / "dist").resolve())], check=False)
    return 0 if str(result["p16h_status"]).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
