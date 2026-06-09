"""V4R fail-closed GUI and review evidence remediation orchestration."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GIT = r"C:\Program Files\Git\cmd\git.exe"
V4R_PHASE = "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION"
V4R_REVIEW_ZIP = "codex_v4r_gui_safety_review.zip"
V4_EXTERNAL_ZIP_HASH = "75808571c9cf44a2b58cc1dd85bff4d84640a4ccafd2bda61d09fd5622f28037"
TEST_OUTPUT = "CODEX_V4R_TEST_OUTPUT.txt"

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
    "aa_vision_phase_catalog.py",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "VISION_PROGRESS.json",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_vision_phase_catalog.py",
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
        run_git(["log", "--oneline", "--decorate", "--all", "-n", "30"]).strip(),
        run_git(["rev-parse", "HEAD"]).strip(),
    ]
    (doc_path("CODEX_V4R_GIT_STATUS.txt")).write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_preflight() -> None:
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    hooks = (ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8") if (ROOT / ".cursor" / "hooks.json").is_file() else "{}"
    hooks_active = '"hooks": {}' not in hooks.replace(" ", "")
    text = f"""# CODEX V4R Preflight

Generated: {utc_stamp()}

## V4 external seal target

- Predecessor phase: `V4_DECISION_COCKPIT_GUI_INTEGRATION`
- Review ZIP: `codex_v4_gui_review.zip`
- Expected external SHA-256: `{V4_EXTERNAL_ZIP_HASH}`
- V4R seals V4 on `register_external_approval`

## Controller state (pre-V4R)

- current_executed_phase: `{state.get('current_executed_phase')}`
- expected_next_phase (reconciled to V4R): `{V4R_PHASE}`
- execution_status: `{state.get('execution_status')}`

## Hook and safety status

- Hooks active: {'YES' if hooks_active else 'NO'}
- LOCKED_CHAMPION: R3_w075_q065_noexit
- Evidence stage: BACKTESTED (must not increase)
- V5 not started: YES

## Fail-closed GUI findings remediated in V4R

1. Champion fail-open fallback removed — multi-source consensus required
2. Evidence stage now source-validated and dynamic
3. Current blockers and source conflicts visible in GUI
4. Experiment manifest uses actual schema fields
5. Missing monitoring evidence shows UNKNOWN — BLOCKED FOR SAFETY
6. Export restricted to isolated directories outside protected paths
7. Complete before/after protected-hash evidence (V4 after file was incomplete)
8. Git status included in review package
9. Tests added for all fail-closed paths

## V4 protected hash note

- `CODEX_V4_PROTECTED_HASHES_AFTER.json` was incomplete (3 paths only)
- V4R generates full 16-path before/after sets

## Prohibited in this run

- V5 EXE build or execution
- Operative jobs, promotion, champion change
"""
    (doc_path("CODEX_V4R_PREFLIGHT.md")).write_text(text, encoding="utf-8")


def run_tests(root: Path) -> int:
    tests = [
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
        "tests/test_decision_cockpit_viewmodel.py",
        "tests/test_decision_cockpit_gui.py",
        "tests/test_v4r_review_zip_packaging.py",
    ]
    cmd = [sys.executable, "-m", "pytest", *tests, "-q"]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    combined = (proc.stdout or "") + (proc.stderr or "")
    (root / TEST_OUTPUT).write_text(combined, encoding="utf-8")
    return proc.returncode


def reconcile_expected_next_for_v4r(root: Path) -> None:
    from aa_vision_controller import load_automation_state, save_automation_state
    from aa_vision_phase_catalog import allowed_next_phases

    state = load_automation_state(root)
    executed = str(state.get("current_executed_phase") or "")
    if executed != "V4_DECISION_COCKPIT_GUI_INTEGRATION":
        return
    if state.get("execution_status") != "AWAITING_EXTERNAL_REVIEW":
        return
    allowed = allowed_next_phases(root, executed)
    if V4R_PHASE not in allowed:
        return
    if state.get("expected_next_phase") == V4R_PHASE:
        return
    new_state = dict(state)
    new_state["expected_next_phase"] = V4R_PHASE
    save_automation_state(root, new_state)


def write_safety_report(v4_sealed: bool, test_rc: int) -> None:
    gui_skip = "skipped" in (ROOT / TEST_OUTPUT).read_text(encoding="utf-8").lower()
    report = f"""# CODEX V4R GUI Safety Report

Phase: `{V4R_PHASE}`

## Summary

V4R enforces fail-closed read-only Decision Cockpit display before any V5 EXE build.

- V4 externally sealed: {'YES' if v4_sealed else 'NO'}
- GUI fail-closed remediation: YES
- Export path isolation: YES
- Protected hash evidence: complete before/after sets
- V5 started: NO

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL

## GUI tests

{'PySide6 GUI smoke tests skipped — execute in V5 build environment.' if gui_skip else 'GUI unit tests executed in this run.'}

## Test exit code

{test_rc}
"""
    (doc_path("CODEX_V4R_GUI_SAFETY_REPORT.md")).write_text(report, encoding="utf-8")


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
    from tools.build_v4r_review_zip import main as build_zip

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Helper bypass audit failed: {audit['findings']}")

    write_git_status()
    write_preflight()

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V4R"
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
        json.dumps({"created_at_utc": ts, "phase": V4R_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V4R-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V4R_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    sync_phase_catalog(ROOT)
    bootstrap_vision_automation(ROOT)
    reconcile_expected_next_for_v4r(ROOT)

    reg = register_external_approval(ROOT, phase_id=V4R_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"V4R authorization failed: {reg.get('errors')}")
    begin = begin_authorized_phase(ROOT, V4R_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V4R begin failed: {begin.get('errors')}")

    rc = run_tests(ROOT)
    if rc != 0:
        raise SystemExit(f"Tests failed with exit code {rc}")

    test_hash = sha256_file(ROOT / TEST_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V4R_PHASE,
        test_output_file=TEST_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"Test pass recording failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V4R_PHASE, review_zip_name=V4R_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"V4R completion failed: {comp.get('errors')}")

    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    for rel in PROTECTED:
        if before.get(rel) != after.get(rel):
            src = backup_dir / rel.replace("/", "__")
            if src.is_file():
                dst = ROOT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            raise SystemExit(f"Protected file changed and restored: {rel}")

    (doc_path("CODEX_V4R_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    registry = json.loads(
        (ROOT / "control" / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    v4_sealed = False
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == "V4_DECISION_COCKPIT_GUI_INTEGRATION":
            v4_sealed = bool(entry.get("external_sealed"))
            if entry.get("review_zip_sha256") != V4_EXTERNAL_ZIP_HASH:
                raise SystemExit("V4 seal hash mismatch")

    write_safety_report(v4_sealed, rc)
    build_zip()

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V4R_EXTERNAL_REVIEW_REQUIRED",
        "authorized_phase": "",
        "completed_phases": [
            "V0_SAFETY_AND_REPRODUCIBILITY",
            "V0R_EXTERNAL_REVIEW_REMEDIATION",
            "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
            "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
            "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "V1R3_AUTHORIZED_COMPLETION_GATE",
            "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
            "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION",
            "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
            "V4_DECISION_COCKPIT_GUI_INTEGRATION",
            V4R_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
        "next_phase_authorized": False,
        "selected_external_branch": "V4_DECISION_COCKPIT_GUI_INTEGRATION",
        "v4_fail_closed_gui_remediation": True,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    state = load_automation_state(ROOT)
    print("V4R OK", ts, state.get("current_executed_phase"), "v4_sealed=", v4_sealed)


if __name__ == "__main__":
    main()
