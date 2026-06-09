#!/usr/bin/env python3
"""Register pending G0/G1 review rows in review_registry (external_sealed: false)."""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json
REGISTRY = ROOT / "control" / "vision_automation" / "review_registry" / "review_registry.json"

PENDING = (
    {
        "phase_id": "G0_AUTHORIZATION_SOURCE_CONFLICT_REMEDIATION",
        "phase_key": "G0",
        "approval_file": "EXTERNAL_REVIEW_APPROVAL_G0_AUTHORIZATION_SOURCE_CONFLICT_REMEDIATION.md",
        "review_zip": "codex_g0_authorization_conflict_remediation_review.zip",
    },
    {
        "phase_id": "G1_READ_ONLY_CHALLENGER_COST_EVIDENCE_PREPARATION",
        "phase_key": "G1",
        "approval_file": "EXTERNAL_REVIEW_APPROVAL_G1_READ_ONLY_CHALLENGER_COST_EVIDENCE.md",
        "review_zip": "codex_g1_readonly_challenger_cost_evidence_submission.zip",
    },
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _zip_sha256(name: str) -> str:
    path = ROOT / name
    if not path.is_file():
        return "PENDING_EXTERNAL_SEAL"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reviews = list(registry.get("reviews") or [])
    existing = {str(r.get("phase_id") or "") for r in reviews if isinstance(r, dict)}

    added = []
    updated = []
    for spec in PENDING:
        sha = _zip_sha256(spec["review_zip"])
        if spec["phase_id"] in existing:
            for row in reviews:
                if not isinstance(row, dict):
                    continue
                if row.get("phase_id") != spec["phase_id"]:
                    continue
                if sha != "PENDING_EXTERNAL_SEAL" and row.get("review_zip_sha256") != sha:
                    row["review_zip_sha256"] = sha
                    updated.append(spec["phase_id"])
            continue
        reviews.append(
            {
                "approval_file": spec["approval_file"],
                "approval_sha256": "PENDING_EXTERNAL_SEAL",
                "blockers": [],
                "champion_changed": False,
                "completed_at_utc": _utc_now(),
                "exe_built": False,
                "exe_executed": False,
                "execution_status": "AWAITING_EXTERNAL_REVIEW",
                "external_sealed": False,
                "operative_jobs_executed": False,
                "phase_id": spec["phase_id"],
                "phase_key": spec["phase_key"],
                "promotion_executed": False,
                "real_money_executed": False,
                "review_zip": spec["review_zip"],
                "review_zip_sha256": _zip_sha256(spec["review_zip"]),
            }
        )
        added.append(spec["phase_id"])

    registry["reviews"] = reviews
    atomic_write_json(REGISTRY, registry)
    print(json.dumps({"added": added, "updated_sha256": updated, "registry": str(REGISTRY)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
