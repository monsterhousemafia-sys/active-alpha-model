#!/usr/bin/env python3
"""Build G0 authorization conflict remediation review ZIP."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import RELOCATED, doc_path, doc_rel

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ZIP = ROOT / "codex_g0_authorization_conflict_remediation_review.zip"
OUT_SHA = doc_path("codex_g0_authorization_conflict_remediation_review.zip.sha256")

INCLUDE = [
    "CODEX_G0_PREFLIGHT.md",
    "CONTROL_AUTHORIZATION_CONFLICT_REPORT.md",
    "CODEX_G0_GIT_STATUS.txt",
    "CODEX_G0_PROTECTED_HASHES_BEFORE.json",
    "CODEX_G0_PROTECTED_HASHES_AFTER.json",
    "CODEX_G0_TEST_OUTPUT.txt",
    "EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md",
    "NEXT_CURSOR_PROMPT.md",
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "IMPLEMENTATION_STATUS.md",
    "VISION_PROGRESS.json",
    "aa_authorization_policy.py",
    "aa_decision_cockpit_viewmodel.py",
    "aa_decision_cockpit_gui.py",
    "aa_decision_cockpit_readonly_snapshot.py",
    "control/authorization/authorization_source_policy.json",
    "control/authorization/current_authorization_status.json",
    "control/operational_safety_flags.json",
    "control/champion_lineage_policy.json",
    "control/CHAMPION_LINEAGE.md",
    "control/evidence/governance_drift_reconciliation.json",
    "control/vision_automation/phase_catalog.json",
    "control/vision_automation/review_registry/review_registry.json",
    "tests/test_authorization_conflict_fail_closed.py",
    "tests/cockpit_governance_fixtures.py",
    "control/review_snapshot/v5r_decision_cockpit_snapshot.json",
]


def _resolve(rel: str) -> Path:
    if rel in RELOCATED:
        return doc_path(rel)
    return ROOT / rel


def main() -> int:
    if OUT_ZIP.is_file():
        OUT_ZIP.unlink()
    incidents = sorted((ROOT / "control" / "incidents").glob("authorization_source_conflict_*.json"))
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = _resolve(rel)
            if path.is_file():
                zf.write(path, rel)
        for path in incidents:
            zf.write(path, str(path.relative_to(ROOT)).replace("\\", "/"))
    digest = hashlib.sha256(OUT_ZIP.read_bytes()).hexdigest()
    OUT_SHA.parent.mkdir(parents=True, exist_ok=True)
    OUT_SHA.write_text(f"{digest}  {OUT_ZIP.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(OUT_ZIP), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
