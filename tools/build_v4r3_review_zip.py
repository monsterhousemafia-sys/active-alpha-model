"""Build codex_v4r3_final_build_gate_review.zip with duplicate-path and hash guards."""
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
ZIP_NAME = "codex_v4r3_final_build_gate_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V4R3.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V4R3_PREFLIGHT.md"),
    doc_rel("CODEX_V4R3_GIT_STATUS.txt"),
    doc_rel("CODEX_V4R3_FINAL_BUILD_GATE_REPORT.md"),
    doc_rel("CODEX_V4R3_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V4R3_PROTECTED_HASHES_BEFORE.json"),
    doc_rel("CODEX_V4R3_PROTECTED_HASHES_AFTER.json"),
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
    "aa_vision_controller.py",
    "aa_vision_review_gate.py",
    "aa_vision_phase_catalog.py",
    "tools/complete_v4r2_run.py",
    "tools/build_v4r2_review_zip.py",
    "tools/complete_v4r3_run.py",
    "tools/build_v4r3_review_zip.py",
    "tests/test_decision_cockpit_viewmodel.py",
    "tests/test_decision_cockpit_gui.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_controller.py",
    "tests/test_v4r_review_zip_packaging.py",
    "V4R3-BACKUP_MANIFEST.json",
    ".cursor/hooks.json",
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
    before_path = root / doc_rel("CODEX_V4R3_PROTECTED_HASHES_BEFORE.json")
    after_path = root / doc_rel("CODEX_V4R3_PROTECTED_HASHES_AFTER.json")
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
