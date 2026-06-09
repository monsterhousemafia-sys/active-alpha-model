"""Build codex_v2r_statistical_validity_review.zip and sidecar."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import doc_path, doc_rel

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZIP_NAME = "codex_v2r_statistical_validity_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V2R.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V2R_PREFLIGHT.md"),
    doc_rel("CODEX_V2R_GIT_STATUS.txt"),
    doc_rel("CODEX_V2R_SOURCE_INVENTORY.md"),
    doc_rel("CODEX_V2R_STATISTICAL_VALIDITY_REPORT.md"),
    doc_rel("CODEX_V2R_TEST_OUTPUT.txt"),
    doc_rel("CODEX_V2R_PROTECTED_HASHES_BEFORE.json"),
    doc_rel("CODEX_V2R_PROTECTED_HASHES_AFTER.json"),
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "control/system_health.json",
    "control/last_known_good_state.json",
    "control/p9_shadow_paper_prep_status.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "control/evidence/current_evidence_status.json",
    "control/evidence/v2_source_inventory.json",
    "control/evidence/cost_stress_status.json",
    "control/evidence/robustness_status.json",
    "control/evidence/multiple_testing_status.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "model_output_sp500_pit_t212/background_research_status.json",
    "model_output_sp500_pit_t212/strategy_daily_returns.csv",
    "model_output_sp500_pit_t212/backtest_decisions.csv",
    "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/mom_blend_matched_controls_daily_returns.csv",
    "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_decisions.csv",
    "runs/20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce/naive_momentum_daily_returns.csv",
    "control/challenger_report.json",
    "aa_cost_stress.py",
    "aa_robustness_evidence.py",
    "aa_multiple_testing_adjustment.py",
    "aa_v2_source_inventory.py",
    "aa_evidence_status.py",
    "aa_vision_controller.py",
    "aa_vision_review_gate.py",
    "aa_vision_phase_catalog.py",
    "tools/complete_v2_run.py",
    "tools/complete_v2r_run.py",
    "tools/build_v2_review_zip.py",
    "tools/build_v2r_review_zip.py",
    "tests/test_cost_stress.py",
    "tests/test_robustness_evidence.py",
    "tests/test_multiple_testing_adjustment.py",
    "tests/test_evidence_status.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_controller.py",
    "V2R-BACKUP_MANIFEST.json",
    ".cursor/hooks.json",
]


def main() -> None:
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
