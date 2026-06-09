"""Resume interrupted V5 build — no re-register, no begin_authorized_phase, no EXE execution."""

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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"
V5_PHASE = "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
V4R3_PHASE = "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE"
V4R3_ZIP_HASH = "ea345927f370bd8cf0807b77addd7a2413025af8cf89ebb32e3b3b828b070999"
V5_REVIEW_ZIP = "codex_v5_exe_build_review.zip"
PREBUILD_OUTPUT = "CODEX_V5_PREBUILD_TEST_OUTPUT.txt"
POSTBUILD_OUTPUT = "CODEX_V5_POSTBUILD_TEST_OUTPUT.txt"
PREEXISTING_BASELINE = "CODEX_V5_PREEXISTING_EXE_BASELINE.json"

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

REGRESSION_TESTS = [
    "tests/test_p7_auto_promotion.py",
    "tests/test_pipeline_orchestration.py",
    "tests/test_pipeline_autopilot.py",
    "tests/test_control_plane.py",
    "tests/test_p9_controlled_shadow_paper_validation.py",
    "tests/test_evidence_schema.py",
    "tests/test_experiment_registry.py",
    "tests/test_evidence_status.py",
    "tests/test_cost_stress.py",
    "tests/test_robustness_evidence.py",
    "tests/test_multiple_testing_adjustment.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_review_gate.py",
    "tests/test_vision_controller.py",
    "tests/test_forward_monitor_schema.py",
    "tests/test_monitoring_readiness.py",
    "tests/test_shadow_monitor_status.py",
    "tests/test_paper_monitor_status.py",
    "tests/test_v4r_review_zip_packaging.py",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(args: list[str]) -> str:
    proc = subprocess.run([GIT, *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def python_exe() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def validate_resume_state() -> None:
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    required = {
        "authorized_phase": V5_PHASE,
        "current_running_phase": V5_PHASE,
        "execution_status": "RUNNING_AUTHORIZED_PHASE",
    }
    for key, val in required.items():
        if state.get(key) != val:
            raise SystemExit(f"INTERRUPTED_V5_STATE_NOT_SAFE_TO_RESUME: {key}={state.get(key)!r}")

    registry = json.loads(
        (ROOT / "control/vision_automation/review_registry/review_registry.json").read_text(encoding="utf-8")
    )
    v4r3_sealed = False
    v5_completed = False
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V4R3_PHASE:
            v4r3_sealed = bool(entry.get("external_sealed"))
            if entry.get("review_zip_sha256") != V4R3_ZIP_HASH:
                raise SystemExit("V4R3 seal hash mismatch")
        if entry.get("phase_id") == V5_PHASE and entry.get("completed_at_utc"):
            v5_completed = True
    if not v4r3_sealed:
        raise SystemExit("V4R3 not externally sealed")
    if v5_completed:
        raise SystemExit("V5 already completed in review registry")

    for artefact in ("CODEX_V5_BUILD_LOG.txt", "CODEX_V5_STATIC_EXE_VERIFICATION.md", V5_REVIEW_ZIP):
        if (ROOT / artefact).is_file():
            raise SystemExit(f"Prior V5 completion artefact exists: {artefact}")


def protected_hashes() -> dict[str, str]:
    return {rel: sha256_file(ROOT / rel) for rel in PROTECTED}


def run_pytest(tests: list[str], log_path: Path) -> int:
    py = python_exe()
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [str(py), "-m", "pytest", *tests, "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    log_path.write_text(combined, encoding="utf-8")
    lower = combined.lower()
    if " skipped" in lower and ("test_decision_cockpit_gui" in lower or "test_dashboard_gui" in lower):
        return 99
    return proc.returncode


def write_exe_report(v4r3_sealed: bool, pre_rc: int, post_rc: int, static_ok: bool) -> None:
    exe = ROOT / "Marktanalyse.exe"
    pre = json.loads((ROOT / PREEXISTING_BASELINE).read_text(encoding="utf-8"))
    new_hash = sha256_file(exe)
    new_mtime = exe.stat().st_mtime if exe.is_file() else 0
    report = f"""# CODEX V5 EXE Build Report

Phase: `{V5_PHASE}` (resumed after interrupted run)

## Recovery

- Interrupted run recovered: YES
- V4R3 sealed: {'YES' if v4r3_sealed else 'NO'}
- Pre-existing EXE baseline preserved: YES

## Pre-existing EXE (not V5 build evidence)

- SHA-256: `{pre.get('sha256')}`
- LastWriteTimeUtc: `{pre.get('last_write_time_utc')}`

## New V5 build EXE

- Path: `{exe}`
- Size bytes: {exe.stat().st_size if exe.is_file() else 0}
- SHA-256: `{new_hash}`
- Distinct from pre-existing: {new_hash.lower() != str(pre.get('sha256', '')).lower()}

## Tests

- GUI prebuild: see CODEX_V5_GUI_PREBUILD_TEST.log
- Full prebuild exit: {pre_rc}
- Postbuild exit: {post_rc}

## Static verification

{'PASS' if static_ok else 'BLOCKED'}

## Protected hashes

See CODEX_V5_PROTECTED_HASHES_BEFORE.json and AFTER.json

## Confirmations

- EXE executed: NO
- Pre-existing EXE reused as build evidence: NO
- No operative jobs: YES

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
"""
    (doc_path("CODEX_V5_EXE_BUILD_REPORT.md")).write_text(report, encoding="utf-8")


def git_commit_v5() -> bool:
    files = [
        "EXTERNAL_REVIEW_APPROVAL_V5.md",
        "aa_decision_cockpit_viewmodel.py",
        "aa_decision_cockpit_gui.py",
        "build/launcher/Marktanalyse.spec",
        "tests/test_decision_cockpit_viewmodel.py",
        "tests/test_decision_cockpit_gui.py",
        "tools/build_v5_exe.py",
        "tools/build_v5_review_zip.py",
        "tools/complete_v5_run.py",
        "tools/resume_v5_run.py",
        "tools/static_verify_marktanalyse_exe.py",
        "tools/verify_v4r3_baseline.py",
        "VISION_PROGRESS.json",
        "control/vision_automation/automation_state.json",
        "control/vision_automation/review_registry/review_registry.json",
        "control/vision_automation/transition_log.jsonl",
        "CODEX_V5_RECOVERY_PREFLIGHT.md",
        "CODEX_V5_RECOVERY_GIT_STATUS.txt",
        "CODEX_V5_V4R3_BASELINE_VERIFICATION.json",
        "CODEX_V5_INTERRUPTED_STATE_DIFF.json",
        "CODEX_V5_PREEXISTING_EXE_BASELINE.json",
        "CODEX_V5_ORCHESTRATOR_AUDIT.md",
        "CODEX_V5_EXE_BUILD_REPORT.md",
        "CODEX_V5_GUI_PREBUILD_TEST.log",
        "CODEX_V5_PREBUILD_TEST_OUTPUT.txt",
        "CODEX_V5_POSTBUILD_TEST_OUTPUT.txt",
        "CODEX_V5_BUILD_LOG.txt",
        "CODEX_V5_STATIC_EXE_VERIFICATION.md",
        "CODEX_V5_PROTECTED_HASHES_BEFORE.json",
        "CODEX_V5_PROTECTED_HASHES_AFTER.json",
        "V5-BACKUP_MANIFEST.json",
        "Marktanalyse.exe.sha256",
        "codex_v5_exe_build_review.zip.sha256",
    ]
    for rel in files:
        if (ROOT / rel).is_file():
            run_git(["add", rel.replace("\\", "/")])
    out = run_git(["commit", "-m", "build: create read-only Marktanalyse Decision Cockpit EXE for external review"])
    return "nothing to commit" not in out.lower()


def main() -> None:
    from aa_safe_io import atomic_write_json
    from aa_vision_controller import (
        complete_authorized_phase,
        load_automation_state,
        record_phase_test_pass,
    )
    from tools.build_v5_exe import main as build_exe
    from tools.build_v5_review_zip import main as build_zip
    from tools.static_verify_marktanalyse_exe import main as static_verify
    from tools.verify_v4r3_baseline import main as verify_baseline

    if not (ROOT / PREEXISTING_BASELINE).is_file():
        raise SystemExit(f"Missing {PREEXISTING_BASELINE}")
    validate_resume_state()
    verify_baseline()

    before = protected_hashes()
    (doc_path("CODEX_V5_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    gui_rc = run_pytest(
        ["tests/test_decision_cockpit_viewmodel.py", "tests/test_decision_cockpit_gui.py"],
        doc_path("CODEX_V5_GUI_PREBUILD_TEST.log"),
    )
    if gui_rc != 0:
        raise SystemExit(f"GUI_SMOKE_TESTS_NOT_PASSED_IN_BUILD_ENVIRONMENT: exit {gui_rc}")

    reg_rc = run_pytest(REGRESSION_TESTS, ROOT / PREBUILD_OUTPUT)
    combined_pre = (doc_path("CODEX_V5_GUI_PREBUILD_TEST.log")).read_text(encoding="utf-8")
    combined_pre += "\n\n=== REGRESSION SUITE ===\n\n"
    combined_pre += (ROOT / PREBUILD_OUTPUT).read_text(encoding="utf-8")
    (ROOT / PREBUILD_OUTPUT).write_text(combined_pre, encoding="utf-8")
    if reg_rc != 0:
        raise SystemExit(f"Prebuild regression failed: exit {reg_rc}")

    if build_exe() != 0:
        raise SystemExit("EXE build failed")

    pre = json.loads((ROOT / PREEXISTING_BASELINE).read_text(encoding="utf-8"))
    exe = ROOT / "Marktanalyse.exe"
    new_hash = sha256_file(exe).lower()
    if new_hash == str(pre.get("sha256", "")).lower():
        raise SystemExit("New build hash identical to pre-existing EXE — not a new V5 artefact")

    if static_verify() != 0:
        raise SystemExit("Static verification failed")

    post_rc = run_pytest(
        ["tests/test_decision_cockpit_viewmodel.py", "tests/test_decision_cockpit_gui.py", *REGRESSION_TESTS],
        ROOT / POSTBUILD_OUTPUT,
    )
    if post_rc != 0:
        raise SystemExit(f"Postbuild tests failed: exit {post_rc}")

    test_hash = sha256_file(ROOT / POSTBUILD_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V5_PHASE,
        test_output_file=POSTBUILD_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"record_phase_test_pass failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V5_PHASE, review_zip_name=V5_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"complete_authorized_phase failed: {comp.get('errors')}")

    after = protected_hashes()
    for rel in PROTECTED:
        if before.get(rel) != after.get(rel):
            raise SystemExit(f"Protected artefact changed: {rel}")
    (doc_path("CODEX_V5_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    v4r3_sealed = True
    write_exe_report(v4r3_sealed, 0, post_rc, True)

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V5_EXTERNAL_REVIEW_REQUIRED",
        "authorized_phase": "",
        "exe_built": True,
        "exe_executed": False,
        "next_expected_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
        "next_phase_authorized": False,
        "v5_windows_exe_build_and_verification": True,
        "interrupted_run_recovered": True,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    build_zip()
    git_commit_v5()

    state = load_automation_state(ROOT)
    print("V5 RESUME OK", utc_now(), state.get("current_executed_phase"), state.get("execution_status"))


if __name__ == "__main__":
    main()
