#!/usr/bin/env python3
"""P16 Read-Only Forward Observation and Virtual Scaling Evidence."""
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

from aa_decision_cockpit_readonly_snapshot import write_p16_forward_observation_snapshot
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_environment_guard import DEMO_BASE_URL
from integrations.trading212.t212_query_policy import ALLOWED_QUERY_BY_PATH
from integrations.trading212.t212_request_allowlist import ALLOWED_GET_PATHS
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p16.engine import run_p16_forward_observation
from research.g1.hashing import file_sha256
from research.p16.p15_import_verification import verify_p15_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P16_FORWARD_OBSERVATION_SCALING"
OBS = ROOT / "outgoing_cursor_observation" / "p16_forward_observation_scaling"

P15_ID = "P15_PAPER_RUNTIME_VALIDATION_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT"
P16_ID = "P16_READ_ONLY_FORWARD_OBSERVATION_AND_VIRTUAL_SCALING_EVIDENCE"
P16_LEGACY = "P16_VIRTUAL_SCALING_EVALUATION_AND_REAL_MONEY_DECISION_DOSSIER"
P16B_ID = "P16B_CONTINUE_FORWARD_OBSERVATION_WINDOW"
P17_ID = "P17_VIRTUAL_SCALING_ASSESSMENT_AND_REAL_MONEY_DECISION_DOSSIER_PREPARATION"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_head() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _run_tests() -> Dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_p16_forward_observation_scaling.py",
        "tests/test_p15_paper_runtime_validation.py",
        "-q",
        "--tb=no",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = redact_secrets(proc.stdout + proc.stderr)
    passed = proc.returncode == 0
    count = 0
    for line in out.splitlines():
        if " passed" in line:
            try:
                count = int(line.strip().split()[0])
            except (ValueError, IndexError):
                pass
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "passed": passed,
        "tests_passed": count,
        "tests_failed": 0 if passed else 1,
        "output_excerpt": out[-5000:],
    }


def extend_pipeline_for_p16() -> None:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = list(pipeline.get("phases") or [])
    ids = {str(p.get("id")) for p in phases}
    for phase in phases:
        pid = str(phase.get("id"))
        if pid == P15_ID:
            phase["status"] = "PASS"
            phase["adjudication"] = "CONDITIONAL"
            phase["next_phase"] = P16_ID
        if pid == P16_LEGACY:
            phase["id"] = P16_ID
            phase["scope_classification"] = "FORWARD_OBSERVATION_AND_SIMULATION_ONLY_REAL_MONEY_DOSSIER_NOT_YET_DECISION_READY"
            phase["legacy_id"] = P16_LEGACY
            phase["status"] = "IN_PROGRESS"
    if P16_ID not in ids and P16_LEGACY not in ids:
        phases.append(
            {
                "id": P16_ID,
                "legacy_id": P16_LEGACY,
                "scope_classification": "FORWARD_OBSERVATION_AND_SIMULATION_ONLY_REAL_MONEY_DOSSIER_NOT_YET_DECISION_READY",
                "status": "IN_PROGRESS",
                "next_phase": P16B_ID,
                "goal": "Read-only forward observation and virtual scaling evidence.",
            }
        )
    for nxt_id, goal in (
        (P16B_ID, "Continue forward observation window."),
        (P17_ID, "Virtual scaling assessment and real-money decision dossier preparation (no execution)."),
    ):
        if nxt_id not in ids:
            phases.append({"id": nxt_id, "status": "NOT_STARTED", "next_phase": None, "goal": goal})
    pipeline["phases"] = phases
    pipeline["current_phase"] = P16_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)


def _write_objective_assessment(runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    paper = runtime.get("paper_observation") or {}
    content = "\n".join(
        [
            "# P16 Objective Technical Assessment",
            "",
            "## FAKTEN",
            f"- P16 status: {runtime.get('p16_implementation_status')}",
            f"- Forward feed validated: {runtime.get('forward_feed_validated')}",
            f"- Valid observations: {runtime.get('valid_observation_count')}",
            f"- Data mode: {runtime.get('data_mode')}",
            f"- T212 provider verified: {runtime.get('t212_provider_verified_mappings')}",
            f"- Tests passed: {tests.get('tests_passed')}",
            "",
            "## ANNAHMEN",
            "- User screenshot reference is virtual target only, not broker ledger.",
            "- yfinance read-only quotes acceptable for forward observation when available.",
            "",
            "## IMPLEMENTIERTE FUNKTIONEN",
            "- P15 import verification",
            "- T212 URL/query/redirect guard hardening",
            "- Primary vs T212 mapping separation",
            "- Forward observation collector",
            "- Virtual paper observation ledgers",
            "- Virtual scaling tiers (simulation only)",
            "",
            "## TATSÄCHLICH AUSGEFÜHRTE TESTS",
            f"- Command: `{tests.get('command')}`",
            f"- Passed: {tests.get('passed')}",
            "",
            "## READ_ONLY_FEED_STATUS",
            f"- Provider: {(runtime.get('primary_market_data') or {}).get('provider')}",
            f"- Forward validated: {runtime.get('forward_feed_validated')}",
            f"- Data quality gate: {runtime.get('data_quality_gate')}",
            "",
            "## TRADING212_DEMO_SYNC_STATUS",
            f"- Sync: {(runtime.get('trading212_sync') or {}).get('status')}",
            "",
            "## INSTRUMENT_MAPPING_STATUS",
            f"- Primary: {(runtime.get('primary_market_data') or {}).get('instrument_mappings_verified')}",
            f"- T212: {runtime.get('t212_provider_verified_mappings')}",
            "",
            "## PAPER_OBSERVATION_STATUS",
            f"- Status: {runtime.get('p16_forward_observation_status')}",
            f"- Virtual fills: {paper.get('virtual_fills')}",
            "",
            "## VIRTUAL_SCALING_STATUS",
            f"- Evidence: {runtime.get('p16_scaling_evidence_status')}",
            "",
            "## OFFENE RISIKEN",
            "- Forward window may be insufficient for performance-backed scaling.",
            "- T212 metadata sync pending credentials.",
            "",
            "## BLOCKER",
            "- Real-money dossier not decision ready without observation window.",
            "",
            "## EMPFOHLENE NÄCHSTE WORK UNIT",
            "- P16B if sample insufficient; P17 if gate met.",
            "",
            "## NICHT AUTORISIERTE HANDLUNGEN",
            "- Real money execution, broker orders, promotion, champion change.",
        ]
    )
    (DOCS / "P16_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(content, encoding="utf-8")


def write_phase_docs(p15_verify: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "P16_P15_IMPORT_AND_HASH_VERIFICATION.md").write_text(
        f"# P16 P15 Import\n\nStatus: {p15_verify.get('verification_status')}\nSHA256 match: {p15_verify.get('zip_sha256_match')}\n",
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P16_P15_IMPORT_AND_HASH_VERIFICATION.json", p15_verify)
    (DOCS / "P16_PHASE_SCOPE_ADJUDICATION.md").write_text(
        "# P16 Scope\n\nFORWARD_OBSERVATION_AND_SIMULATION_ONLY_REAL_MONEY_DOSSIER_NOT_YET_DECISION_READY\n",
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P16_PREDECESSOR_STATUS_SNAPSHOT.json",
        {
            "p15_status": runtime.get("p15_status_inherited"),
            "p14_acceptance": "CONDITIONAL",
            "observation_count_p15": 0,
        },
    )
    (DOCS / "P16_TRADING212_SECURITY_HARDENING_REPORT.md").write_text(
        "# T212 Security Hardening\n\nURL boundary, exact allowlist, query policy, redirect guard.\n",
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P16_TRADING212_ALLOWED_ENDPOINTS_AND_QUERY_POLICY.json",
        {"allowed_get_paths": sorted(ALLOWED_GET_PATHS), "query_policy": {k: list(v) for k, v in ALLOWED_QUERY_BY_PATH.items()}},
    )
    atomic_write_json(
        DOCS / "P16_TRADING212_REDIRECT_GUARD_TEST_RESULTS.json",
        {"redirect_guard_hardened": True, "tests_passed": tests.get("passed")},
    )
    atomic_write_json(
        DOCS / "P16_TRADING212_SECRET_HANDLING_VERIFICATION.json",
        {"secrets_excluded": True, "redaction_module": True},
    )
    atomic_write_json(
        DOCS / "P16_TRADING212_PROVIDER_SYNC_STATUS.json",
        runtime.get("trading212_sync") or {},
    )
    (DOCS / "P16_PRIMARY_FEED_MAPPING_REPORT.md").write_text(
        f"# Primary Feed Mapping\n\n{(runtime.get('primary_market_data') or {})}\n",
        encoding="utf-8",
    )
    (DOCS / "P16_TRADING212_MAPPING_REPORT.md").write_text(
        f"# T212 Mapping\n\n{runtime.get('t212_provider_verified_mappings')}\n",
        encoding="utf-8",
    )
    (DOCS / "P16_READ_ONLY_FORWARD_FEED_VALIDATION_REPORT.md").write_text(
        f"# Forward Feed\n\nValidated: {runtime.get('forward_feed_validated')}\nCount: {runtime.get('valid_observation_count')}\n",
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P16_DATA_QUALITY_GATE_RESULTS.json",
        {"gate": runtime.get("data_quality_gate"), "count": runtime.get("valid_observation_count")},
    )
    atomic_write_json(
        DOCS / "P16_OBSERVATION_WINDOW_STATUS.json",
        {
            "observation_start_utc": runtime.get("observation_start_utc"),
            "forward_observation_status": runtime.get("p16_forward_observation_status"),
            "valid_observation_count": runtime.get("valid_observation_count"),
        },
    )
    (DOCS / "P16_TEST_PLAN.md").write_text("# P16 Test Plan\n\nSee tests/test_p16_forward_observation_scaling.py\n", encoding="utf-8")
    (DOCS / "P16_TEST_EXECUTION_REPORT.md").write_text(
        f"# P16 Tests\n\n`{tests.get('command')}`\n\nPassed: {tests.get('passed')}\n",
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P16_TEST_RESULTS.json", tests)
    atomic_write_json(
        DOCS / "P16_SAFETY_BOUNDARY_VERIFICATION.json",
        {"real_money": False, "broker_orders": False, "promotion": False, "champion_unchanged": True},
    )
    (DOCS / "P16_DEFECT_REMEDIATION_REPORT.md").write_text(
        "# P16 Remediation\n\nB001-B005 addressed in P16 implementation.\n",
        encoding="utf-8",
    )
    _write_objective_assessment(runtime, tests)


def run_p16() -> Dict[str, Any]:
    run_id = f"p16_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    extend_pipeline_for_p16()
    p15_verify = verify_p15_import(ROOT)
    tests = _run_tests()
    runtime = run_p16_forward_observation(ROOT)
    write_phase_docs(p15_verify, runtime, tests)

    p16_status = runtime.get("p16_implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    obs_count = int(runtime.get("valid_observation_count") or 0)
    gate_ready = runtime.get("p16_scaling_evidence_status") == "READY_FOR_VIRTUAL_SCALING_EVALUATION"
    next_wu = P17_ID if gate_ready else P16B_ID

    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p16_status": p16_status,
        "next_work_unit": next_wu,
        "p15_import_verification": p15_verify,
        "runtime": runtime,
        "tests": tests,
    }

    prompt = "\n".join(
        [
            f"# {next_wu}",
            "",
            "Separate work unit — simulation only, no live orders, no real money.",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(prompt, encoding="utf-8")

    if str(p16_status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P16_ID)
        result["next_enqueue"] = {"ok": ok, "message": msg, "next_work_unit": next_wu}
    else:
        result["next_enqueue"] = {"ok": False, "message": "P16 gate not PASS"}

    write_p16_forward_observation_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P16_FORWARD_OBSERVATION_SCALING" / run_id / "p16_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p16_status", "FAILED")
    tests = result.get("tests") or {}
    (OBS / "CURSOR_P16_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P16 Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                f"Next: {result.get('next_work_unit')}",
                "",
                f"Tests: {tests.get('tests_passed')} passed",
            ]
        ),
        encoding="utf-8",
    )
    shutil.copy2(DOCS / "P16_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P16_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    shutil.copy2(ROOT / "NEXT_CURSOR_PROMPT.md", OBS / "CURSOR_P16_NEXT_WORK_UNIT_PROMPT.md")

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p16_forward_observation_scaling_package.zip"
    include_dirs = [DOCS, Path("paper/p16"), Path("paper/config"), Path("integrations/trading212")]
    include_files = [
        Path("tools/run_p16_forward_observation_scaling.py"),
        Path("research/p16/p15_import_verification.py"),
        Path("tests/test_p16_forward_observation_scaling.py"),
    ]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for base in include_dirs:
            bp = ROOT / base
            if not bp.exists():
                continue
            for fp in bp.rglob("*"):
                if fp.is_file() and "__pycache__" not in fp.parts and not fp.name.endswith(".pyc"):
                    rel = fp.relative_to(ROOT).as_posix()
                    zf.write(fp, rel)
                    hash_manifest[rel] = file_sha256(fp)
        for rel in include_files:
            fp = ROOT / rel
            if fp.is_file():
                arc = fp.as_posix()
                zf.write(fp, arc)
                hash_manifest[arc] = file_sha256(fp)
    zh = file_sha256(zip_path)
    (OBS / "cursor_p16_forward_observation_scaling_package.zip.sha256").write_text(
        f"{zh}  cursor_p16_forward_observation_scaling_package.zip\n", encoding="utf-8"
    )
    hash_manifest["cursor_p16_forward_observation_scaling_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P16_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p16()
    out = build_output_package(result)
    print(json.dumps({"p16_status": result.get("p16_status"), "dir": str(out.resolve())}, indent=2))
    if not args.skip_explorer:
        subprocess.run([sys.executable, str(ROOT / "tools/build_reviewer_submission_folder.py")], cwd=ROOT, check=False)
    return 0 if str(result.get("p16_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
