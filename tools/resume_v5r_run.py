"""Resume interrupted V5R — no re-register, no re-begin, no EXE execution."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
V5R_PHASE = "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR"
V5R_REVIEW_ZIP = "codex_v5r_standalone_exe_review.zip"
PREBUILD = "CODEX_V5R_PREBUILD_TEST_OUTPUT.txt"
POSTBUILD = "CODEX_V5R_POSTBUILD_TEST_OUTPUT.txt"
REJECTED_EXE_HASH = "44c84873f38f009c2cae5f504cd0f5644ca5f743fb74e34e5cf20013723d3fad"

PROTECTED = [
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "model_output_sp500_pit_t212/background_research_status.json",
    "control/last_known_good_state.json",
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/p9_shadow_paper_prep_status.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/evidence/current_evidence_status.json",
    "control/evidence/cost_stress_status.json",
    "control/evidence/robustness_status.json",
    "control/evidence/multiple_testing_status.json",
    "control/evidence/forward_monitoring_readiness_status.json",
    "control/evidence/shadow_monitor_status.json",
    "control/evidence/paper_monitor_status.json",
    "control/evidence/forward_monitoring_data_requirements.json",
]

TESTS = [
    "tests/test_decision_cockpit_readonly_launcher.py",
    "tests/test_v5r_standalone_spec.py",
    "tests/test_v5r_build_chain_audit.py",
    "tests/test_v5r_snapshot.py",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_dashboard_result.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_review_gate.py",
    "tests/test_vision_controller.py",
    "tests/test_evidence_status.py",
    "tests/test_cost_stress.py",
    "tests/test_robustness_evidence.py",
    "tests/test_multiple_testing_adjustment.py",
    "tests/test_monitoring_readiness.py",
    "tests/test_shadow_monitor_status.py",
    "tests/test_paper_monitor_status.py",
]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def python_exe() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def validate_state() -> None:
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    if state.get("authorized_phase") != V5R_PHASE:
        raise SystemExit("authorized_phase mismatch")
    if state.get("current_running_phase") != V5R_PHASE:
        raise SystemExit("current_running_phase mismatch")
    if state.get("execution_status") != "RUNNING_AUTHORIZED_PHASE":
        raise SystemExit("not RUNNING_AUTHORIZED_PHASE")


def run_tests(output: str) -> int:
    py = python_exe()
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [str(py), "-m", "pytest", *TESTS, "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=600,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    (ROOT / output).write_text(combined, encoding="utf-8")
    if " skipped" in combined.lower() and "test_decision_cockpit_gui" in combined.lower():
        return 99
    return proc.returncode


def patch_v5r_registry() -> None:
    from aa_safe_io import atomic_write_json

    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V5R_PHASE:
            entry.update(
                {
                    "exe_built": True,
                    "exe_executed": False,
                    "distribution_type": "ONEFILE_STANDALONE",
                    "entrypoint": "tools/decision_cockpit_readonly_launcher.py",
                    "artifact_acceptance": "PENDING_EXTERNAL_REVIEW",
                    "review_zip_sha256": "PENDING_EXTERNAL_SEAL",
                }
            )
    atomic_write_json(path, registry)


def main() -> None:
    from aa_safe_io import atomic_write_json
    from aa_vision_controller import complete_authorized_phase, load_automation_state, record_phase_test_pass
    from tools.build_v5r_review_zip import main as build_zip
    from tools.build_v5r_standalone_exe import main as build_exe
    from tools.static_verify_v5r_standalone_exe import main as static_verify

    validate_state()
    before = json.loads((doc_path("CODEX_V5R_PROTECTED_HASHES_BEFORE.json")).read_text(encoding="utf-8"))

    pre_rc = run_tests(PREBUILD)
    if pre_rc != 0:
        raise SystemExit(f"Prebuild failed: {pre_rc}")

    if build_exe() != 0:
        raise SystemExit("Build failed")
    new_hash = sha256_file(ROOT / "Marktanalyse.exe").lower()
    if new_hash == REJECTED_EXE_HASH.lower():
        raise SystemExit("EXE hash unchanged from rejected V5")

    if static_verify() != 0:
        raise SystemExit("Static verify failed")

    post_rc = run_tests(POSTBUILD)
    if post_rc != 0:
        raise SystemExit(f"Postbuild failed: {post_rc}")

    rec = record_phase_test_pass(
        ROOT,
        phase_id=V5R_PHASE,
        test_output_file=POSTBUILD,
        test_output_sha256=sha256_file(ROOT / POSTBUILD),
    )
    if not rec.get("recorded"):
        raise SystemExit(f"record failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V5R_PHASE, review_zip_name=V5R_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"complete failed: {comp.get('errors')}")

    patch_v5r_registry()
    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    if before != after:
        raise SystemExit("Protected hashes changed")
    (doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    report = f"""# CODEX V5R Standalone EXE Report

V5R resume completed.

- EXE SHA-256: `{new_hash}`
- DISTRIBUTION_TYPE: ONEFILE_STANDALONE
- EXE executed: NO

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
"""
    (doc_path("CODEX_V5R_STANDALONE_EXE_REPORT.md")).write_text(report, encoding="utf-8")
    atomic_write_json(
        ROOT / "VISION_PROGRESS.json",
        {
            "program": "MARKTANALYSE_DECISION_COCKPIT",
            "current_phase": "V5R_EXTERNAL_REVIEW_REQUIRED",
            "v5r_standalone_exe_rebuild": True,
            "distribution_type": "ONEFILE_STANDALONE",
            "next_expected_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
        },
    )
    build_zip()
    print("V5R RESUME OK", new_hash[:16])


if __name__ == "__main__":
    main()
