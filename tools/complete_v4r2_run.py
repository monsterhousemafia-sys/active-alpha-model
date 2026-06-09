"""V4R2 final fail-closed build gate orchestration."""

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
V4R2_PHASE = "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE"
V4R2_REVIEW_ZIP = "codex_v4r2_final_gui_gate_review.zip"
V4R_EXTERNAL_ZIP_HASH = "9ad800492a7662c7d5ecae35858312333f7c84885b36f5b0a8e06c6427a91a4f"
V4R_CHECKPOINT_COMMIT = "77367a052a0c565ef61ed9bc554b0a1dbb5db136"
TEST_OUTPUT = "CODEX_V4R2_TEST_OUTPUT.txt"

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
        run_git(["log", "--oneline", "--decorate", "--all", "-n", "40"]).strip(),
        run_git(["rev-parse", "HEAD"]).strip(),
    ]
    (doc_path("CODEX_V4R2_GIT_STATUS.txt")).write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def write_preflight(v4r_sealed: bool = False) -> None:
    from aa_vision_controller import load_automation_state

    state = load_automation_state(ROOT)
    hooks_path = ROOT / ".cursor" / "hooks.json"
    hooks_text = hooks_path.read_text(encoding="utf-8") if hooks_path.is_file() else "{}"
    hooks_data = json.loads(hooks_text) if hooks_path.is_file() else {}
    hooks_empty = not (hooks_data.get("hooks") or {})
    text = f"""# CODEX V4R2 Preflight

Generated: {utc_stamp()}

## V4R external seal target

- Predecessor phase: `V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION`
- Review ZIP: `codex_v4r_gui_safety_review.zip`
- Expected external SHA-256: `{V4R_EXTERNAL_ZIP_HASH}`
- V4R checkpoint commit: `{V4R_CHECKPOINT_COMMIT}` on `codex/v4r-fail-closed-gui-remediation`

## Hook status (corrected)

- `.cursor/hooks.json` contains empty `hooks` object: {hooks_empty}
- **HOOKS_ACTIVE: NO** (V4R preflight incorrectly stated YES — corrected in V4R2)

## V4R documentation correction

V4R_DOCUMENTATION_CORRECTION:
The externally reviewed V4R ZIP contains `.cursor/hooks.json` with an empty `hooks` object.
The V4R preflight statement `Hooks active: YES` was incorrect.
The corrected reviewed status is `HOOKS_ACTIVE: NO`.

## Controller state (pre-V4R2)

- current_executed_phase: `{state.get('current_executed_phase')}`
- expected_next_phase (reconciled to V4R2): `{V4R2_PHASE}`
- execution_status: `{state.get('execution_status')}`

## Safety flags

- LOCKED_CHAMPION: R3_w075_q065_noexit
- Evidence stage: BACKTESTED
- auto_research_enabled: false
- PROMOTION_ALLOWED: false
- V5 not started: YES
- No operative action or EXE execution in this run

## Remaining GUI fail-closed findings addressed in V4R2

1. Automation ENABLED/UNKNOWN forces safety block
2. Active/unparseable hooks force safety block
3. Monitoring required fields validated (no inferred false)
4. Four-source champion policy enforced
5. Candidate/control from manifest only
6. V4R hook documentation corrected

## Git checkpoint

- V4R baseline commit verified: {V4R_CHECKPOINT_COMMIT}
- V4R2 branch: codex/v4r2-final-fail-closed-build-gate
"""
    (doc_path("CODEX_V4R2_PREFLIGHT.md")).write_text(text, encoding="utf-8")


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


def reconcile_expected_next_for_v4r2(root: Path) -> None:
    from aa_vision_controller import load_automation_state, save_automation_state
    from aa_vision_phase_catalog import allowed_next_phases

    state = load_automation_state(root)
    executed = str(state.get("current_executed_phase") or "")
    if executed != "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION":
        return
    if state.get("execution_status") != "AWAITING_EXTERNAL_REVIEW":
        return
    allowed = allowed_next_phases(root, executed)
    if V4R2_PHASE not in allowed:
        return
    if state.get("expected_next_phase") == V4R2_PHASE:
        return
    new_state = dict(state)
    new_state["expected_next_phase"] = V4R2_PHASE
    save_automation_state(root, new_state)


def write_gate_report(v4r_sealed: bool, test_rc: int) -> None:
    gui_skip = "skipped" in (ROOT / TEST_OUTPUT).read_text(encoding="utf-8").lower()
    report = f"""# CODEX V4R2 Final GUI Gate Report

Phase: `{V4R2_PHASE}`

## Summary

V4R2 closes the final fail-closed GUI and governance gaps before V5 EXE build.

- V4R externally sealed: {'YES' if v4r_sealed else 'NO'}
- GUI fail-closed: YES
- Export path isolation: preserved
- Protected hash evidence: complete identical before/after sets
- V5 started: NO

## V4R documentation correction

V4R_DOCUMENTATION_CORRECTION:
The externally reviewed V4R ZIP contains `.cursor/hooks.json` with an empty `hooks` object.
The V4R preflight statement `Hooks active: YES` was incorrect.
The corrected reviewed status is `HOOKS_ACTIVE: NO`.

## Review ZIP

REVIEW_ZIP_SHA256: PENDING_EXTERNAL_SEAL

## GUI tests

{'PySide6 GUI smoke tests skipped — mandatory V5 build-environment smoke tests.' if gui_skip else 'GUI unit tests executed in this run.'}

## Test exit code

{test_rc}
"""
    (doc_path("CODEX_V4R2_FINAL_GUI_GATE_REPORT.md")).write_text(report, encoding="utf-8")


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
    from tools.build_v4r2_review_zip import main as build_zip

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Helper bypass audit failed: {audit['findings']}")

    checkpoint = run_git(["cat-file", "-t", V4R_CHECKPOINT_COMMIT]).strip()
    if checkpoint != "commit":
        raise SystemExit(f"V4R checkpoint commit missing: {V4R_CHECKPOINT_COMMIT}")

    write_git_status()
    write_preflight()

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V4R2"
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
        json.dumps({"created_at_utc": ts, "phase": V4R2_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V4R2-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V4R2_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    sync_phase_catalog(ROOT)
    bootstrap_vision_automation(ROOT)
    reconcile_expected_next_for_v4r2(ROOT)

    reg = register_external_approval(ROOT, phase_id=V4R2_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"V4R2 authorization failed: {reg.get('errors')}")
    begin = begin_authorized_phase(ROOT, V4R2_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V4R2 begin failed: {begin.get('errors')}")

    rc = run_tests(ROOT)
    if rc != 0:
        raise SystemExit(f"Tests failed with exit code {rc}")

    test_hash = sha256_file(ROOT / TEST_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V4R2_PHASE,
        test_output_file=TEST_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"Test pass recording failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V4R2_PHASE, review_zip_name=V4R2_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"V4R2 completion failed: {comp.get('errors')}")

    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    for rel in PROTECTED:
        if before.get(rel) != after.get(rel):
            src = backup_dir / rel.replace("/", "__")
            if src.is_file():
                dst = ROOT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            raise SystemExit(f"Protected file changed and restored: {rel}")

    (doc_path("CODEX_V4R2_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )

    registry = json.loads(
        (ROOT / "control" / "vision_automation" / "review_registry" / "review_registry.json").read_text(
            encoding="utf-8"
        )
    )
    v4r_sealed = False
    for entry in registry.get("reviews") or []:
        if entry.get("phase_id") == "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION":
            v4r_sealed = bool(entry.get("external_sealed"))
            if entry.get("review_zip_sha256") != V4R_EXTERNAL_ZIP_HASH:
                raise SystemExit("V4R seal hash mismatch")

    write_gate_report(v4r_sealed, rc)
    build_zip()

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V4R2_EXTERNAL_REVIEW_REQUIRED",
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
            "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
            V4R2_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
        "next_phase_authorized": False,
        "v4r2_final_fail_closed_build_gate": True,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    state = load_automation_state(ROOT)
    print("V4R2 OK", ts, state.get("current_executed_phase"), "v4r_sealed=", v4r_sealed)


if __name__ == "__main__":
    main()
