#!/usr/bin/env python3
"""Reconcile champion/evidence documentation drift (read-only exports, no operative jobs)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa_cost_stress import export_cost_stress_status
from aa_decision_cockpit_readonly_snapshot import refresh_live_review_snapshot
from aa_evidence_schema import LOCKED_CHAMPION, PREVIOUS_CHAMPION, resolve_locked_champion
from aa_multiple_testing_adjustment import export_multiple_testing_status
from aa_robustness_evidence import export_robustness_status
from aa_safe_io import atomic_write_json
from tools.prepare_g1_challenger_cost_evidence import prepare_g1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _refresh_champion_lineage_policy(root: Path) -> Path:
    from analytics.strategic_governance import sync_strategic_governance

    result = sync_strategic_governance(root)
    return root / "control" / "champion_lineage_policy.json"


def main() -> int:
    root = ROOT
    champion = resolve_locked_champion(root)
    cost_path = export_cost_stress_status(root)
    robust_path = export_robustness_status(root)
    mt_path = export_multiple_testing_status(root)
    g1 = prepare_g1(root)
    policy_path = _refresh_champion_lineage_policy(root)
    snap_path = refresh_live_review_snapshot(root)

    cost = json.loads(cost_path.read_text(encoding="utf-8"))
    summary = {
        "champion_resolved": champion,
        "cost_stress_gate_pass": (cost.get("COST_STRESS_GATE") or {}).get("pass"),
        "cost_stress_blockers": (cost.get("COST_STRESS_GATE") or {}).get("blockers"),
        "operational_user_override_removed": "operational_user_override" not in cost,
        "g1_blockers": g1.get("status", {}).get("blockers") if isinstance(g1.get("status"), dict) else g1.get("blockers"),
        "artifacts": {
            "cost_stress_status": str(cost_path.relative_to(root)),
            "robustness_status": str(robust_path.relative_to(root)),
            "multiple_testing_status": str(mt_path.relative_to(root)),
            "champion_lineage_policy": str(policy_path.relative_to(root)),
            "review_snapshot": str(snap_path.relative_to(root)),
        },
    }
    out = root / "control" / "evidence" / "governance_drift_reconciliation.json"
    atomic_write_json(out, {"schema_version": 1, "generated_at_utc": _utc_now(), **summary})
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
