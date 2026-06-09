#!/usr/bin/env python3
"""Build G1 external review submission ZIP (B — awaiting approval, not approved)."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from aa_doc_paths import RELOCATED, doc_path

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_ZIP = ROOT / "codex_g1_readonly_challenger_cost_evidence_submission.zip"
OUT_SHA = doc_path("codex_g1_readonly_challenger_cost_evidence_submission.zip.sha256")

INCLUDE = [
    "CODEX_G1_PREFLIGHT.md",
    "CODEX_G1_EXTERNAL_REVIEW_SUBMISSION.md",
    "G1_EXTERNAL_REVIEW_STATUS.md",
    "G1_COMPARISON_LOGIC.md",
    "EXTERNAL_REVIEW_APPROVAL_G1_TEMPLATE.md",
    "control/evidence/g1_challenger_cost_preparation_status.json",
    "control/evidence/g1_source_inventory.json",
    "control/authorization/current_authorization_status.json",
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    "control/experiments/EXP_INITIAL_MOM_63_TOP12.yaml",
]


def _resolve(rel: str) -> Path:
    if rel in RELOCATED:
        return doc_path(rel)
    return ROOT / rel


def main() -> int:
    if OUT_ZIP.is_file():
        OUT_ZIP.unlink()
    with zipfile.ZipFile(OUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = _resolve(rel)
            if path.is_file():
                zf.write(path, rel)
    digest = hashlib.sha256(OUT_ZIP.read_bytes()).hexdigest()
    OUT_SHA.parent.mkdir(parents=True, exist_ok=True)
    OUT_SHA.write_text(f"{digest}  {OUT_ZIP.name}\n", encoding="utf-8")
    print(json.dumps({"zip": str(OUT_ZIP), "sha256": digest, "status": "AWAITING_EXTERNAL_REVIEW"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
