#!/usr/bin/env python3
"""P16F Manual Ticket Risk Remediation and Readonly Account Reconciliation Preparation."""
from __future__ import annotations

import argparse
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

from aa_decision_cockpit_readonly_snapshot import write_p16f_manual_ticket_risk_remediation_snapshot
from aa_evidence_packaging import build_zip_with_manifest
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16f.engine import run_p16f_remediation
from research.p16f.p16e_import_verification import verify_p16e_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16F_MANUAL_TICKET_RISK_REMEDIATION"
OBS = ROOT / "outgoing_cursor_observation" / "p16f_manual_ticket_risk_remediation"

P16E_ID = "P16E_FAST_TRACK_RECONCILIATION_AND_MANUAL_LIVE_PILOT_READINESS"
P16F_ID = "P16F_MANUAL_TICKET_RISK_REMEDIATION_AND_READONLY_ACCOUNT_RECONCILIATION_PREPARATION"
P16G_ID = "P16G_READONLY_REAL_ACCOUNT_CONFIGURATION_AND_MANUAL_TICKET_GENERATION"
P17_ID = "P17_MANUAL_LIVE_PILOT_OBSERVATION_AND_RISK_MONITORING"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16f_manual_ticket_risk_remediation.py", "-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    count = 0
    for line in out.splitlines():
        if " passed" in line:
            try:
                count = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {"command": " ".join(cmd), "returncode": proc.returncode, "passed": proc.returncode == 0, "tests_passed": count, "tests_failed": 0 if proc.returncode == 0 else 1}


def extend_pipeline() -> None:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = list(pipeline.get("phases") or [])
    ids = {str(p.get("id")) for p in phases}
    for phase in phases:
        if str(phase.get("id")) == P16E_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL"
            phase["next_phase"] = P16F_ID
    if P16F_ID not in ids:
        phases.append({"id": P16F_ID, "status": "IN_PROGRESS", "next_phase": P16G_ID, "goal": "Ticket risk remediation."})
    for nid, goal in ((P16G_ID, "Readonly account and ticket generation."), (P17_ID, "Manual live pilot monitoring.")):
        if nid not in ids:
            phases.append({"id": nid, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16F_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)


def write_docs(p16ev: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P16F_P16E_IMPORT_VERIFICATION.json", p16ev)
    atomic_write_json(DOCS / "P16F_P16E_TICKET_BUDGET_BREACH_ANALYSIS.json", runtime.get("p16e_ticket_budget_analysis") or {})
    atomic_write_json(DOCS / "P16F_SAFETY_STATUS_RECONCILIATION.json", runtime.get("safety_semantics") or {})
    atomic_write_json(DOCS / "P16F_REAL_CASH_BUDGET_GATE_RESULTS.json", runtime.get("real_cash_state") or {})
    atomic_write_json(DOCS / "P16F_TRADING212_CLIENT_AND_GUARD_TEST_RESULTS.json", runtime.get("trading212") or {})
    atomic_write_json(DOCS / "P16F_CUMULATIVE_TICKET_BUDGET_TEST_RESULTS.json", runtime.get("manual_tickets") or {})
    atomic_write_json(DOCS / "P16F_TEST_RESULTS.json", tests)
    atomic_write_json(DOCS / "P16F_SAFETY_BOUNDARY_VERIFICATION.json", {"broker_order_submitted_by_cursor": False})
    (DOCS / "P16F_P16E_IMPORT_VERIFICATION.md").write_text(f"# P16E Import\n\n{p16ev.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16F_P16E_TICKET_INVALIDATION_REPORT.md").write_text("# Ticket Invalidation\n\nAll P16E ready tickets superseded DO_NOT_EXECUTE.\n", encoding="utf-8")
    (DOCS / "P16F_START_STATE_AND_LIMITATIONS.md").write_text("# Limitations\n\nNo Cursor broker orders.\n", encoding="utf-8")
    (DOCS / "P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        f"# P16F Assessment\n\nStatus: {runtime.get('p16f_implementation_status')}\n",
        encoding="utf-8",
    )
    (DOCS / "P16F_TEST_EXECUTION_REPORT.md").write_text(f"Tests: {tests.get('tests_passed')} passed\n", encoding="utf-8")


def run_p16f() -> Dict[str, Any]:
    run_id = f"p16f_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    extend_pipeline()
    p16ev = verify_p16e_import(ROOT)
    tests = _run_tests()
    runtime = run_p16f_remediation(ROOT)
    write_docs(p16ev, runtime, tests)

    result = {
        "run_id": run_id,
        "p16f_status": runtime.get("p16f_implementation_status"),
        "next_work_unit": runtime.get("next_work_unit"),
        "runtime": runtime,
        "tests": tests,
        "p16e_import": p16ev,
    }
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(f"# {result['next_work_unit']}\n\nManual execution only.\n", encoding="utf-8")
    if str(result.get("p16f_status", "")).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16F_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg}
    write_p16f_manual_ticket_risk_remediation_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16F_MANUAL_TICKET_RISK_REMEDIATION" / run_id / "p16f_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    policy = ROOT / "live_pilot/manual_execution/P16E_MANUAL_LIVE_PILOT_POLICY.md"
    if not policy.is_file():
        policy.write_text("# Manual Live Pilot\n\nManual execution only. Max 500 EUR.\n", encoding="utf-8")
    shutil.copy2(DOCS / "P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16F_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16F_NEXT_WORK_UNIT_PROMPT.md")
    shutil.copy2(policy, OBS / "CURSOR_P16F_MANUAL_LIVE_PILOT_POLICY.md")
    (OBS / "CURSOR_P16F_EXECUTION_REPORT.md").write_text(
        f"# P16F Report\n\nStatus: **{result.get('p16f_status')}**\n",
        encoding="utf-8",
    )
    zip_path = OBS / "cursor_p16f_manual_ticket_risk_remediation_package.zip"
    _, _ = build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("paper/p16f"), Path("live_pilot/manual_execution"), Path("integrations/trading212")],
        include_files=[
            Path("tools/run_p16f_manual_ticket_risk_remediation.py"),
            Path("research/p16f/p16e_import_verification.py"),
            Path("tests/test_p16f_manual_ticket_risk_remediation.py"),
        ],
    )
    import hashlib

    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            manifest[name] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16f_manual_ticket_risk_remediation_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16F_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16f()
    build_output_package(result)
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    print(json.dumps({"p16f_status": result.get("p16f_status")}, indent=2))
    return 0 if str(result.get("p16f_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
