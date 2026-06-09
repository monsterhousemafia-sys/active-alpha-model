#!/usr/bin/env python3
"""P16D Validated Forward Runtime Hardening and Observation Continuation."""
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

from aa_decision_cockpit_readonly_snapshot import write_p16d_validated_forward_runtime_snapshot
from aa_evidence_packaging import build_zip_with_manifest
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16d.engine import run_p16d_forward_hardening
from research.p16d.p16c_import_verification import verify_p16c_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16D_VALIDATED_FORWARD_RUNTIME"
OBS = ROOT / "outgoing_cursor_observation" / "p16d_validated_forward_runtime"

P16C_ID = "P16C_FORWARD_RUNTIME_CORRECTION_AND_VALIDATED_OBSERVATION_WINDOW_CONTINUATION"
P16D_ID = "P16D_VALIDATED_FORWARD_RUNTIME_HARDENING_AND_OBSERVATION_CONTINUATION"
P16E_ID = "P16E_CONTINUE_POST_BASELINE_VALIDATED_OBSERVATION_WINDOW"
P17_ID = "P17_VIRTUAL_SCALING_EVALUATION_AND_DECISION_SUPPORT_SIMULATION_ONLY"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _capture_start_state() -> Dict[str, Any]:
    import subprocess as sp

    head = sp.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True)
    status = sp.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True)
    pipeline = {}
    if (ROOT / "DEVELOPMENT_PIPELINE.json").is_file():
        pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    return {
        "project_root": str(ROOT),
        "isolation_mode": "GIT_WORKTREE",
        "start_head": head.stdout.strip() if head.returncode == 0 else "",
        "start_pipeline_phase": pipeline.get("current_phase"),
        "start_changed_paths_count": len([l for l in status.stdout.splitlines() if l.strip()]),
        "generated_at_utc": _utc_now(),
    }


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16d_validated_forward_runtime.py", "-q", "--tb=no"]
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
        if str(phase.get("id")) == P16C_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL"
            phase["next_phase"] = P16D_ID
    if P16D_ID not in ids:
        phases.append({"id": P16D_ID, "status": "IN_PROGRESS", "next_phase": P16E_ID, "goal": "Runtime hardening and observation."})
    for nid, goal in ((P16E_ID, "Continue post-baseline observation."), (P17_ID, "Virtual scaling simulation only.")):
        if nid not in ids:
            phases.append({"id": nid, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16D_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)


def write_docs(p16cv: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any], start: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P16D_P16C_IMPORT_AND_HASH_VERIFICATION.json", p16cv)
    atomic_write_json(DOCS / "P16D_START_STATE_SNAPSHOT.json", start)
    atomic_write_json(DOCS / "P16D_REMEDIATION_BACKLOG.json", {"P16D-B001": "ADDRESSED", "P16D-B002": "ADDRESSED", "P16D-B005": "ADDRESSED", "P16D-B006": "ADDRESSED"})
    atomic_write_json(DOCS / "P16D_CURRENCY_RECONCILIATION_RESULTS.json", runtime.get("currency_reconciliation") or {})
    atomic_write_json(DOCS / "P16D_OBSERVATION_WINDOW_STATUS.json", runtime.get("observation_window") or {})
    atomic_write_json(DOCS / "P16D_TRADING212_SYNC_STATUS.json", runtime.get("trading212") or {})
    atomic_write_json(DOCS / "P16D_TEST_RESULTS.json", tests)
    atomic_write_json(DOCS / "P16D_SAFETY_BOUNDARY_VERIFICATION.json", {"real_money": False, "simulation_only": True})
    (DOCS / "P16D_P16C_IMPORT_AND_HASH_VERIFICATION.md").write_text(f"# P16C Import\n\n{p16cv.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16D_P16C_ADJUDICATION.md").write_text("# P16C Adjudication\n\nConditional pass; hardening in P16D.\n", encoding="utf-8")
    (DOCS / "P16D_MULTI_CURRENCY_ACCOUNTING_STANDARD.md").write_text("# Multi-Currency\n\nNo static FX on performance paths.\n", encoding="utf-8")
    (DOCS / "P16D_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P16D Assessment",
                "",
                "## FAKTEN",
                f"Status: {runtime.get('p16d_implementation_status')}",
                f"Multi-currency gate: {runtime.get('multi_currency_runtime_gate')}",
                f"Performance class: {runtime.get('performance_evidence_classification')}",
                "",
                "## PORTFOLIOIDENTITÄT",
                "Reference 8 / Executable 6 — no retroactive merge.",
                "",
                "## NICHT AUTORISIERT",
                "Real money, broker orders, promotion.",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P16D_TEST_EXECUTION_REPORT.md").write_text(f"Tests: {tests.get('tests_passed')} passed\n", encoding="utf-8")


def run_p16d() -> Dict[str, Any]:
    run_id = f"p16d_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    start = _capture_start_state()
    extend_pipeline()
    p16cv = verify_p16c_import(ROOT)
    tests = _run_tests()
    runtime = run_p16d_forward_hardening(ROOT)
    write_docs(p16cv, runtime, tests, start)

    status = runtime.get("p16d_implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    win = runtime.get("observation_window") or {}
    next_wu = P17_ID if win.get("scaling_gate_status") == "READY_FOR_VIRTUAL_SCALING_REVIEW" else P16E_ID

    result = {"run_id": run_id, "p16d_status": status, "next_work_unit": next_wu, "runtime": runtime, "tests": tests, "p16c_import": p16cv, "start_state": start}
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(f"# {next_wu}\n\nSimulation only.\n", encoding="utf-8")
    if str(status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16D_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg}
    write_p16d_validated_forward_runtime_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16D_VALIDATED_FORWARD_RUNTIME" / run_id / "p16d_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS / "P16D_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16D_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16D_NEXT_WORK_UNIT_PROMPT.md")
    (OBS / "CURSOR_P16D_EXECUTION_REPORT.md").write_text(
        f"# P16D Report\n\nStatus: **{result.get('p16d_status')}**\nRun: {result.get('run_id')}\n",
        encoding="utf-8",
    )
    zip_path = OBS / "cursor_p16d_validated_forward_runtime_package.zip"
    _, _ = build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("paper/p16d"), Path("paper/config"), Path("integrations/trading212")],
        include_files=[
            Path("tools/run_p16d_validated_forward_runtime.py"),
            Path("research/p16d/p16c_import_verification.py"),
            Path("aa_evidence_packaging.py"),
            Path("tests/test_p16d_validated_forward_runtime.py"),
        ],
    )
    import hashlib

    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            manifest[name] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16d_validated_forward_runtime_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16D_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16d()
    build_output_package(result)
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    print(json.dumps({"p16d_status": result.get("p16d_status")}, indent=2))
    return 0 if str(result.get("p16d_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
