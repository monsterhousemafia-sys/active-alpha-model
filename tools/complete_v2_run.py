"""V2 cost stress and robustness completion orchestration."""

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
V2_PHASE = "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE"
V2_REVIEW_ZIP = "codex_v2_robustness_review.zip"
TEST_OUTPUT = "CODEX_V2_TEST_OUTPUT.txt"

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
]

BACKUP_FILES = [
    "aa_cost_stress.py",
    "aa_robustness_evidence.py",
    "aa_multiple_testing_adjustment.py",
    "aa_v2_source_inventory.py",
    "aa_v2_bypass_audit.py",
    "aa_evidence_status.py",
    "aa_evidence_schema.py",
    "control/evidence/current_evidence_status.json",
    "VISION_PROGRESS.json",
    "tests/test_cost_stress.py",
    "tests/test_robustness_evidence.py",
    "tests/test_multiple_testing_adjustment.py",
    "tests/test_v2_helper_bypass_preflight.py",
]


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(args: list[str]) -> str:
    out = subprocess.run([GIT, *args], capture_output=True, text=True, cwd=ROOT, check=False)
    return (out.stdout or out.stderr or "").strip()


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
        "tests/test_vision_phase_catalog.py",
        "tests/test_vision_review_gate.py",
        "tests/test_vision_controller.py",
        "tests/test_cost_stress.py",
        "tests/test_robustness_evidence.py",
        "tests/test_multiple_testing_adjustment.py",
        "tests/test_v2_helper_bypass_preflight.py",
    ]
    cmd = [sys.executable, "-m", "pytest", *tests, "-q"]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    combined = (proc.stdout or "") + (proc.stderr or "")
    (root / TEST_OUTPUT).write_text(combined, encoding="utf-8")
    return proc.returncode


def main() -> None:
    from aa_cost_stress import export_cost_stress_status
    from aa_evidence_status import export_evidence_status
    from aa_multiple_testing_adjustment import export_multiple_testing_status
    from aa_robustness_evidence import export_robustness_status
    from aa_safe_io import atomic_write_json
    from aa_v2_bypass_audit import audit_helper_scripts
    from aa_v2_source_inventory import export_v2_source_inventory
    from aa_vision_controller import (
        bootstrap_vision_automation,
        complete_authorized_phase,
        load_automation_state,
        record_phase_test_pass,
        register_external_approval,
        begin_authorized_phase,
    )

    audit = audit_helper_scripts(ROOT)
    if not audit["ok"]:
        raise SystemExit(f"Helper bypass audit failed: {audit['findings']}")

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V2"
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
        json.dumps({"created_at_utc": ts, "phase": V2_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V2-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V2_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    bootstrap_vision_automation(ROOT)
    reg = register_external_approval(ROOT, phase_id=V2_PHASE)
    if not reg.get("registered"):
        raise SystemExit(f"V2 authorization failed: {reg.get('errors')}")
    begin = begin_authorized_phase(ROOT, V2_PHASE)
    if not begin.get("started"):
        raise SystemExit(f"V2 begin failed: {begin.get('errors')}")

    export_v2_source_inventory(ROOT)
    export_cost_stress_status(ROOT)
    export_robustness_status(ROOT)
    export_multiple_testing_status(ROOT)
    export_evidence_status(ROOT)

    rc = run_tests(ROOT)
    if rc != 0:
        raise SystemExit(f"Tests failed with exit code {rc}")

    test_hash = sha256_file(ROOT / TEST_OUTPUT)
    rec = record_phase_test_pass(
        ROOT,
        phase_id=V2_PHASE,
        test_output_file=TEST_OUTPUT,
        test_output_sha256=test_hash,
    )
    if not rec.get("recorded"):
        raise SystemExit(f"Test pass recording failed: {rec.get('errors')}")

    comp = complete_authorized_phase(ROOT, phase_id=V2_PHASE, review_zip_name=V2_REVIEW_ZIP)
    if not comp.get("completed"):
        raise SystemExit(f"V2 completion failed: {comp.get('errors')}")

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
        "current_phase": "V2_EXTERNAL_REVIEW_REQUIRED",
        "authorized_phase": "",
        "completed_phases": [
            "V0_SAFETY_AND_REPRODUCIBILITY",
            "V0R_EXTERNAL_REVIEW_REMEDIATION",
            "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
            "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
            "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            "V1R3_AUTHORIZED_COMPLETION_GATE",
            V2_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
        "next_required_artifact": "EXTERNAL_REVIEW_APPROVAL_V3.md",
        "next_phase_authorized": False,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    (doc_path("CODEX_V2_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )
    state = load_automation_state(ROOT)
    print("V2 OK", ts, state.get("current_executed_phase"))


if __name__ == "__main__":
    main()
