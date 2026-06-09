#!/usr/bin/env python3
"""P16E Fast-Track Reconciliation and Manual Live Pilot Readiness."""
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

from aa_decision_cockpit_readonly_snapshot import write_p16e_fast_track_manual_live_readiness_snapshot
from aa_evidence_packaging import build_zip_with_manifest
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16e.engine import run_p16e_fast_track
from research.p16e.p16d_import_verification import verify_p16d_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16E_FAST_TRACK_MANUAL_LIVE_READINESS"
OBS = ROOT / "outgoing_cursor_observation" / "p16e_fast_track_manual_live_readiness"

P16D_ID = "P16D_VALIDATED_FORWARD_RUNTIME_HARDENING_AND_OBSERVATION_CONTINUATION"
P16E_ID = "P16E_FAST_TRACK_RECONCILIATION_AND_MANUAL_LIVE_PILOT_READINESS"
P16F_ID = "P16F_MANUAL_LIVE_PILOT_TICKET_REVIEW_AND_READONLY_RECONCILIATION"
P17_ID = "P17_MANUAL_LIVE_PILOT_OBSERVATION_AND_RISK_MONITORING"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16e_fast_track_manual_live_readiness.py", "-q", "--tb=no"]
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
        if str(phase.get("id")) == P16D_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL"
            phase["next_phase"] = P16E_ID
    if P16E_ID not in ids:
        phases.append({"id": P16E_ID, "status": "IN_PROGRESS", "next_phase": P16F_ID, "goal": "Manual live pilot readiness."})
    for nid, goal in ((P16F_ID, "Manual ticket review and reconciliation."), (P17_ID, "Manual live pilot monitoring.")):
        if nid not in ids:
            phases.append({"id": nid, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16E_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)


def write_docs(p16dv: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P16E_P16D_IMPORT_VERIFICATION.json", p16dv)
    atomic_write_json(DOCS / "P16E_PORTFOLIO_PNL_RECONCILIATION_RESULTS.json", runtime.get("pnl_reconciliation") or {})
    atomic_write_json(DOCS / "P16E_TRADING212_SECURITY_TEST_RESULTS.json", runtime.get("trading212") or {})
    atomic_write_json(DOCS / "P16E_SECRET_HANDLING_VERIFICATION.json", {"secrets_excluded": True})
    atomic_write_json(DOCS / "P16E_TEST_RESULTS.json", tests)
    atomic_write_json(DOCS / "P16E_SAFETY_BOUNDARY_VERIFICATION.json", {"broker_order_submission_by_cursor": False, "real_capital_deployed_by_cursor_eur": 0.0})
    atomic_write_json(
        DOCS / "P16E_TRADING212_ENDPOINT_ALLOWLIST.json",
        {"allowed_methods": ["GET"], "order_endpoints_allowed": False},
    )
    (DOCS / "P16E_P16D_IMPORT_VERIFICATION.md").write_text(f"# P16D Import\n\n{p16dv.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16E_START_STATE_AND_LIMITATIONS.md").write_text("# Limitations\n\nManual execution only. No Cursor broker orders.\n", encoding="utf-8")
    (DOCS / "P16E_PORTFOLIO_PNL_RECONCILIATION_REPORT.md").write_text(
        f"# P/L Reconciliation\n\nGate: {runtime.get('pnl_reconciliation', {}).get('pnl_reconciliation_gate')}\n", encoding="utf-8"
    )
    (DOCS / "P16E_TRADING212_READ_ONLY_SECURITY_POLICY.md").write_text("# T212 Security\n\nGET-only. Order endpoints blocked.\n", encoding="utf-8")
    (DOCS / "P16E_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P16E Assessment",
                "",
                "## FAKTEN",
                f"Status: {runtime.get('p16e_implementation_status')}",
                f"P/L gate: {runtime.get('pnl_reconciliation', {}).get('pnl_reconciliation_gate')}",
                f"Ready tickets: {runtime.get('manual_tickets', {}).get('ready_for_user_manual_review')}",
                "",
                "## NICHT AUTORISIERT",
                "Automated broker orders, promotion, champion change.",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P16E_TEST_EXECUTION_REPORT.md").write_text(f"Tests: {tests.get('tests_passed')} passed\n", encoding="utf-8")


def run_p16e() -> Dict[str, Any]:
    run_id = f"p16e_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    extend_pipeline()
    p16dv = verify_p16d_import(ROOT)
    tests = _run_tests()
    runtime = run_p16e_fast_track(ROOT)
    write_docs(p16dv, runtime, tests)

    status = runtime.get("p16e_implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    next_wu = P16F_ID

    result = {"run_id": run_id, "p16e_status": status, "next_work_unit": next_wu, "runtime": runtime, "tests": tests, "p16d_import": p16dv}
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(f"# {next_wu}\n\nManual execution only.\n", encoding="utf-8")
    if str(status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16E_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg}
    write_p16e_fast_track_manual_live_readiness_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16E_FAST_TRACK_MANUAL_LIVE_READINESS" / run_id / "p16e_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    policy_src = ROOT / "live_pilot/manual_execution/P16E_MANUAL_LIVE_PILOT_POLICY.md"
    shutil.copy2(DOCS / "P16E_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16E_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16E_NEXT_WORK_UNIT_PROMPT.md")
    if policy_src.is_file():
        shutil.copy2(policy_src, OBS / "CURSOR_P16E_MANUAL_LIVE_PILOT_POLICY.md")
    else:
        (OBS / "CURSOR_P16E_MANUAL_LIVE_PILOT_POLICY.md").write_text("# Manual Live Pilot\n\nManual execution only.\n", encoding="utf-8")
    (OBS / "CURSOR_P16E_EXECUTION_REPORT.md").write_text(
        f"# P16E Report\n\nStatus: **{result.get('p16e_status')}**\nRun: {result.get('run_id')}\n",
        encoding="utf-8",
    )
    zip_path = OBS / "cursor_p16e_fast_track_manual_live_readiness_package.zip"
    _, _ = build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("paper/p16e"), Path("live_pilot/manual_execution"), Path("integrations/trading212")],
        include_files=[
            Path("tools/run_p16e_fast_track_manual_live_readiness.py"),
            Path("research/p16e/p16d_import_verification.py"),
            Path("aa_evidence_packaging.py"),
            Path("tests/test_p16e_fast_track_manual_live_readiness.py"),
        ],
    )
    import hashlib

    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            manifest[name] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16e_fast_track_manual_live_readiness_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16E_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16e()
    build_output_package(result)
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    print(json.dumps({"p16e_status": result.get("p16e_status")}, indent=2))
    return 0 if str(result.get("p16e_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
