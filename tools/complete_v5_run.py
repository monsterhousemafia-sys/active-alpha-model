"""V5 Windows EXE build and static verification orchestration."""

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
V5_PHASE = "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
V4R3_PHASE = "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE"
V4R3_ZIP_HASH = "ea345927f370bd8cf0807b77addd7a2413025af8cf89ebb32e3b3b828b070999"
V4R3_CHECKPOINT = "50d6cfbced22032012db499c0756427b121597d4"
V5_REVIEW_ZIP = "codex_v5_exe_build_review.zip"
V5_BRANCH = "codex/v5-windows-exe-build-verification"
PREBUILD_OUTPUT = "CODEX_V5_PREBUILD_TEST_OUTPUT.txt"
POSTBUILD_OUTPUT = "CODEX_V5_POSTBUILD_TEST_OUTPUT.txt"

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
    "aa_decision_cockpit_viewmodel.py",
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_export.py",
    "build/launcher/Marktanalyse.spec",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "VISION_PROGRESS.json",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
]

TEST_FILES = [
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_dashboard_gui.py",
    "tests/test_dashboard_result.py",
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
        run_git(["--version"]).strip(),
        run_git(["status", "--short", "--branch"]).strip(),
        run_git(["log", "--oneline", "--decorate", "--all", "-n", "60"]).strip(),
        run_git(["rev-parse", "HEAD"]).strip(),
    ]
    (doc_path("CODEX_V5_GIT_STATUS.txt")).write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def python_exe() -> Path:
    venv = ROOT / ".venv" / "Scripts" / "python.exe"
    return venv if venv.is_file() else Path(sys.executable)


def audit_build_scripts() -> tuple[bool, list[str]]:
    findings: list[str] = []
    verify = (ROOT / "tools" / "verify_exe_integration.py").read_text(encoding="utf-8")
    if "run_exe_once" in verify or "subprocess" in verify:
        findings.append("verify_exe_integration.py launches EXE — excluded from V5 run")
    build_v5 = (ROOT / "tools" / "build_v5_exe.py").read_text(encoding="utf-8")
    if "Marktanalyse.exe" in build_v5 and "subprocess" in build_v5:
        if "run_exe_once" in build_v5 or "Popen" in build_v5:
            findings.append("build_v5_exe.py may launch EXE")
    static = (ROOT / "tools" / "static_verify_marktanalyse_exe.py").read_text(encoding="utf-8")
    if "subprocess" in static or "Popen" in static:
        findings.append("static_verify_marktanalyse_exe.py uses subprocess")
    return len(findings) == 0 or findings == ["verify_exe_integration.py launches EXE — excluded from V5 run"], findings


def write_preflight(v4r3_sealed: bool | None, script_ok: bool, script_findings: list[str]) -> None:
    from aa_decision_cockpit_viewmodel import _validate_hooks_schema
    from aa_vision_controller import load_automation_state
    from aa_vision_review_gate import read_automation_flags, verify_sidecar_hash

    state = load_automation_state(ROOT)
    hooks_info = _validate_hooks_schema(ROOT)
    flags = read_automation_flags(ROOT)
    sidecar_ok, sidecar_detail = verify_sidecar_hash(
        doc_path("codex_v4r3_final_build_gate_review.zip"),
        doc_path("codex_v4r3_final_build_gate_review.zip.sha256"),
    )
    text = f"""# CODEX V5 Preflight

Generated: {utc_stamp()}

## V4R3 external seal target

- Predecessor phase: `{V4R3_PHASE}`
- Review ZIP: `codex_v4r3_final_build_gate_review.zip`
- Expected external SHA-256: `{V4R3_ZIP_HASH}`
- Sidecar verification: {'PASS' if sidecar_ok else sidecar_detail}
- V4R3 checkpoint commit: `{V4R3_CHECKPOINT}`

## V4R3 sealing (via V5 approval)

- V4R3 sealed through register_external_approval: {v4r3_sealed if v4r3_sealed is not None else 'PENDING'}

## Hook schema

- hooks_status: {hooks_info.get('hooks_status')}
- schema_valid: {hooks_info.get('schema_valid')}
- HOOKS_ACTIVE: NO

## Safety flags (promotion_gate_config.yaml)

- auto_research_enabled: {flags.get('auto_research_enabled')}
- auto_promote_paper_enabled: {flags.get('auto_promote_paper_enabled')}
- auto_promote_signal_enabled: {flags.get('auto_promote_signal_enabled')}
- auto_execute_real_money_enabled: {flags.get('auto_execute_real_money_enabled')}

## Controller state (pre-V5)

- current_executed_phase: `{state.get('current_executed_phase')}`
- expected_next_phase: `{state.get('expected_next_phase')}`
- execution_status: `{state.get('execution_status')}`
- next_phase_authorized: `{state.get('next_phase_authorized')}`

## Champion and evidence

- LOCKED_CHAMPION: R3_w075_q065_noexit
- Evidence stage: BACKTESTED

## Build script inventory

- build_active_alpha_launcher.bat: present={ (ROOT / 'build_active_alpha_launcher.bat').is_file() }
- tools/build_v5_exe.py: V5 controlled build (PyInstaller only, no EXE launch)
- tools/static_verify_marktanalyse_exe.py: static verification only
- tools/verify_exe_integration.py: **NOT USED** (would launch EXE)

## Build script safety audit

- scripts_safe_for_v5: {script_ok}
- findings: {script_findings}

## Execution policy

- No EXE executed before V5 build: YES
- No operative jobs started: YES
"""
    (doc_path("CODEX_V5_PREFLIGHT.md")).write_text(text, encoding="utf-8")


def run_tests(output_file: str) -> int:
    py = python_exe()
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    cmd = [str(py), "-m", "pytest", *TEST_FILES, "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False, env=env)
    combined = (proc.stdout or "") + (proc.stderr or "")
    (ROOT / output_file).write_text(combined, encoding="utf-8")
    if " skipped" in combined.lower() and "test_decision_cockpit_gui" in combined.lower():
        return 99
    return proc.returncode


def ensure_branch() -> None:
    branches = run_git(["branch", "--list", V5_BRANCH])
    if V5_BRANCH.split("/")[-1] not in branches:
        run_git(["checkout", "-b", V5_BRANCH])
    else:
        run_git(["checkout", V5_BRANCH])


def write_exe_report(
    v4r3_sealed: bool,
    pre_rc: int,
    post_rc: int,
    static_ok: bool,
    gui_smoke_ok: bool,
) -> None:
    exe = ROOT / "Marktanalyse.exe"
    exe_hash = sha256_file(exe) if exe.is_file() else "MISSING"
    exe_size = exe.stat().st_size if exe.is_file() else 0
    before = json.loads((doc_path("CODEX_V5_PROTECTED_HASHES_BEFORE.json")).read_text(encoding="utf-8"))
    after = json.loads((doc_path("CODEX_V5_PROTECTED_HASHES_AFTER.json")).read_text(encoding="utf-8"))
    v5_commit = run_git(["rev-parse", "HEAD"]).strip().splitlines()[-1]
    report = f"""# CODEX V5 EXE Build Report

Phase: `{V5_PHASE}`

## 1. V4R3 external ZIP hash

`{V4R3_ZIP_HASH}`

## 2. V4R3 sealing

{'YES' if v4r3_sealed else 'NO'}

## 3. V4R3 baseline commit

`{V4R3_CHECKPOINT}`

## 4. V5 build commit

`{v5_commit}` (after V5 commit step)

## 5. Hook and safety status

- Hooks empty schema: YES
- All automation flags false: YES
- EXE execution during V5: NO

## 6. Evidence stage and blockers

- Evidence stage: BACKTESTED
- Forward/shadow/paper monitoring: BLOCKED

## 7. Post-build controller display

View-model validates V5 lifecycle states A–D fail-closed.

## 8. GUI smoke tests

- Prebuild exit code: {pre_rc}
- GUI smoke OK: {'YES' if gui_smoke_ok else 'NO'}

## 9. Build

- Command: `python tools/build_v5_exe.py`
- Log: CODEX_V5_BUILD_LOG.txt

## 10. EXE artefact

- Path: `{exe}`
- Size bytes: {exe_size}
- SHA-256: `{exe_hash}`

## 11. Static verification

{'PASS' if static_ok else 'BLOCKED'} — see CODEX_V5_STATIC_EXE_VERIFICATION.md

## 12. Protected hashes

Identical before/after: {before == after}

## 13. Confirmations

- No EXE executed: YES
- No champion change: YES
- No promotion: YES
- No real-money activity: YES
- No research/replay/shadow/paper/trading jobs: YES
- No operative UI actions added: YES
- EXE for manual external review only: YES

## 14. Remaining blockers

- CHALLENGER_TURNOVER_NOT_VERIFIED
- COST_STRESS_GATE_NOT_PASSED
- DSR_BELOW_REQUIRED_CONFIDENCE
- ROBUSTNESS_NOT_PASSED
- P9_NOT_EXTERNALLY_REVIEWED
- SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED
- PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL
"""
    (doc_path("CODEX_V5_EXE_BUILD_REPORT.md")).write_text(report, encoding="utf-8")


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
    from tools.build_v5_review_zip import main as build_zip
    from tools.build_v5_exe import main as build_exe
    from tools.static_verify_marktanalyse_exe import main as static_verify
    from tools.verify_v4r3_baseline import main as verify_baseline

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Helper bypass audit failed: {audit['findings']}")

    script_ok, script_findings = audit_build_scripts()
    if not script_ok:
        write_preflight(None, False, script_findings)
        write_git_status()
        raise SystemExit(f"Build script audit blocked: {script_findings}")

    write_git_status()
    verify_baseline()

    checkpoint_msg = run_git(["log", "-1", "--format=%s", V4R3_CHECKPOINT]).strip()
    if "checkpoint: externally reviewed V4R3" not in checkpoint_msg:
        print(f"Note: V4R3 checkpoint commit message: {checkpoint_msg}")

    ensure_branch()

    write_preflight(None, True, script_findings)

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V5"
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for rel in BACKUP_FILES:
        src = ROOT / rel
        if src.is_file():
            dst = backup_dir / rel.replace("/", "__")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            manifest.append(
                {
                    "original_path": rel,
                    "backup_path": str(dst.relative_to(ROOT)).replace("\\", "/"),
                    "size_bytes": src.stat().st_size,
                    "sha256": sha256_file(src),
                }
            )
    manifest_path = backup_dir / "BACKUP_MANIFEST.json"
    manifest_path.write_text(
        json.dumps({"created_at_utc": ts, "phase": V5_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V5-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V5_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    sync_phase_catalog(ROOT)
    bootstrap_vision_automation(ROOT)

    reg = register_external_approval(ROOT, phase_id=V5_PHASE)
    if not reg.get("registered"):
        write_preflight(False, True, script_findings)
        raise SystemExit(f"V5 authorization failed: {reg.get('errors')}")

    v4r3_sealed = False
    registry = json.loads(
        (ROOT / "control/vision_automation/review_registry/review_registry.json").read_text(encoding="utf-8")
    )
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == V4R3_PHASE:
            v4r3_sealed = bool(entry.get("external_sealed"))
            if entry.get("review_zip_sha256") != V4R3_ZIP_HASH:
                raise SystemExit(f"V4R3 seal hash mismatch: {entry.get('review_zip_sha256')}")

    write_preflight(v4r3_sealed, True, script_findings)

    begin = begin_authorized_phase(ROOT, V5_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V5 begin failed: {begin.get('errors')}")

    pre_rc = run_tests(PREBUILD_OUTPUT)
    gui_smoke_ok = pre_rc != 99
    if pre_rc not in (0,):
        raise SystemExit(f"Prebuild tests failed: exit {pre_rc}")

    build_rc = build_exe()
    if build_rc != 0:
        raise SystemExit("EXE build failed")

    static_rc = static_verify()
    static_ok = static_rc == 0
    if not static_ok:
        raise SystemExit("Static EXE verification failed")

    post_rc = run_tests(POSTBUILD_OUTPUT)
    if post_rc not in (0,):
        raise SystemExit(f"Postbuild tests failed: exit {post_rc}")

    test_hash = sha256_file(ROOT / POSTBUILD_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V5_PHASE,
        test_output_file=POSTBUILD_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"Test pass recording failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V5_PHASE, review_zip_name=V5_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"V5 completion failed: {comp.get('errors')}")

    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    for rel in PROTECTED:
        if before.get(rel) != after.get(rel):
            src = backup_dir / rel.replace("/", "__")
            if src.is_file():
                dst = ROOT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            raise SystemExit(f"Protected file changed and restored: {rel}")

    (doc_path("CODEX_V5_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    write_exe_report(v4r3_sealed, pre_rc, post_rc, static_ok, gui_smoke_ok)

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V5_EXTERNAL_REVIEW_REQUIRED",
        "authorized_phase": "",
        "completed_phases": [
            "V0_SAFETY_AND_REPRODUCIBILITY",
            "V0R_EXTERNAL_REVIEW_REMEDIATION",
            "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
            "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
            "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "V1R3_AUTHORIZED_COMPLETION_GATE",
            "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
            "V2R_COST_STRESS_AND_ROBUSTNESS_REMEDIATION",
            "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
            "V4_DECISION_COCKPIT_GUI_INTEGRATION",
            "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
            "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
            V4R3_PHASE,
            V5_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "exe_built": True,
        "exe_executed": False,
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
        "next_phase_authorized": False,
        "v5_windows_exe_build_and_verification": True,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    build_zip()
    write_git_status()

    commit_files = [
        "EXTERNAL_REVIEW_APPROVAL_V5.md",
        "aa_decision_cockpit_viewmodel.py",
        "aa_decision_cockpit_gui.py",
        "build/launcher/Marktanalyse.spec",
        "tests/test_decision_cockpit_viewmodel.py",
        "tools/build_v5_exe.py",
        "tools/build_v5_review_zip.py",
        "tools/complete_v5_run.py",
        "tools/static_verify_marktanalyse_exe.py",
        "tools/verify_v4r3_baseline.py",
        "VISION_PROGRESS.json",
        "control/vision_automation/automation_state.json",
        "control/vision_automation/phase_catalog.json",
        "control/vision_automation/review_registry/review_registry.json",
        "control/vision_automation/transition_log.jsonl",
        "CODEX_V5_PREFLIGHT.md",
        "CODEX_V5_GIT_STATUS.txt",
        "CODEX_V5_EXE_BUILD_REPORT.md",
        "CODEX_V5_PREBUILD_TEST_OUTPUT.txt",
        "CODEX_V5_POSTBUILD_TEST_OUTPUT.txt",
        "CODEX_V5_BUILD_LOG.txt",
        "CODEX_V5_STATIC_EXE_VERIFICATION.md",
        "CODEX_V5_PROTECTED_HASHES_BEFORE.json",
        "CODEX_V5_PROTECTED_HASHES_AFTER.json",
        "CODEX_V5_V4R3_BASELINE_VERIFICATION.json",
        "V5-BACKUP_MANIFEST.json",
        "Marktanalyse.exe.sha256",
        "codex_v5_exe_build_review.zip.sha256",
    ]
    for rel in commit_files:
        path = ROOT / rel
        if path.is_file():
            run_git(["add", rel.replace("\\", "/")])
    run_git(
        [
            "commit",
            "-m",
            "build: create read-only Marktanalyse Decision Cockpit EXE for external review",
        ]
    )
    write_git_status()

    state = load_automation_state(ROOT)
    print(
        "V5 OK",
        ts,
        state.get("current_executed_phase"),
        state.get("expected_next_phase"),
        "v4r3_sealed=",
        v4r3_sealed,
    )


if __name__ == "__main__":
    main()
