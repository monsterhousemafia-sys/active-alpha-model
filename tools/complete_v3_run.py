"""V3 controlled forward monitoring foundation orchestration."""

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
V3_PHASE = "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION"
V3_REVIEW_ZIP = "codex_v3_monitor_foundation_review.zip"
TEST_OUTPUT = "CODEX_V3_TEST_OUTPUT.txt"

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
]

BACKUP_FILES = [
    "aa_evidence_status.py",
    "aa_forward_monitor_schema.py",
    "aa_monitoring_readiness.py",
    "aa_shadow_monitor_status.py",
    "aa_paper_monitor_status.py",
    "aa_vision_controller.py",
    "aa_vision_phase_catalog.py",
    "control/evidence/current_evidence_status.json",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "VISION_PROGRESS.json",
]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    ]
    cmd = [sys.executable, "-m", "pytest", *tests, "-q"]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    combined = (proc.stdout or "") + (proc.stderr or "")
    (root / TEST_OUTPUT).write_text(combined, encoding="utf-8")
    return proc.returncode


def main() -> None:
    from aa_evidence_status import export_evidence_status
    from aa_monitoring_readiness import (
        export_forward_monitoring_data_requirements,
        export_forward_monitoring_readiness,
    )
    from aa_paper_monitor_status import export_paper_monitor_status
    from aa_safe_io import atomic_write_json
    from aa_shadow_monitor_status import export_shadow_monitor_status
    from aa_v2_bypass_audit import audit_helper_scripts
    from aa_vision_controller import (
        begin_authorized_phase,
        bootstrap_vision_automation,
        complete_authorized_phase,
        load_automation_state,
        record_phase_test_pass,
        register_external_approval,
    )

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Helper bypass audit failed: {audit['findings']}")

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V3"
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
        json.dumps({"created_at_utc": ts, "phase": V3_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V3-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V3_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    bootstrap_vision_automation(ROOT)

    reg = register_external_approval(ROOT, phase_id=V3_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"V3 authorization failed: {reg.get('errors')}")
    begin = begin_authorized_phase(ROOT, V3_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V3 begin failed: {begin.get('errors')}")

    export_forward_monitoring_readiness(ROOT)
    export_forward_monitoring_data_requirements(ROOT)
    export_shadow_monitor_status(ROOT)
    export_paper_monitor_status(ROOT)
    export_evidence_status(ROOT)

    rc = run_tests(ROOT)
    if rc != 0:
        raise SystemExit(f"Tests failed with exit code {rc}")

    test_hash = sha256_file(ROOT / TEST_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V3_PHASE,
        test_output_file=TEST_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"Test pass recording failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V3_PHASE, review_zip_name=V3_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"V3 completion failed: {comp.get('errors')}")

    after = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    for rel in PROTECTED:
        if before.get(rel) != after.get(rel):
            src = backup_dir / rel.replace("/", "__")
            if src.is_file():
                dst = ROOT / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            raise SystemExit(f"Protected file changed and restored: {rel}")

    progress = {
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "current_phase": "V3_EXTERNAL_REVIEW_REQUIRED",
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
            V3_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "",
        "pending_external_branch_options": [
            "V3S_SHADOW_OBSERVATION_ACTIVATION",
            "V4_DECISION_COCKPIT_GUI_INTEGRATION",
        ],
        "next_required_artifact": "EXTERNAL_REVIEW_APPROVAL_V3S.md or EXTERNAL_REVIEW_APPROVAL_V4.md",
        "next_phase_authorized": False,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    (doc_path("CODEX_V3_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )
    state = load_automation_state(ROOT)
    print("V3 OK", ts, state.get("current_executed_phase"), state.get("pending_external_branch_options"))


if __name__ == "__main__":
    main()
