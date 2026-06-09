"""Build V1R review ZIP with external sidecar hash (no self-hash inside ZIP)."""
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
ZIP_NAME = "codex_v1r_evidence_controller_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V1R.md",
    "AGENTS.md",
    "VISION_PROGRESS.json",
    doc_rel("CODEX_V1R_PREFLIGHT.md"),
    doc_rel("CODEX_V1R_GIT_STATUS.txt"),
    doc_rel("CODEX_V1R_EVIDENCE_CONTROLLER_REPORT.md"),
    doc_rel("CODEX_V1R_TEST_OUTPUT.txt"),
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "control/system_health.json",
    "control/last_known_good_state.json",
    "DEVELOPMENT_PIPELINE.json",
    "DEVELOPMENT_PIPELINE.yaml",
    "aa_evidence_schema.py",
    "aa_experiment_registry.py",
    "aa_evidence_status.py",
    "aa_vision_phase_catalog.py",
    "aa_vision_review_gate.py",
    "aa_vision_controller.py",
    "control/evidence/current_evidence_status.json",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    ".cursor/hooks.json",
    "tests/test_evidence_status.py",
    "tests/test_experiment_registry.py",
    "tests/test_vision_review_gate.py",
    "tests/test_vision_controller.py",
    "tests/test_evidence_schema.py",
    "tests/test_vision_phase_catalog.py",
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
        p9 = ROOT / "control" / "p9_shadow_paper_prep_status.json"
        if p9.is_file():
            zf.write(p9, "control/p9_shadow_paper_prep_status.json")
        backup_root = ROOT / "control" / "repair_backups"
        if backup_root.is_dir():
            manifests = sorted(backup_root.glob("*_V1R/BACKUP_MANIFEST.json"))
            if manifests:
                latest = manifests[-1]
                zf.write(latest, latest.relative_to(ROOT).as_posix())

    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    sidecar = ROOT / f"{ZIP_NAME}.sha256"
    sidecar.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
