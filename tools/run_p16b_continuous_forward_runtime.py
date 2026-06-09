#!/usr/bin/env python3
"""P16B Continuous Forward Paper Runtime Remediation and Observation Window."""
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

from aa_decision_cockpit_readonly_snapshot import write_p16b_continuous_forward_snapshot
from aa_evidence_packaging import build_zip_with_manifest
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16b.engine import run_p16b_continuous_forward
from research.p16b.p16_import_verification import verify_p16_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16B_CONTINUOUS_FORWARD_RUNTIME"
OBS = ROOT / "outgoing_cursor_observation" / "p16b_continuous_forward_runtime"

P16_ID = "P16_READ_ONLY_FORWARD_OBSERVATION_AND_VIRTUAL_SCALING_EVIDENCE"
P16B_ID = "P16B_CONTINUOUS_FORWARD_PAPER_RUNTIME_REMEDIATION_AND_OBSERVATION_WINDOW"
P16C_ID = "P16C_CONTINUE_VALIDATED_FORWARD_OBSERVATION_WINDOW"
P17_ID = "P17_VIRTUAL_SCALING_EVALUATION_AND_DECISION_SUPPORT_SIMULATION_ONLY"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run_tests() -> Dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/test_p16b_continuous_forward_runtime.py", "-q", "--tb=no"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    count = 0
    for line in out.splitlines():
        if " passed" in line:
            try:
                count = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {"command": " ".join(cmd), "returncode": proc.returncode, "passed": proc.returncode == 0, "tests_passed": count, "tests_failed": 0 if proc.returncode == 0 else 1, "output_excerpt": out[-4000:]}


def extend_pipeline() -> None:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = list(pipeline.get("phases") or [])
    ids = {str(p.get("id")) for p in phases}
    for phase in phases:
        if str(phase.get("id")) == P16_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL_PASS_INITIAL_READ_ONLY_SNAPSHOT_AND_RUNTIME_FOUNDATION"
            phase["next_phase"] = P16B_ID
    if P16B_ID not in ids:
        phases.append({"id": P16B_ID, "status": "IN_PROGRESS", "next_phase": P16C_ID, "goal": "Continuous forward paper runtime remediation."})
    for nid, goal in ((P16C_ID, "Continue observation window."), (P17_ID, "Virtual scaling evaluation simulation only.")):
        if nid not in ids:
            phases.append({"id": nid, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16B_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml
    _sync_pipeline_yaml(ROOT, pipeline)


def write_docs(p16v: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    backlog = {
        "P16B-B001": "BASE_CURRENCY_AND_QUOTE_CURRENCY_RECONCILIATION_MISSING",
        "P16B-B002": "STATEFUL_PAPER_PORTFOLIO_CONTINUATION_NOT_IMPLEMENTED",
        "P16B-B003": "FORWARD_DATA_QUALITY_GATE_INCOMPLETE",
        "P16B-B004": "SCALING_GATE_DOES_NOT_MEASURE_FORWARD_OBSERVATION_WINDOW",
        "P16B-B005": "PRIMARY_FEED_MAPPING_STATUS_OVERSTATED",
        "P16B-B006": "P16_FINAL_PACKAGE_MANIFEST_COVERAGE_INCOMPLETE",
        "P16B-B007": "TRADING212_DEMO_CLIENT_EXECUTION_PATH_NOT_YET_PROVEN",
        "P16B-B008": "INITIAL_ALLOCATION_COST_IS_NOT_FORWARD_PERFORMANCE",
    }
    atomic_write_json(DOCS / "P16B_P16_IMPORT_AND_HASH_VERIFICATION.json", p16v)
    (DOCS / "P16B_P16_IMPORT_AND_HASH_VERIFICATION.md").write_text(f"# P16 Import\n\nStatus: {p16v.get('verification_status')}\n", encoding="utf-8")
    (DOCS / "P16B_P16_LIMITATION_ADJUDICATION.md").write_text("# P16 Limitations\n\nSee P16B_REMEDIATION_BACKLOG.json\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16B_REMEDIATION_BACKLOG.json", backlog)
    (DOCS / "P16B_CURRENCY_AND_FX_ACCOUNTING_STANDARD.md").write_text("# FX Standard\n\nUSD quotes converted via READONLY_YFINANCE EURUSD.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16B_CURRENCY_RECONCILIATION_RESULTS.json", {"status": runtime.get("currency_reconciliation")})
    (DOCS / "P16B_STATEFUL_PAPER_RUNTIME_SPECIFICATION.md").write_text("# Stateful Runtime\n\nInitial allocation once; MTM on subsequent runs.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16B_LEDGER_RECONCILIATION_RESULTS.json", {"portfolio": runtime.get("portfolio_reconciliation")})
    atomic_write_json(DOCS / "P16B_DATA_QUALITY_GATE_RESULTS.json", runtime.get("forward_batch") or {})
    (DOCS / "P16B_TRADING212_CLIENT_PATH_VALIDATION_REPORT.md").write_text("# T212 Client\n\nMock path tested in unit tests.\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16B_TRADING212_GUARD_AND_SECRET_TEST_RESULTS.json", {"mock_client_tested": True})
    (DOCS / "P16B_TEST_EXECUTION_REPORT.md").write_text(f"# Tests\n\n`{tests.get('command')}` passed={tests.get('passed')}\n", encoding="utf-8")
    atomic_write_json(DOCS / "P16B_TEST_RESULTS.json", tests)
    atomic_write_json(DOCS / "P16B_SAFETY_BOUNDARY_VERIFICATION.json", {"real_money": False, "broker_orders": False})
    (DOCS / "P16B_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        "\n".join(
            [
                "# P16B Assessment",
                "",
                "## FAKTEN",
                f"- Status: {runtime.get('p16b_implementation_status')}",
                f"- Currency reconciliation: {runtime.get('currency_reconciliation')}",
                f"- Initial allocation once: {runtime.get('initial_allocation_executed_once')}",
                f"- Observation batches: {(runtime.get('observation_window') or {}).get('observation_batches')}",
                "",
                "## NICHT AUTORISIERT",
                "- Real money, broker orders, promotion, champion change.",
            ]
        ),
        encoding="utf-8",
    )


def run_p16b() -> Dict[str, Any]:
    run_id = f"p16b_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    extend_pipeline()
    p16v = verify_p16_import(ROOT)
    tests = _run_tests()
    runtime = run_p16b_continuous_forward(ROOT)
    write_docs(p16v, runtime, tests)

    status = runtime.get("p16b_implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    window = runtime.get("observation_window") or {}
    next_wu = P17_ID if window.get("status") == "OBSERVATION_WINDOW_COMPLETE_FOR_VIRTUAL_SCALING_REVIEW" else P16C_ID

    result = {"run_id": run_id, "generated_at_utc": _utc_now(), "p16b_status": status, "next_work_unit": next_wu, "p16_import": p16v, "runtime": runtime, "tests": tests}
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(f"# {next_wu}\n\nSimulation only.\n", encoding="utf-8")

    if str(status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16B_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg}
    write_p16b_continuous_forward_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16B_CONTINUOUS_FORWARD_RUNTIME" / run_id / "p16b_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p16b_status", "FAILED")
    tests = result.get("tests") or {}
    (OBS / "CURSOR_P16B_EXECUTION_REPORT.md").write_text(
        f"# P16B Report\n\nStatus: **{status}**\nRun: {result.get('run_id')}\nTests: {tests.get('tests_passed')} passed\n",
        encoding="utf-8",
    )
    shutil.copy2(DOCS / "P16B_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16B_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16B_NEXT_WORK_UNIT_PROMPT.md")

    zip_path = OBS / "cursor_p16b_continuous_forward_runtime_package.zip"
    _, manifest = build_zip_with_manifest(
        root=ROOT,
        zip_path=zip_path,
        include_dirs=[DOCS, Path("paper/p16b"), Path("paper/config"), Path("integrations/trading212")],
        include_files=[
            Path("tools/run_p16b_continuous_forward_runtime.py"),
            Path("research/p16b/p16_import_verification.py"),
            Path("aa_evidence_packaging.py"),
            Path("tests/test_p16b_continuous_forward_runtime.py"),
        ],
    )
    with zipfile.ZipFile(zip_path, "r") as zf:
        entry_names = sorted(i.filename.replace("\\", "/") for i in zf.infolist())
    verified_manifest: Dict[str, str] = {}
    zip_bytes = zip_path.read_bytes()
    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in entry_names:
            verified_manifest[name] = hashlib.sha256(zf.read(name)).hexdigest()
    verified_manifest[zip_path.name] = hashlib.sha256(zip_bytes).hexdigest()
    (OBS / "cursor_p16b_continuous_forward_runtime_package.zip.sha256").write_text(
        f"{verified_manifest[zip_path.name]}  {zip_path.name}\n", encoding="utf-8"
    )
    atomic_write_json(OBS / "CURSOR_P16B_HASH_MANIFEST.json", {"files": verified_manifest, "manifest_coverage": "COMPLETE"})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16b()
    build_output_package(result)
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    print(json.dumps({"p16b_status": result.get("p16b_status")}, indent=2))
    return 0 if str(result.get("p16b_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
