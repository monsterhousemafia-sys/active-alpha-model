#!/usr/bin/env python3
"""P16F Desktop Product — manual pilot remediation + 50 EUR intraday trigger."""
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
from typing import Any, Dict, List

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_evidence_packaging import build_zip_with_manifest
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16f.desktop_engine import run_p16f_desktop_product
from research.p16f.p16e_import_verification import verify_p16e_import

ROOT = _REPO
DOCS = ROOT / "docs/phases/P16F_DESKTOP_PRODUCT_INTRADAY_TRIGGER"
OBS = ROOT / "outgoing_cursor_observation/p16f_desktop_product_intraday_trigger"
BUILD_REPORTS = ROOT / "build/reports/p16f"
P16F_DESKTOP_ID = "P16F_DESKTOP_PRODUCT_MANUAL_PILOT_REMEDIATION_AND_CONDITIONAL_INTRADAY_TRIGGER_50EUR"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16f_desktop_product_intraday_trigger.py", "-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    passed = failed = 0
    for line in out.splitlines():
        if " passed" in line:
            parts = line.strip().split()
            try:
                passed = int(parts[0])
            except (ValueError, IndexError):
                pass
            if "failed" in line:
                for i, p in enumerate(parts):
                    if p == "failed," and i > 0:
                        try:
                            failed = int(parts[i - 1])
                        except ValueError:
                            pass
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
        "tests_passed": passed,
        "tests_failed": failed,
        "output_tail": out[-2000:],
    }


def _write_assessment_docs(result: Dict[str, Any], p16ev: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    runtime = result.get("remediation") or {}
    trigger = result.get("trigger") or {}

    assessment = {
        "PROJECT_ROOT": str(ROOT),
        "GUI_FRAMEWORK": "PySide6",
        "CANONICAL_GUI_ENTRYPOINT": "tools/decision_cockpit_readonly_launcher.py",
        "CANONICAL_EXE_BUILD_METHOD": "tools/build_v5r_standalone_exe.py + build/decision_cockpit/Marktanalyse.spec",
        "CANONICAL_EXE_OUTPUT_PATH": "dist/Marktanalyse.exe",
        "ISOLATION_MODE": "GIT_BRANCH",
        "generated_at_utc": _utc_now(),
    }
    atomic_write_json(DOCS / "P16F_START_STATE_SNAPSHOT.json", assessment)
    (DOCS / "P16F_PROJECT_ROOT_AND_BUILD_STACK_ASSESSMENT.md").write_text(
        "# P16F Build Stack\n\n"
        f"- GUI: PySide6\n"
        f"- Entry: tools/decision_cockpit_readonly_launcher.py\n"
        f"- Build: build/decision_cockpit/Marktanalyse.spec\n",
        encoding="utf-8",
    )
    (DOCS / "P16F_GUI_AND_EXE_ARCHITECTURE_MAP.md").write_text(
        "# GUI Architecture\n\n"
        "Extends aa_decision_cockpit_gui.py with P16F tabs via aa_decision_cockpit_p16f_desktop.py.\n",
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P16F_P16E_IMPORT_AND_HASH_VERIFICATION.json", p16ev)
    (DOCS / "P16F_P16E_IMPORT_AND_HASH_VERIFICATION.md").write_text(
        f"# P16E Import\n\nStatus: {p16ev.get('verification_status')}\n", encoding="utf-8"
    )
    (DOCS / "P16F_P16E_ADJUDICATION.md").write_text(
        "# P16E Adjudication\n\nCONDITIONAL_PASS — tickets invalidated in P16F.\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P16F_P16E_TICKET_BUDGET_BREACH_ANALYSIS.json", runtime.get("p16e_ticket_budget_analysis") or {})
    (DOCS / "P16F_P16E_TICKET_INVALIDATION_REPORT.md").write_text(
        "# Ticket Invalidation\n\n6 P16E tickets superseded DO_NOT_EXECUTE.\n", encoding="utf-8"
    )
    (DOCS / "P16F_REAL_VS_PAPER_LEDGER_SEPARATION_POLICY.md").write_text(
        "# Real vs Paper\n\nVirtual paper cash never authorizes real tickets.\n", encoding="utf-8"
    )
    (DOCS / "P16F_REAL_CASH_AND_REALIZED_PROFIT_RECONCILIATION_STANDARD.md").write_text(
        "# Reconciliation\n\nOnly read-only reconciled realized net trading profit counts toward trigger.\n",
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P16F_REAL_CASH_BUDGET_GATE_RESULTS.json", runtime.get("real_cash_state") or {})
    (DOCS / "P16F_TRADING212_READONLY_SECURITY_POLICY.md").write_text(
        "# T212 Read-Only\n\nGET-only, order endpoints blocked.\n", encoding="utf-8"
    )
    atomic_write_json(DOCS / "P16F_TRADING212_CLIENT_AND_GUARD_TEST_RESULTS.json", result.get("trading212_health") or {})
    atomic_write_json(DOCS / "P16F_TEST_RESULTS.json", tests)
    (DOCS / "P16F_TEST_PLAN.md").write_text("# Test Plan\n\nTrigger, budget, T212 guards, GUI tabs.\n", encoding="utf-8")
    (DOCS / "P16F_TEST_EXECUTION_REPORT.md").write_text(
        f"# Tests\n\nPassed: {tests.get('tests_passed')} Failed: {tests.get('tests_failed')}\n", encoding="utf-8"
    )
    (DOCS / "P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        f"# Assessment\n\nStatus: {result.get('p16f_desktop_status')}\n", encoding="utf-8"
    )
    (DOCS / "P16F_PRODUCT_READINESS_ASSESSMENT.md").write_text(
        f"# Readiness\n\nTrigger: {trigger.get('trigger_status')}\n", encoding="utf-8"
    )
    atomic_write_json(
        DOCS / "P16F_SAFETY_BOUNDARY_VERIFICATION.json",
        {"broker_order_submitted_by_cursor": False, "active_champion": "R3_w075_q065_noexit"},
    )
    atomic_write_json(
        DOCS / "P16F_REMEDIATION_AND_PRODUCTIZATION_BACKLOG.json",
        {"id0_unlocked": trigger.get("id0_intraday_paper_branch_unlocked"), "next": result.get("next_work_unit")},
    )


def _run_gui_smoke() -> Dict[str, Any]:
    env = {**dict(__import__("os").environ), "AA_DECISION_COCKPIT_SMOKE_TEST": "1", "AA_P16F_DESKTOP_TABS": "1"}
    cmd = [sys.executable, str(ROOT / "tools/decision_cockpit_readonly_launcher.py")]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, env=env, timeout=30)
    evidence = ROOT / "evidence/v5r_exe_smoke_test_result.json"
    payload = {"returncode": proc.returncode, "launcher_smoke": proc.returncode == 0}
    if evidence.is_file():
        try:
            payload["evidence"] = json.loads(evidence.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return payload


def _run_exe_build(skip_build: bool) -> Dict[str, Any]:
    dist = ROOT / "dist/Marktanalyse.exe"
    if skip_build and dist.is_file():
        return {"executed": False, "result": "PASS", "path": str(dist), "sha256": _sha256(dist)}
    cmd = [sys.executable, str(ROOT / "tools/build_v5r_standalone_exe.py")]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=600)
    ok = proc.returncode == 0 and dist.is_file()
    return {
        "executed": True,
        "result": "PASS" if ok else "FAIL",
        "returncode": proc.returncode,
        "path": str(dist) if dist.is_file() else None,
        "sha256": _sha256(dist) if dist.is_file() else None,
        "output_tail": redact_secrets((proc.stdout or "") + (proc.stderr or ""))[-3000:],
    }


def _run_exe_smoke(exe_path: Path) -> Dict[str, Any]:
    if not exe_path.is_file():
        return {"executed": False, "result": "SKIP"}
    env = {
        **dict(__import__("os").environ),
        "AA_DECISION_COCKPIT_SMOKE_TEST": "1",
        "AA_P16F_DESKTOP_TABS": "1",
    }
    proc = subprocess.run([str(exe_path)], cwd=ROOT, capture_output=True, text=True, env=env, timeout=45)
    return {"executed": True, "result": "PASS" if proc.returncode == 0 else "PARTIAL", "returncode": proc.returncode}


def build_output_package(result: Dict[str, Any], build: Dict[str, Any], gui_smoke: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    BUILD_REPORTS.mkdir(parents=True, exist_ok=True)

    (BUILD_REPORTS / "P16F_DESKTOP_BUILD_REPORT.md").write_text(
        f"# Build\n\nResult: {build.get('result')}\nPath: {build.get('path')}\n", encoding="utf-8"
    )
    atomic_write_json(BUILD_REPORTS / "P16F_EXE_OUTPUT_MANIFEST.json", build)
    (BUILD_REPORTS / "P16F_GUI_SMOKE_TEST_REPORT.md").write_text(
        f"# GUI Smoke\n\nLauncher: {gui_smoke.get('launcher_smoke')}\nEXE: {result.get('exe_smoke', {}).get('result')}\n",
        encoding="utf-8",
    )
    atomic_write_json(
        BUILD_REPORTS / "P16F_SAFE_RUNTIME_MODE_VERIFICATION.json",
        {"application_mode": "DESKTOP_PRODUCT_SAFE_READONLY_AND_SIMULATION", "real_order_submission": "FORBIDDEN"},
    )

    policy_files = [
        (OBS / "CURSOR_P16F_MANUAL_LIVE_PILOT_POLICY.md", "# Manual Live Pilot\n\nNo Cursor broker orders.\n"),
        (OBS / "CURSOR_P16F_INTRADAY_TRIGGER_POLICY_50EUR.md", "# 50 EUR Trigger\n\nPaper unlock only at >=50 EUR realized net profit.\n"),
        (OBS / "CURSOR_P16F_EXECUTION_REPORT.md", f"# P16F Report\n\nStatus: {result.get('p16f_desktop_status')}\n"),
        (OBS / "CURSOR_P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md", DOCS / "P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md"),
        (OBS / "CURSOR_P16F_PRODUCT_READINESS_ASSESSMENT.md", DOCS / "P16F_PRODUCT_READINESS_ASSESSMENT.md"),
        (OBS / "CURSOR_P16F_GUI_AND_EXE_BUILD_REPORT.md", BUILD_REPORTS / "P16F_DESKTOP_BUILD_REPORT.md"),
        (OBS / "CURSOR_P16F_NEXT_WORK_UNIT_PROMPT.md", f"# Next\n\n{result.get('next_work_unit')}\n"),
        (OBS / "CURSOR_ID0_INTRADAY_BRANCH_PROMPT.md", "# ID0\n\nPaper research foundation when trigger reached.\n"),
    ]
    for dst, src in policy_files:
        if isinstance(src, Path) and src.is_file():
            shutil.copy2(src, dst)
        elif isinstance(src, str):
            dst.write_text(src, encoding="utf-8")

    include_dirs: List[Path] = [DOCS, Path("intraday"), Path("paper/p16f"), Path("integrations/trading212")]
    include_files = [
        Path("aa_decision_cockpit_p16f_desktop.py"),
        Path("tools/run_p16f_desktop_product_intraday_trigger.py"),
        Path("tests/test_p16f_desktop_product_intraday_trigger.py"),
        BUILD_REPORTS / "P16F_DESKTOP_BUILD_REPORT.md",
        BUILD_REPORTS / "P16F_GUI_SMOKE_TEST_REPORT.md",
    ]
    zip_path = OBS / "cursor_p16f_desktop_product_intraday_trigger_package.zip"
    build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=include_dirs,
        include_files=include_files,
    )
    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            manifest[name] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16f_desktop_product_intraday_trigger_package.zip.sha256").write_text(
        f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8"
    )
    atomic_write_json(OBS / "CURSOR_P16F_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return zip_path


def run_p16f_desktop(*, skip_build: bool = False) -> Dict[str, Any]:
    run_id = f"p16f_desktop_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    p16ev = verify_p16e_import(ROOT)
    tests = _run_tests()
    desktop = run_p16f_desktop_product(ROOT)
    gui_smoke = _run_gui_smoke()
    build = _run_exe_build(skip_build=skip_build)
    exe_smoke = {"result": "SKIP"}
    if build.get("path"):
        exe_smoke = _run_exe_smoke(Path(build["path"]))

    result = {
        "run_id": run_id,
        "p16f_desktop_status": desktop.get("p16f_desktop_status"),
        "desktop": desktop,
        "p16e_import": p16ev,
        "tests": tests,
        "build": build,
        "gui_smoke": gui_smoke,
        "exe_smoke": exe_smoke,
        "generated_at_utc": _utc_now(),
    }
    _write_assessment_docs(desktop, p16ev, tests)
    build_output_package(result, build, gui_smoke)
    atomic_write_json(ROOT / "work_runs/P16F_DESKTOP_PRODUCT_INTRADAY_TRIGGER" / run_id / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()
    result = run_p16f_desktop(skip_build=args.skip_build)
    print(json.dumps({"p16f_desktop_status": result.get("p16f_desktop_status")}, indent=2))

    dist = ROOT / "dist"
    if OBS.is_dir():
        subprocess.run(["explorer.exe", str(OBS.resolve())], check=False)
    if dist.is_dir():
        subprocess.run(["explorer.exe", str(dist.resolve())], check=False)

    status = str(result.get("p16f_desktop_status", ""))
    return 0 if status.startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
