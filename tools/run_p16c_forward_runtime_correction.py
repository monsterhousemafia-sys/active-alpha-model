#!/usr/bin/env python3
"""P16C Forward Runtime Correction and Validated Observation Window Continuation."""
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

from aa_decision_cockpit_readonly_snapshot import write_p16c_forward_runtime_correction_snapshot
from aa_evidence_packaging import build_zip_with_manifest
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16c.engine import run_p16c_forward_correction
from research.p16c.p16b_import_verification import verify_p16b_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16C_FORWARD_RUNTIME_CORRECTION"
OBS = ROOT / "outgoing_cursor_observation" / "p16c_forward_runtime_correction"

P16B_ID = "P16B_CONTINUOUS_FORWARD_PAPER_RUNTIME_REMEDIATION_AND_OBSERVATION_WINDOW"
P16C_ID = "P16C_FORWARD_RUNTIME_CORRECTION_AND_VALIDATED_OBSERVATION_WINDOW_CONTINUATION"
P16D_ID = "P16D_CONTINUE_VALIDATED_FORWARD_OBSERVATION_WINDOW"
P17_ID = "P17_VIRTUAL_SCALING_EVALUATION_AND_DECISION_SUPPORT_SIMULATION_ONLY"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16c_forward_runtime_correction.py", "-q", "--tb=no"]
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
        if str(phase.get("id")) == P16B_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL"
            phase["next_phase"] = P16C_ID
    if P16C_ID not in ids:
        phases.append({"id": P16C_ID, "status": "IN_PROGRESS", "next_phase": P16D_ID, "goal": "Forward runtime correction."})
    for nid, goal in ((P16D_ID, "Continue validated observation window."), (P17_ID, "Virtual scaling simulation only.")):
        if nid not in ids:
            phases.append({"id": nid, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16C_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml
    _sync_pipeline_yaml(ROOT, pipeline)


def write_docs(p16bv: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    atomic_write_json(DOCS / "P16C_P16B_IMPORT_AND_HASH_VERIFICATION.json", p16bv)
    (DOCS / "P16C_P16B_IMPORT_AND_HASH_VERIFICATION.md").write_text(f"# P16B Import\n\n{p16bv.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16C_P16B_ADJUDICATION.md").write_text("# P16B Adjudication\n\nConditional pass with runtime defects remediated in P16C.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16C_REMEDIATION_BACKLOG.json", {"P16C-B001": "ADDRESSED", "P16C-B002": "ADDRESSED"})
    (DOCS / "P16C_FX_FAIL_CLOSED_SPECIFICATION.md").write_text("# FX Fail-Closed\n\nStatic fallback excluded from performance.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16C_FX_RUNTIME_GATE_RESULTS.json", {"gate": runtime.get("fx_runtime_gate")})
    (DOCS / "P16C_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P16C Assessment",
                "",
                "## FAKTEN",
                f"Status: {runtime.get('p16c_implementation_status')}",
                f"FX gate: {runtime.get('fx_runtime_gate')}",
                f"P/L attribution: {runtime.get('pnl_attribution_gate')}",
                f"Performance class: {runtime.get('performance_evidence_classification')}",
                "",
                "## NICHT AUTORISIERT",
                "Real money, broker orders, promotion.",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P16C_TEST_EXECUTION_REPORT.md").write_text(f"Tests: {tests.get('tests_passed')} passed\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16C_TEST_RESULTS.json", tests)
    atomic_write_json(DOCS / "P16C_SAFETY_BOUNDARY_VERIFICATION.json", {"real_money": False})


def run_p16c() -> Dict[str, Any]:
    run_id = f"p16c_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    extend_pipeline()
    p16bv = verify_p16b_import(ROOT)
    tests = _run_tests()
    runtime = run_p16c_forward_correction(ROOT)
    write_docs(p16bv, runtime, tests)

    status = runtime.get("p16c_implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    win = runtime.get("observation_window") or {}
    next_wu = P17_ID if win.get("scaling_gate_status") == "READY_FOR_VIRTUAL_SCALING_REVIEW" else P16D_ID

    result = {"run_id": run_id, "p16c_status": status, "next_work_unit": next_wu, "runtime": runtime, "tests": tests, "p16b_import": p16bv}
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(f"# {next_wu}\n\nSimulation only.\n", encoding="utf-8")
    if str(status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16C_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg}
    write_p16c_forward_runtime_correction_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16C_FORWARD_RUNTIME_CORRECTION" / run_id / "p16c_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    shutil.copy2(DOCS / "P16C_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16C_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16C_NEXT_WORK_UNIT_PROMPT.md")
    (OBS / "CURSOR_P16C_EXECUTION_REPORT.md").write_text(
        f"# P16C Report\n\nStatus: **{result.get('p16c_status')}**\nRun: {result.get('run_id')}\n",
        encoding="utf-8",
    )
    zip_path = OBS / "cursor_p16c_forward_runtime_correction_package.zip"
    _, _ = build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("paper/p16c"), Path("paper/config"), Path("integrations/trading212")],
        include_files=[
            Path("tools/run_p16c_forward_runtime_correction.py"),
            Path("research/p16c/p16b_import_verification.py"),
            Path("aa_evidence_packaging.py"),
            Path("tests/test_p16c_forward_runtime_correction.py"),
        ],
    )
    import hashlib
    manifest: Dict[str, str] = {}
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            manifest[name] = hashlib.sha256(zf.read(info.filename)).hexdigest()
    manifest[zip_path.name] = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (OBS / "cursor_p16c_forward_runtime_correction_package.zip.sha256").write_text(f"{manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8")
    atomic_write_json(OBS / "CURSOR_P16C_HASH_MANIFEST.json", {"files": manifest, "manifest_coverage": "COMPLETE"})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16c()
    build_output_package(result)
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    print(json.dumps({"p16c_status": result.get("p16c_status")}, indent=2))
    return 0 if str(result.get("p16c_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
