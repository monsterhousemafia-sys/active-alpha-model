"""Build V1R2 review ZIP with external sidecar."""
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
ZIP_NAME = "codex_v1r2_review_chain_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V1R2.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V1R2_PREFLIGHT.md"),
    doc_rel("CODEX_V1R2_GIT_STATUS.txt"),
    doc_rel("CODEX_V1R2_REVIEW_CHAIN_REPORT.md"),
    doc_rel("CODEX_V1R2_TEST_OUTPUT.txt"),
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "control/system_health.json",
    "control/last_known_good_state.json",
    "control/p9_shadow_paper_prep_status.json",
    "control/evidence/current_evidence_status.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
    "model_output_sp500_pit_t212/background_research_status.json",
    "aa_evidence_schema.py",
    "aa_experiment_registry.py",
    "aa_evidence_status.py",
    "aa_vision_phase_catalog.py",
    "aa_vision_review_gate.py",
    "aa_vision_controller.py",
    "tests/test_evidence_status.py",
    "tests/test_experiment_registry.py",
    "tests/test_vision_review_gate.py",
    "tests/test_vision_controller.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_evidence_schema.py",
    ".cursor/hooks.json",
]


def main() -> None:
    zip_path = ROOT / ZIP_NAME
    if zip_path.is_file():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            p = ROOT / rel
            if p.is_file():
                zf.write(p, rel.replace("\\", "/"))
        backup_root = ROOT / "control" / "repair_backups"
        if backup_root.is_dir():
            manifests = sorted(backup_root.glob("*_V1R2/BACKUP_MANIFEST.json"))
            if manifests:
                zf.write(manifests[-1], manifests[-1].relative_to(ROOT).as_posix())

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = ROOT / f"{ZIP_NAME}.sha256"
    sidecar.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
