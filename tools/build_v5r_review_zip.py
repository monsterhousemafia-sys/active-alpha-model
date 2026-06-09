"""Build codex_v5r_standalone_exe_review.zip — EXE excluded."""
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
ZIP_NAME = "codex_v5r_standalone_exe_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V5R.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V5R_PREFLIGHT.md"),
    doc_rel("CODEX_V5R_GIT_STATUS.txt"),
    doc_rel("CODEX_V5R_REJECTED_V5_EXE_BASELINE.json"),
    doc_rel("CODEX_V5R_BUILD_CHAIN_AUDIT.md"),
    doc_rel("CODEX_V5R_STANDALONE_EXE_REPORT.md"),
    doc_rel("CODEX_V5R_PREBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5R_POSTBUILD_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V5R_BUILD_LOG.txt"),
    doc_rel("CODEX_V5R_STATIC_EXE_VERIFICATION.md"),
    doc_rel("CODEX_V5R_PROTECTED_HASHES_BEFORE.json"),
    doc_rel("CODEX_V5R_PROTECTED_HASHES_AFTER.json"),
    "Marktanalyse.exe.sha256",
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
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "model_output_sp500_pit_t212/background_research_status.json",
    "tools/decision_cockpit_readonly_launcher.py",
    "tools/build_v5r_standalone_exe.py",
    "tools/static_verify_v5r_standalone_exe.py",
    "tools/complete_v5r_run.py",
    "tools/build_v5r_review_zip.py",
    "build/decision_cockpit/Marktanalyse.spec",
    "aa_decision_cockpit_viewmodel.py",
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_export.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "aa_vision_controller.py",
    "aa_vision_review_gate.py",
    "aa_vision_phase_catalog.py",
    "tests/test_decision_cockpit_readonly_launcher.py",
    "tests/test_v5r_standalone_spec.py",
    "tests/test_v5r_build_chain_audit.py",
    "tests/test_v5r_snapshot.py",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "V5R-BACKUP_MANIFEST.json",
    ".cursor/hooks.json",
]


def validate_include_paths(paths: List[str]) -> Tuple[bool, List[str]]:
    seen: set[str] = set()
    dups: List[str] = []
    for rel in paths:
        norm = rel.replace("\\", "/")
        if norm in seen:
            dups.append(norm)
        seen.add(norm)
    return len(dups) == 0, dups


def validate_protected_hashes(root: Path) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    before = json.loads((root / doc_rel("CODEX_V5R_PROTECTED_HASHES_BEFORE.json")).read_text(encoding="utf-8"))
    after = json.loads((root / doc_rel("CODEX_V5R_PROTECTED_HASHES_AFTER.json")).read_text(encoding="utf-8"))
    if set(before.keys()) != set(after.keys()):
        errors.append("path_set_mismatch")
    for k in before:
        if before[k] != after.get(k):
            errors.append(f"hash_changed:{k}")
    return len(errors) == 0, errors


def main() -> None:
    ok, dups = validate_include_paths(INCLUDE)
    if not ok:
        raise SystemExit(f"Duplicate ZIP paths: {dups}")
    hash_ok, errs = validate_protected_hashes(ROOT)
    if not hash_ok:
        raise SystemExit(f"Protected hash check failed: {errs}")
    zip_path = ROOT / ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = ROOT / rel
            if path.is_file():
                zf.write(path, rel.replace("\\", "/"))
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (ROOT / f"{ZIP_NAME}.sha256").write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(f"Wrote {ZIP_NAME} sha256={digest}")


if __name__ == "__main__":
    main()
