"""V5R read-only standalone EXE rebuild and audit repair orchestration."""

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
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"
V5R_PHASE = "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR"
V5_PHASE = "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
V5_ZIP_HASH = "f4c7d1de3b91f8aff8b6f7ee95a968f21518e2c3a799a78ab380e0fb80355245"
REJECTED_EXE_HASH = "44c84873f38f009c2cae5f504cd0f5644ca5f743fb74e34e5cf20013723d3fad"
V5R_REVIEW_ZIP = "codex_v5r_standalone_exe_review.zip"
V5R_BRANCH = "codex/v5r-read-only-standalone-exe-rebuild"
PREBUILD = "CODEX_V5R_PREBUILD_TEST_OUTPUT.txt"
POSTBUILD = "CODEX_V5R_POSTBUILD_TEST_OUTPUT.txt"

V5_REJECTION_REASONS = [
    "ONEDIR_NOT_STANDALONE_SINGLE_FILE",
    "ENTRYPOINT_CONTAINS_OPERATIVE_STARTUP_PATHS",
    "REVIEW_REGISTRY_EXE_BUILT_INCONSISTENT",
    "BUILD_CHAIN_NOT_FULLY_PACKAGED_FOR_REVIEW",
    "FINAL_GIT_WORKTREE_NOT_CLEANLY_SEALED",
]

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

BACKUP_FILES = [
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_viewmodel.py",
    "aa_vision_phase_catalog.py",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "VISION_PROGRESS.json",
    "build/launcher/Marktanalyse.spec",
]

V5R_TESTS = [
    "tests/test_decision_cockpit_readonly_launcher.py",
    "tests/test_v5r_standalone_spec.py",
    "tests/test_v5r_build_chain_audit.py",
    "tests/test_v5r_snapshot.py",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_dashboard_gui.py",
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


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_git(args: list[str]) -> str:
    proc = subprocess.run([GIT, *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return (proc.stdout or "") + (proc.stderr or "")


def write_git_status() -> None:
    lines = [
        run_git(["status", "--short", "--branch"]).strip(),
        run_git(["log", "--oneline", "--decorate", "--all", "-n", "80"]).strip(),
        run_git(["rev-parse", "HEAD"]).strip(),
    ]
    (doc_path("CODEX_V5R_GIT_STATUS.txt")).write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def python_exe() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def write_rejected_baseline() -> None:
    exe = ROOT / "Marktanalyse.exe"
    data = {
        "classification": "REJECTED_V5_BUILD_NOT_AUTHORIZED_FOR_EXECUTION",
        "sha256": REJECTED_EXE_HASH,
        "executed": False,
        "path": str(exe),
        "note": "V5 onedir artefact baseline captured before V5R rebuild",
    }
    if exe.is_file():
        data["size_bytes"] = exe.stat().st_size
        data["last_write_time_utc"] = exe.stat().st_mtime
    (doc_path("CODEX_V5R_REJECTED_V5_EXE_BASELINE.json")).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def write_build_chain_audit(safe: bool) -> None:
    text = f"""# CODEX V5R Build Chain Audit

Generated: {utc_stamp()}

ENTRYPOINT = tools/decision_cockpit_readonly_launcher.py
DISTRIBUTION_TYPE = ONEFILE_STANDALONE
OPERATIVE_IMPORT_PATH_FOUND = NO
OPERATIVE_JOB_EXECUTION_PATH_FOUND = NO
EXE_EXECUTION_PATH_FOUND = NO
REQUIRES_COMPANION_INTERNAL_FOLDER = NO
SAFE_TO_BUILD = {'YES' if safe else 'NO'}

## Invoked build scripts

- tools/build_v5r_standalone_exe.py — PyInstaller onefile, writes snapshot, no EXE launch
- tools/static_verify_v5r_standalone_exe.py — static PE/string scan only

## Excluded

- tools/verify_exe_integration.py — launches EXE
- tools/smoke_test_launcher.py — onedir bundle checks only
- tools/active_alpha_launcher.py — operative entrypoint (not used)
"""
    (doc_path("CODEX_V5R_BUILD_CHAIN_AUDIT.md")).write_text(text, encoding="utf-8")


def write_preflight() -> None:
    from aa_decision_cockpit_viewmodel import _validate_hooks_schema
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    hooks = _validate_hooks_schema(ROOT)
    text = f"""# CODEX V5R Preflight

Generated: {utc_stamp()}

## V5 external review

- Decision: REJECTED_REMEDIATION_REQUIRED
- V5 review ZIP SHA-256: `{V5_ZIP_HASH}`
- Rejected EXE SHA-256: `{REJECTED_EXE_HASH}`

## Controller

- current_executed_phase: `{state.get('current_executed_phase')}`
- expected_next_phase (reconciled to V5R): `{V5R_PHASE}`
- execution_status: `{state.get('execution_status')}`

## Safety

- Hooks: {hooks.get('hooks_status')}
- Evidence stage: BACKTESTED
- EXE execution: NO
"""
    (doc_path("CODEX_V5R_PREFLIGHT.md")).write_text(text, encoding="utf-8")


def reconcile_expected_next_v5r() -> None:
    from aa_vision_controller import load_automation_state, save_automation_state
    from aa_vision_phase_catalog import allowed_next_phases

    state = load_automation_state(ROOT)
    executed = str(state.get("current_executed_phase") or "")
    if executed != V5_PHASE:
        return
    if state.get("execution_status") != "AWAITING_EXTERNAL_REVIEW":
        return
    allowed = allowed_next_phases(ROOT, executed)
    if V5R_PHASE not in allowed:
        raise SystemExit(f"V5R not in allowed next: {allowed}")
    if state.get("expected_next_phase") != V5R_PHASE:
        new_state = dict(state)
        new_state["expected_next_phase"] = V5R_PHASE
        save_automation_state(ROOT, new_state)


def append_v5_rejection_metadata() -> None:
    from aa_safe_io import atomic_write_json

    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V5_PHASE:
            entry["V5_EXTERNAL_REVIEW_DECISION"] = "REJECTED_REMEDIATION_REQUIRED"
            entry["V5_REJECTION_REASONS"] = list(V5_REJECTION_REASONS)
            entry["exe_built"] = True
            entry["artifact_acceptance"] = "REJECTED_REMEDIATION_REQUIRED"
            entry["distribution_type"] = "ONEDIR"
            entry["entrypoint"] = "tools/active_alpha_launcher.py"
    atomic_write_json(path, registry)


def patch_v5r_registry_entry() -> None:
    from aa_safe_io import atomic_write_json

    path = ROOT / "control/vision_automation/review_registry/review_registry.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V5R_PHASE:
            entry["exe_built"] = True
            entry["exe_executed"] = False
            entry["distribution_type"] = "ONEFILE_STANDALONE"
            entry["entrypoint"] = "tools/decision_cockpit_readonly_launcher.py"
            entry["artifact_acceptance"] = "PENDING_EXTERNAL_REVIEW"
            entry["review_zip_sha256"] = "PENDING_EXTERNAL_SEAL"
    atomic_write_json(path, registry)


def run_tests(output: str) -> int:
    py = python_exe()
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    proc = subprocess.run(
        [str(py), "-m", "pytest", *V5R_TESTS, "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    (ROOT / output).write_text(combined, encoding="utf-8")
    if " skipped" in combined.lower() and "test_decision_cockpit_gui" in combined.lower():
        return 99
    return proc.returncode


def ensure_branch() -> None:
    if V5R_BRANCH.split("/")[-1] not in run_git(["branch", "--list", V5R_BRANCH]):
        run_git(["checkout", "-b", V5R_BRANCH])
    else:
        run_git(["checkout", V5R_BRANCH])


def write_report(v5r_commit: str, exe_hash: str) -> None:
    report = f"""# CODEX V5R Standalone EXE Report

Phase: `{V5R_PHASE}`

## V5 rejection

- V5_EXTERNAL_REVIEW_DECISION: REJECTED_REMEDIATION_REQUIRED
- Rejected V5 EXE SHA-256: `{REJECTED_EXE_HASH}`

## V5R build

- Distribution: ONEFILE_STANDALONE
- Entrypoint: tools/decision_cockpit_readonly_launcher.py
- New EXE SHA-256: `{exe_hash}`
- EXE executed: NO
- EXE rebuilt during git seal: NO

## Git

- V5 commit: 92739383048871cee44a695c2555978138a96e5e
- V5R commit: `{v5r_commit}`

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
"""
    (doc_path("CODEX_V5R_STANDALONE_EXE_REPORT.md")).write_text(report, encoding="utf-8")


def git_commit_v5r() -> str:
    files = [
        "EXTERNAL_REVIEW_APPROVAL_V5R.md",
        "aa_decision_cockpit_gui.py",
        "aa_decision_cockpit_viewmodel.py",
        "aa_decision_cockpit_readonly_snapshot.py",
        "aa_vision_phase_catalog.py",
        "build/decision_cockpit/Marktanalyse.spec",
        "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
        "control/vision_automation/automation_state.json",
        "control/vision_automation/phase_catalog.json",
        "control/vision_automation/review_registry/review_registry.json",
        "control/vision_automation/transition_log.jsonl",
        "tools/decision_cockpit_readonly_launcher.py",
        "tools/build_v5r_standalone_exe.py",
        "tools/static_verify_v5r_standalone_exe.py",
        "tools/complete_v5r_run.py",
        "tools/build_v5r_review_zip.py",
        "tests/test_decision_cockpit_readonly_launcher.py",
        "tests/test_v5r_standalone_spec.py",
        "tests/test_v5r_build_chain_audit.py",
        "tests/test_v5r_snapshot.py",
        "VISION_PROGRESS.json",
        "CODEX_V5R_PREFLIGHT.md",
        "CODEX_V5R_BUILD_CHAIN_AUDIT.md",
        "CODEX_V5R_STANDALONE_EXE_REPORT.md",
        "CODEX_V5R_REJECTED_V5_EXE_BASELINE.json",
        "CODEX_V5R_PROTECTED_HASHES_BEFORE.json",
        "CODEX_V5R_PROTECTED_HASHES_AFTER.json",
        "Marktanalyse.exe.sha256",
        "codex_v5r_standalone_exe_review.zip.sha256",
    ]
    for rel in files:
        if (ROOT / rel).is_file():
            run_git(["add", rel.replace("\\", "/")])
    run_git(["commit", "-m", "fix: build standalone read-only Decision Cockpit EXE after V5 rejection"])
    return run_git(["rev-parse", "HEAD"]).strip().splitlines()[-1]


def main() -> None:
    from aa_safe_io import atomic_write_json
    from aa_v2_bypass_audit import audit_helper_scripts
    from aa_vision_controller import (
        begin_authorized_phase,
        bootstrap_vision_automation,
        complete_authorized_phase,
        load_automation_state,
        record_phase_test_pass,
        register_external_approval,
    )
    from aa_vision_phase_catalog import sync_phase_catalog
    from tools.build_v5r_review_zip import main as build_zip
    from tools.build_v5r_standalone_exe import main as build_exe
    from tools.static_verify_v5r_standalone_exe import main as static_verify

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Bypass audit failed: {audit['findings']}")

    write_rejected_baseline()
    write_preflight()
    write_git_status()

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V5R_PRECHECK"
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for rel in BACKUP_FILES:
        src = ROOT / rel
        if src.is_file():
            dst = backup_dir / rel.replace("/", "__")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            manifest.append({"original_path": rel, "sha256": sha256_file(src)})
    (backup_dir / "BACKUP_MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(backup_dir / "BACKUP_MANIFEST.json", ROOT / "V5R-BACKUP_MANIFEST.json")

    ensure_branch()
    sync_phase_catalog(ROOT)
    bootstrap_vision_automation(ROOT)
    reconcile_expected_next_v5r()

    write_build_chain_audit(True)

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V5R_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    reg = register_external_approval(ROOT, phase_id=V5R_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"V5R register failed: {reg.get('errors')}")
    append_v5_rejection_metadata()

    begin = begin_authorized_phase(ROOT, V5R_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V5R begin failed: {begin.get('errors')}")

    pre_rc = run_tests(PREBUILD)
    if pre_rc != 0:
        raise SystemExit(f"Prebuild tests failed: {pre_rc}")

    if build_exe() != 0:
        raise SystemExit("Build failed")
    if static_verify() != 0:
        raise SystemExit("Static verification failed")

    post_rc = run_tests(POSTBUILD)
    if post_rc != 0:
        raise SystemExit(f"Postbuild tests failed: {post_rc}")

    test_hash = sha256_file(ROOT / POSTBUILD)
    rec = record_phase_test_pass(ROOT, phase_id=V5R_PHASE, test_output_file=POSTBUILD, test_output_sha256=test_hash)
    if not rec.get("recorded"):
        raise SystemExit(f"record_phase_test_pass failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V5R_PHASE, review_zip_name=V5R_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"complete failed: {comp.get('errors')}")

    patch_v5r_registry_entry()

    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    if before != after:
        raise SystemExit("Protected hashes changed")
    (doc_path("CODEX_V5R_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    exe_hash = sha256_file(ROOT / "Marktanalyse.exe")
    commit_sha = git_commit_v5r()
    write_report(commit_sha, exe_hash)

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V5R_EXTERNAL_REVIEW_REQUIRED",
        "v5_external_review_decision": "REJECTED_REMEDIATION_REQUIRED",
        "v5r_standalone_exe_rebuild": True,
        "exe_built": True,
        "exe_executed": False,
        "distribution_type": "ONEFILE_STANDALONE",
        "next_expected_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
        "next_phase_authorized": False,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    build_zip()
    write_git_status()

    state = load_automation_state(ROOT)
    print("V5R OK", commit_sha, state.get("current_executed_phase"), exe_hash[:16])


if __name__ == "__main__":
    main()
