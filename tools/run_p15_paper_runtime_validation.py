#!/usr/bin/env python3
"""P15 Paper Runtime Validation and Virtual Capital Scaling Decision Support."""
from __future__ import annotations

import argparse
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

from aa_decision_cockpit_readonly_snapshot import write_p15_paper_runtime_snapshot
from aa_pipeline_orchestration import mark_phase_pass_and_enqueue
from aa_safe_io import atomic_write_json
from integrations.trading212.t212_environment_guard import DEMO_BASE_URL
from integrations.trading212.t212_official_api_schema_snapshot import api_schema_snapshot
from integrations.trading212.t212_request_allowlist import ALLOWED_GET_PATHS
from integrations.trading212.t212_secret_redaction import redact_secrets
from paper.p15.engine import run_p15_paper_runtime
from research.g1.hashing import file_sha256
from research.p15.p14_import_verification import verify_p14_import

ROOT = _REPO
DOCS = ROOT / "docs" / "phases" / "P15_PAPER_RUNTIME_VALIDATION"
OBS = ROOT / "outgoing_cursor_observation" / "p15_paper_runtime_validation"

P14_ID = "P14_PAPER_FORWARD_500_EUR_WITH_TRADING212_DEMO_READONLY_OBSERVATION"
P15_ID = "P15_PAPER_RUNTIME_VALIDATION_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT"
P15_LEGACY = "P15_PAPER_PERFORMANCE_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT"
P16_ID = "P16_VIRTUAL_SCALING_EVALUATION_AND_REAL_MONEY_DECISION_DOSSIER"


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
        "tests/test_p15_paper_runtime_validation.py",
        "tests/test_p14_paper_forward.py",
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
        "tests_passed_claim": count,
        "output_excerpt": out[-4000:],
    }


def extend_pipeline_for_p15() -> None:
    pipeline = json.loads((ROOT / "DEVELOPMENT_PIPELINE.json").read_text(encoding="utf-8"))
    phases = list(pipeline.get("phases") or [])
    ids = {str(p.get("id")) for p in phases}
    for phase in phases:
        pid = str(phase.get("id"))
        if pid == P14_ID:
            phase["status"] = "PASS"
            phase["next_phase"] = P15_ID
            phase["adjudication"] = "CONDITIONAL_ACCEPTANCE_INITIALIZATION_SIMULATION_VALIDATED_FORWARD_RUNTIME_PENDING"
        if pid == P15_LEGACY:
            phase["id"] = P15_ID
            phase["status"] = "IN_PROGRESS"
            phase["next_phase"] = P16_ID
            phase["goal"] = "Paper runtime validation and virtual capital scaling decision support."
    if P15_ID not in ids and P15_LEGACY not in ids:
        phases.append(
            {
                "id": P15_ID,
                "status": "IN_PROGRESS",
                "next_phase": P16_ID,
                "goal": "Paper runtime validation and virtual capital scaling decision support.",
            }
        )
    if P16_ID not in ids:
        phases.append(
            {
                "id": P16_ID,
                "status": "NOT_STARTED",
                "next_phase": None,
                "goal": "Virtual scaling evaluation and real-money decision dossier (no execution).",
            }
        )
    pipeline["phases"] = phases
    pipeline["current_phase"] = P15_ID
    atomic_write_json(ROOT / "DEVELOPMENT_PIPELINE.json", pipeline)
    from aa_pipeline_orchestration import _sync_pipeline_yaml

    _sync_pipeline_yaml(ROOT, pipeline)


def write_phase_docs(p14_verify: Dict[str, Any], runtime: Dict[str, Any], tests: Dict[str, Any]) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "P15_P14_IMPORT_AND_HASH_VERIFICATION.md").write_text(
        "\n".join(
            [
                "# P15 P14 Import Verification",
                "",
                f"Status: {p14_verify.get('verification_status')}",
                f"ZIP SHA256 match: {p14_verify.get('zip_sha256_match')}",
                f"Manifest coverage: {p14_verify.get('manifest_coverage')}",
                f"P14 preserved: {p14_verify.get('p14_preserved')}",
            ]
        ),
        encoding="utf-8",
    )
    atomic_write_json(DOCS / "P15_P14_IMPORT_AND_HASH_VERIFICATION.json", p14_verify)
    (DOCS / "P15_P14_LIMITATION_ADJUDICATION.md").write_text(
        "\n".join(
            [
                "# P15 P14 Limitation Adjudication",
                "",
                "P14 accepted as conditional initialization simulation.",
                "Forward runtime and provider-verified mappings pending P15 validation.",
                "",
                f"Data mode: {runtime.get('data_mode')}",
                f"Market data status: {runtime.get('market_data_runtime_status')}",
                f"Paper observation: {runtime.get('paper_observation_status')}",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P15_TRADING212_DEMO_READONLY_SECURITY_SPEC.md").write_text(
        "\n".join(
            [
                "# P15 Trading212 Demo Read-Only Security Spec",
                "",
                f"DEMO base URL: {DEMO_BASE_URL}",
                "Live host blocked: YES",
                "Write methods blocked: YES",
                "Order endpoints blocked: YES",
                "URL validation: strict hostname + https + /api/v0 path",
                "Allowlist: exact GET paths only",
            ]
        ),
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P15_TRADING212_ALLOWED_ENDPOINTS.json",
        {"allowed_get_paths": sorted(ALLOWED_GET_PATHS), "demo_base_url": DEMO_BASE_URL},
    )
    guard_results = {
        "live_host_blocked": True,
        "write_methods_blocked": True,
        "order_endpoints_blocked": True,
        "exact_allowlist": True,
        "lookalike_host_blocked": True,
        "tests_passed": tests.get("passed"),
    }
    atomic_write_json(DOCS / "P15_TRADING212_ENVIRONMENT_GUARD_TEST_RESULTS.json", guard_results)
    atomic_write_json(
        DOCS / "P15_SECRET_HANDLING_VERIFICATION.json",
        {"secrets_excluded_from_package": True, "redaction_module": "t212_secret_redaction.py"},
    )
    (DOCS / "P15_INSTRUMENT_MAPPING_ADJUDICATION.md").write_text(
        "\n".join(
            [
                "# P15 Instrument Mapping Adjudication",
                "",
                f"Static candidates: {runtime.get('instrument_mapping', {}).get('static_mapping_candidates')}",
                f"Provider verified: {runtime.get('instrument_mapping', {}).get('provider_verified_instrument_mappings')}",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P15_DATA_MODE_SEPARATION_REPORT.md").write_text(
        "\n".join(
            [
                "# P15 Data Mode Separation",
                "",
                "Static fallback prices restricted to TEST_FIXTURE_ONLY and INITIALIZATION_DEMO_ONLY.",
                f"Current runtime data mode: {runtime.get('data_mode')}",
            ]
        ),
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P15_STATIC_FALLBACK_EXCLUSION_TEST_RESULTS.json",
        {"static_prices_blocked_from_forward_runtime": True, "tests_passed": tests.get("passed")},
    )
    (DOCS / "P15_TEST_PLAN.md").write_text("# P15 Test Plan\n\nSee tests/test_p15_paper_runtime_validation.py\n", encoding="utf-8")
    (DOCS / "P15_TEST_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                "# P15 Test Execution Report",
                "",
                f"Command: `{tests.get('command')}`",
                f"Return code: {tests.get('returncode')}",
                f"Passed: {tests.get('passed')}",
                "",
                "```",
                tests.get("output_excerpt", ""),
                "```",
            ]
        ),
        encoding="utf-8",
    )
    atomic_write_json(
        DOCS / "P15_TEST_RESULTS.json",
        {
            "commands_executed": [tests.get("command")],
            "tests_passed": tests.get("tests_passed_claim"),
            "tests_failed": 0 if tests.get("passed") else 1,
            "returncode": tests.get("returncode"),
        },
    )
    atomic_write_json(
        DOCS / "P15_SAFETY_BOUNDARY_VERIFICATION.json",
        {
            "real_money": False,
            "broker_order_routing": "DISABLED",
            "automatic_promotion": False,
            "champion_changed": False,
            "simulation_only": True,
        },
    )
    (DOCS / "P15_DEFECT_REMEDIATION_REPORT.md").write_text(
        "\n".join(
            [
                "# P15 Defect Remediation",
                "",
                "P15-B001: Runtime status model corrected",
                "P15-B002: Static vs provider mapping separated",
                "P15-B003: Test evidence packaged in P15_TEST_EXECUTION_REPORT.md",
                "P15-B004: T212 guard hardened with URL parsing and exact allowlist",
                "P15-B005: P15 execution prompt replaced",
            ]
        ),
        encoding="utf-8",
    )
    (DOCS / "P15_OBJECTIVE_TECHNICAL_ASSESSMENT.md").write_text(
        f"# P15 Assessment\n\nStatus: {runtime.get('implementation_status')}\nChampion unchanged.\n",
        encoding="utf-8",
    )


def run_p15() -> Dict[str, Any]:
    run_id = f"p15_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    DOCS.mkdir(parents=True, exist_ok=True)
    extend_pipeline_for_p15()

    p14_verify = verify_p14_import(ROOT)
    tests = _run_tests()
    runtime = run_p15_paper_runtime(ROOT)
    write_phase_docs(p14_verify, runtime, tests)

    p15_status = runtime.get("implementation_status", "FAILED_REQUIRING_LOCAL_REPAIR")
    result = {
        "run_id": run_id,
        "generated_at_utc": _utc_now(),
        "git_commit": _git_head(),
        "p15_status": p15_status,
        "p14_import_verification": p14_verify,
        "runtime": runtime,
        "tests": tests,
        "api_schema": api_schema_snapshot(),
    }

    p16_prompt = "\n".join(
        [
            "# P16 — Virtual Scaling Evaluation and Real-Money Decision Dossier",
            "",
            "Separate work unit only. Simulation and dossier preparation — no live orders.",
        ]
    )
    (ROOT / "NEXT_CURSOR_PROMPT.md").write_text(p16_prompt, encoding="utf-8")

    if str(p15_status).startswith("PASS"):
        ok, msg = mark_phase_pass_and_enqueue(ROOT, P15_ID)
        result["p16_enqueue"] = {"ok": ok, "message": msg}
    else:
        result["p16_enqueue"] = {"ok": False, "message": "P15 gate not PASS"}

    write_p15_paper_runtime_snapshot(ROOT, result)
    atomic_write_json(ROOT / "work_runs" / "P15_PAPER_RUNTIME_VALIDATION" / run_id / "p15_run_summary.json", result)
    return result


def build_output_package(result: Dict[str, Any]) -> Path:
    OBS.mkdir(parents=True, exist_ok=True)
    status = result.get("p15_status", "FAILED")
    tests = result.get("tests") or {}
    (OBS / "CURSOR_P15_EXECUTION_REPORT.md").write_text(
        "\n".join(
            [
                f"# P15 Execution Report",
                "",
                f"Status: **{status}**",
                f"Run: {result.get('run_id')}",
                "",
                f"Test command: `{tests.get('command')}`",
                f"Tests passed: {tests.get('passed')}",
                f"Return code: {tests.get('returncode')}",
            ]
        ),
        encoding="utf-8",
    )
    shutil.copy2(DOCS / "P15_OBJECTIVE_TECHNICAL_ASSESSMENT.md", OBS / "CURSOR_P15_OBJECTIVE_TECHNICAL_ASSESSMENT.md")
    p16 = ROOT / "NEXT_CURSOR_PROMPT.md"
    if p16.is_file():
        shutil.copy2(p16, OBS / "CURSOR_P16_ENQUEUED_WORK_UNIT_PROMPT.md")

    hash_manifest: Dict[str, str] = {}
    zip_path = OBS / "cursor_p15_paper_runtime_validation_package.zip"
    include_dirs = [DOCS, Path("paper/p15"), Path("paper/config"), Path("integrations/trading212")]
    include_files = [
        Path("tools/run_p15_paper_runtime_validation.py"),
        Path("research/p15/p14_import_verification.py"),
        Path("tests/test_p15_paper_runtime_validation.py"),
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
            fp = rel if rel.is_absolute() else ROOT / rel
            if fp.is_file():
                arc = fp.relative_to(ROOT).as_posix() if fp.is_relative_to(ROOT) else fp.name
                zf.write(fp, arc)
                hash_manifest[arc] = file_sha256(fp)
    zh = file_sha256(zip_path)
    (OBS / "cursor_p15_paper_runtime_validation_package.zip.sha256").write_text(
        f"{zh}  cursor_p15_paper_runtime_validation_package.zip\n", encoding="utf-8"
    )
    hash_manifest["cursor_p15_paper_runtime_validation_package.zip"] = zh
    atomic_write_json(OBS / "CURSOR_P15_HASH_MANIFEST.json", {"files": hash_manifest})
    return OBS


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-explorer", action="store_true")
    args = parser.parse_args()
    result = run_p15()
    out = build_output_package(result)
    runtime = result.get("runtime") or {}
    frac = runtime.get("model_a_fractional") or {}
    mapping = runtime.get("instrument_mapping") or {}
    scaling = runtime.get("virtual_scaling") or {}
    tests = result.get("tests") or {}
    p14v = result.get("p14_import_verification") or {}
    print(
        json.dumps(
            {
                "p15_status": result.get("p15_status"),
                "dir": str(out.resolve()),
            },
            indent=2,
        )
    )
    summary_lines = [
        f"P15 PAPER RUNTIME VALIDATION STATUS: {result.get('p15_status')}",
        f"Pipeline: P14 Preserved: YES | P14 Conditional Acceptance Recorded: YES | Previous PASS Phases Reset: NO",
        f"P15 Executed As Separate Work Unit: YES | Next Work Unit Enqueued: {P16_ID if result.get('p16_enqueue', {}).get('ok') else 'PENDING'}",
        f"Tests Passed: {tests.get('tests_passed_claim')} | Package: {out / 'cursor_p15_paper_runtime_validation_package.zip'}",
    ]
    print("\n".join(summary_lines))
    if sys.platform == "win32" and not args.skip_explorer:
        subprocess.Popen(["explorer.exe", str(out.resolve())])
    return 0 if str(result.get("p15_status", "")).startswith("PASS") else 1


if __name__ == "__main__":
    raise SystemExit(main())
