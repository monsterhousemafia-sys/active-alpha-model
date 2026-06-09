"""V1R3 authorized completion gate orchestration."""

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
    "control/evidence/current_evidence_status.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
]

BACKUP_FILES = [
    "aa_vision_controller.py",
    "aa_vision_review_gate.py",
    "aa_vision_phase_catalog.py",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/review_registry/review_registry.json",
    "control/vision_automation/transition_log.jsonl",
    "VISION_PROGRESS.json",
    "tests/test_vision_controller.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_review_gate.py",
]

GIT = r"C:\Program Files\Git\cmd\git.exe"
V1R3_PHASE = "V1R3_AUTHORIZED_COMPLETION_GATE"
V1R3_REVIEW_ZIP = "codex_v1r3_authorized_completion_review.zip"
TEST_OUTPUT = "CODEX_V1R3_TEST_OUTPUT.txt"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_output(args: list[str]) -> str:
    out = subprocess.run([GIT, *args], capture_output=True, text=True, cwd=ROOT, check=False)
    return (out.stdout or out.stderr or "").strip()


def write_git_status(path: Path) -> None:
    sections = [
        git_output(["status", "--short", "--branch"]),
        git_output(["log", "--oneline", "--decorate", "--all", "-n", "20"]),
        git_output(["rev-parse", "HEAD"]),
    ]
    path.write_text("\n\n".join(sections) + "\n", encoding="utf-8")


def remediate_expected_next(root: Path) -> None:
    from aa_safe_io import atomic_write_json
    from aa_vision_controller import AUTOMATION_STATE, load_automation_state, save_automation_state
    from aa_vision_phase_catalog import sync_phase_catalog

    sync_phase_catalog(root)
    state = load_automation_state(root)
    if state.get("current_executed_phase") == "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING":
        if state.get("expected_next_phase") != V1R3_PHASE:
            state["expected_next_phase"] = V1R3_PHASE
            state["schema_version"] = 3
            state.setdefault("current_running_phase", "")
            save_automation_state(root, state)
    atomic_write_json(root / AUTOMATION_STATE, load_automation_state(root))


def run_tests(root: Path) -> int:
    out_path = root / TEST_OUTPUT
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_vision_controller.py",
        "tests/test_vision_phase_catalog.py",
        "tests/test_vision_review_gate.py",
        "tests/test_p7_auto_promotion.py",
        "tests/test_pipeline_orchestration.py",
        "tests/test_pipeline_autopilot.py",
        "tests/test_control_plane.py",
        "tests/test_p9_controlled_shadow_paper_validation.py",
        "tests/test_evidence_schema.py",
        "tests/test_experiment_registry.py",
        "tests/test_evidence_status.py",
        "-q",
    ]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True, check=False)
    combined = (proc.stdout or "") + (proc.stderr or "")
    out_path.write_text(combined, encoding="utf-8")
    return proc.returncode


def main() -> None:
    from aa_safe_io import atomic_write_json
    from aa_vision_controller import (
        bootstrap_vision_automation,
        load_automation_state,
        run_authorized_phase_pipeline,
    )

    ts = utc_stamp()
    backup_dir = ROOT / "control" / "repair_backups" / f"{ts}_V1R3"
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
        json.dumps({"created_at_utc": ts, "phase": V1R3_PHASE, "files": manifest}, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copy2(manifest_path, ROOT / "V1R3-BACKUP_MANIFEST.json")

    before = {rel: sha256_file(ROOT / rel) for rel in PROTECTED}
    (doc_path("CODEX_V1R3_PROTECTED_HASHES_BEFORE.json")).write_text(
        json.dumps(before, indent=2) + "\n", encoding="utf-8"
    )

    bootstrap_vision_automation(ROOT)
    remediate_expected_next(ROOT)

    rc = run_tests(ROOT)
    if rc != 0:
        raise SystemExit(f"Tests failed with exit code {rc}")

    pipeline = run_authorized_phase_pipeline(
        ROOT,
        phase_id=V1R3_PHASE,
        review_zip_name=V1R3_REVIEW_ZIP,
        test_output_file=TEST_OUTPUT,
    )
    if not pipeline.get("ok"):
        raise SystemExit(f"V1R3 pipeline failed at {pipeline.get('step')}: {pipeline.get('errors')}")

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
        "current_phase": "V1R3_EXTERNAL_REVIEW_REQUIRED",
        "authorized_phase": "",
        "completed_phases": [
            "V0_SAFETY_AND_REPRODUCIBILITY",
            "V0R_EXTERNAL_REVIEW_REMEDIATION",
            "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
            "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
            "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
            V1R3_PHASE,
        ],
        "external_review_required_before_next_phase": True,
        "exe_target": "Marktanalyse.exe",
        "real_money_execution_allowed": False,
        "auto_promotion_allowed": False,
        "auto_research_allowed": False,
        "next_expected_phase": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
        "next_required_artifact": "EXTERNAL_REVIEW_APPROVAL_V2.md",
        "next_phase_authorized": False,
    }
    atomic_write_json(ROOT / "VISION_PROGRESS.json", progress)

    (doc_path("CODEX_V1R3_PROTECTED_HASHES_AFTER.json")).write_text(
        json.dumps(after, indent=2) + "\n", encoding="utf-8"
    )
    state = load_automation_state(ROOT)
    print("V1R3 OK", ts, state.get("current_executed_phase"))


if __name__ == "__main__":
    main()
