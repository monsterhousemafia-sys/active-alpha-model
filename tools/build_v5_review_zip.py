"""Build codex_v5_exe_build_review.zip — EXE binary excluded per V5 policy."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import json
import zipfile
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
ZIP_NAME = "codex_v5_exe_build_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V5.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V5_RECOVERY_PREFLIGHT.md"),
    doc_rel("CODEX_V5_RECOVERY_GIT_STATUS.txt"),
    doc_rel("CODEX_V5_GIT_STATUS.txt"),
    doc_rel("CODEX_V5_V4R3_BASELINE_VERIFICATION.json"),
    doc_rel("CODEX_V5_INTERRUPTED_STATE_DIFF.json"),
    doc_rel("CODEX_V5_PREEXISTING_EXE_BASELINE.json"),
    doc_rel("CODEX_V5_ORCHESTRATOR_AUDIT.md"),
    doc_rel("CODEX_V5_EXE_BUILD_REPORT.md"),
    doc_rel("CODEX_V5_GUI_PREBUILD_TEST.log"),
    doc_rel("CODEX_V5_PREBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5_POSTBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5_BUILD_LOG.txt"),
    doc_rel("CODEX_V5_STATIC_EXE_VERIFICATION.md"),
    doc_rel("CODEX_V5_PROTECTED_HASHES_BEFORE.json"),
    doc_rel("CODEX_V5_PROTECTED_HASHES_AFTER.json"),
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "control/system_health.json",
    "control/last_known_good_state.json",
    "control/p9_shadow_paper_prep_status.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/evidence/current_evidence_status.json",
    "control/evidence/cost_stress_status.json",
    "control/evidence/robustness_status.json",
    "control/evidence/multiple_testing_status.json",
    "control/evidence/forward_monitoring_readiness_status.json",
    "control/evidence/shadow_monitor_status.json",
    "control/evidence/paper_monitor_status.json",
    "control/evidence/forward_monitoring_data_requirements.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "model_output_sp500_pit_t212/background_research_status.json",
    "aa_decision_cockpit_viewmodel.py",
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_export.py",
    "aa_dashboard_qt_window.py",
    "aa_dashboard_result.py",
    "aa_model_status.py",
    "aa_vision_controller.py",
    "aa_vision_review_gate.py",
    "aa_vision_phase_catalog.py",
    "build_active_alpha_launcher.bat",
    "tools/active_alpha_launcher.py",
    "tools/static_verify_marktanalyse_exe.py",
    "tools/build_v5_exe.py",
    "tools/complete_v5_run.py",
    "tools/resume_v5_run.py",
    "tools/build_v5_review_zip.py",
    "tools/verify_v4r3_baseline.py",
    "build/launcher/Marktanalyse.spec",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_dashboard_gui.py",
    "tests/test_dashboard_result.py",
    "V5-BACKUP_MANIFEST.json",
    ".cursor/hooks.json",
    "Marktanalyse.exe.sha256",
]


def validate_include_paths(paths: List[str]) -> Tuple[bool, List[str]]:
    seen: set[str] = set()
    duplicates: List[str] = []
    for rel in paths:
        norm = rel.replace("\\", "/")
        if norm in seen:
            duplicates.append(norm)
        seen.add(norm)
    return len(duplicates) == 0, duplicates


def validate_protected_hashes(root: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    before_path = root / doc_rel("CODEX_V5_PROTECTED_HASHES_BEFORE.json")
    after_path = root / doc_rel("CODEX_V5_PROTECTED_HASHES_AFTER.json")
    if not before_path.is_file():
        return False, ["missing_before_hashes"]
    if not after_path.is_file():
        return False, ["missing_after_hashes"]
    before: Dict[str, str] = json.loads(before_path.read_text(encoding="utf-8"))
    after: Dict[str, str] = json.loads(after_path.read_text(encoding="utf-8"))
    if set(before.keys()) != set(after.keys()):
        errors.append("before_after_path_sets_differ")
    for key in before:
        if key not in after:
            errors.append(f"missing_after:{key}")
        elif before[key] != after[key]:
            errors.append(f"hash_changed:{key}")
    return len(errors) == 0, errors


def main() -> None:
    ok, dups = validate_include_paths(INCLUDE)
    if not ok:
        raise SystemExit(f"Duplicate ZIP target paths blocked: {dups}")
    hash_ok, hash_errors = validate_protected_hashes(ROOT)
    if not hash_ok:
        raise SystemExit(f"Protected hash validation blocked packaging: {hash_errors}")
    zip_path = ROOT / ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = ROOT / f"{ZIP_NAME}.sha256"
    sidecar.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"Wrote {zip_path.name} sha256={digest}")


if __name__ == "__main__":
    main()
