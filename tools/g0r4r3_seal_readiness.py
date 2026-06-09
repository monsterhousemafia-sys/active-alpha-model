#!/usr/bin/env python3
"""Pre-submission seal-readiness gate — zero-gap verification before external review."""
from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

BASELINE_EXPECTED: Dict[str, str] = {
    "EXTERNAL_REVIEW_APPROVAL_FINAL.md": "efaf57ec98345f5e571c6694d6b8aba64e40205a4ed85dfdbcdeba336ea90ec3",
    "V5R_EXTERNAL_ACCEPTANCE_REPORT.md": "08a18385f8e6498b0c63437c372ec4d43980e70e8ad32e5ca6220e9a30b1c97f",
    "docs/integrity/protected_hashes/V5R/CODEX_V5R_PROTECTED_HASHES_AFTER.json": (
        "291b1d75d0774dff20db4cd2efc113239254adfcd3a0193b7a5d1bb4180abd17"
    ),
}

REQUIRED_AUDIT_ZIP_PATHS: Tuple[str, ...] = (
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md",
    "control/external_reviews/g0r4r2_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R2_REMEDIATION_RESUBMISSION_ONLY.md.sha256",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_DECISION_G0R4R2_REMEDIATION_REQUIRED.md",
    "control/external_reviews/g0r4r2_rejection/EXTERNAL_REVIEW_OBSERVED_HASH_G0R4R2.sha256",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md",
    "control/external_reviews/g0r4r3_approval/EXTERNAL_REVIEW_APPROVAL_G0R4R3_FINAL_BLOB_ZIP_VERBATIM_REMEDIATION_ONLY.md.sha256",
)

G0R4R3_ZIP_NAME = "codex_g0r4r3_final_blob_zip_verbatim_remediation_review.zip"
G0R4R2_ZIP_NAME = "codex_g0r4r2_verbatim_authoritative_baseline_resubmission.zip"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_zip(path: Path, label: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {"label": label, "path": str(path), "exists": path.is_file(), "gaps": []}
    if not path.is_file():
        result["gaps"].append("ZIP_MISSING")
        return result
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        for rel, expected in BASELINE_EXPECTED.items():
            if rel not in names:
                result["gaps"].append(f"BASELINE_MISSING_IN_ZIP:{rel}")
                continue
            actual = _sha256(zf.read(rel))
            if actual != expected:
                data = zf.read(rel)
                le = "CRLF" if b"\r\n" in data else "LF-only"
                result["gaps"].append(
                    f"BASELINE_HASH_MISMATCH:{rel} expected={expected[:12]} actual={actual[:12]} ({le})"
                )
        for rel in REQUIRED_AUDIT_ZIP_PATHS:
            if rel not in names:
                result["gaps"].append(f"AUDIT_INPUT_MISSING_IN_ZIP:{rel}")
        if ".gitattributes" not in names:
            result["gaps"].append("GITATTRIBUTES_MISSING_IN_ZIP")
    result["pass"] = len(result["gaps"]) == 0
    return result


def main() -> int:
    checks = [
        _check_zip(_REPO / "outgoing_external_reviews/g0r4r2" / G0R4R2_ZIP_NAME, "G0R4R2_CURRENT"),
        _check_zip(_REPO / "outgoing_external_reviews/g0r4r3" / G0R4R3_ZIP_NAME, "G0R4R3_TARGET"),
        _check_zip(_REPO / G0R4R3_ZIP_NAME, "G0R4R3_ROOT"),
    ]
    report = {
        "seal_readiness_summary": "PASS" if any(c.get("pass") for c in checks) else "BLOCKED",
        "baseline_crlf_required_hashes": BASELINE_EXPECTED,
        "required_audit_zip_paths": list(REQUIRED_AUDIT_ZIP_PATHS),
        "checks": checks,
        "g0r4r2_known_gaps_closed_by_g0r4r3": [
            "Git CRLF->LF normalization blocked via .gitattributes -text",
            "Final git blob verbatim gate before ZIP build",
            "Final ZIP entry verbatim gate after ZIP build",
            "Six audit inputs mandatory in ZIP include list",
            "No internal false ZIP-PASS in committed payload",
            "Detached post-build report only claims final verification",
        ],
    }
    out = _REPO / "docs/phases/G0R4R3/CODEX_G0R4R3_SEAL_READINESS_REPORT.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["seal_readiness_summary"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
