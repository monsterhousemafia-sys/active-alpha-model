"""Build codex_v1 review ZIP and update registry with SHA256."""

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

ROOT = Path(__file__).resolve().parent.parent
ZIP_NAME = "codex_v1_evidence_and_cascade_review.zip"

INCLUDE = [
    "EXTERNAL_REVIEW_APPROVAL_V1.md",
    "AGENTS.md",
    "VISION_DECISION_COCKPIT_EXECPLAN.md",
    "VISION_PROGRESS.json",
    "CODEX_V1_PREFLIGHT.md",
    "CODEX_V1_GIT_STATUS.txt",
    "CODEX_V1_EVIDENCE_AND_CASCADE_REPORT.md",
    "CODEX_V1_TEST_OUTPUT.txt",
    "P9_EXTERNAL_REVIEW_STATUS.md",
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
    "control/vision_automation/automation_state.json",
    "control/vision_automation/cascade_policy.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    ".cursor/hooks.json",
    "tests/test_evidence_schema.py",
    "tests/test_experiment_registry.py",
    "tests/test_evidence_status.py",
    "tests/test_vision_phase_catalog.py",
    "tests/test_vision_review_gate.py",
    "tests/test_vision_controller.py",
    "CODEX_V1_REVIEW_ZIP_SHA256.txt",
]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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

        exp_dir = ROOT / "control" / "experiments"
        if exp_dir.is_dir():
            for f in exp_dir.glob("*"):
                if f.is_file():
                    zf.write(f, f"control/experiments/{f.name}")

        tpl = ROOT / "control" / "vision_automation" / "templates"
        if tpl.is_dir():
            for f in tpl.glob("*"):
                if f.is_file():
                    zf.write(f, f"control/vision_automation/templates/{f.name}")

        tasks = ROOT / "control" / "vision_automation" / "authorized_tasks"
        if tasks.is_dir():
            for f in tasks.glob("TEMPLATE_TASK_*.md"):
                zf.write(f, f"control/vision_automation/authorized_tasks/{f.name}")

        backup_root = ROOT / "control" / "repair_backups"
        if backup_root.is_dir():
            manifests = sorted(backup_root.glob("*_V1/BACKUP_MANIFEST.json"))
            if manifests:
                latest = manifests[-1]
                zf.write(latest, latest.relative_to(ROOT).as_posix())

    digest = sha256_bytes(zip_path.read_bytes())
    (doc_path("CODEX_V1_REVIEW_ZIP_SHA256.txt")).write_text(digest + "\n", encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
