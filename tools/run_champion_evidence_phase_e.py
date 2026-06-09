#!/usr/bin/env python3
"""Phase E — Strategic champion decision (default: retain R3, no auto-switch)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_strategic_decision import apply_strategic_decision, evaluate_strategic_options
from aa_safe_io import atomic_write_json


def run_phase_e(root: Path, *, allow_champion_change: bool = False) -> dict:
    root = Path(root)
    decision = evaluate_strategic_options(root)
    apply_result = apply_strategic_decision(root, decision, allow_champion_change=allow_champion_change)
    decision["apply_result"] = apply_result
    decision["e1_operational_applied"] = bool(apply_result.get("applied")) and apply_result.get("option") == "E1_RETAIN_R3"
    conflicts = list(apply_result.get("conflicts") or [])
    decision["status"] = "COMPLETE" if not conflicts else "COMPLETE_WITH_WARNINGS"

    atomic_write_json(root / "control" / "champion_strategic_decision.json", decision)
    summary = {
        "schema_version": 1,
        "phase": "E",
        "generated_at_utc": decision.get("generated_at_utc"),
        "status": decision["status"],
        "selected_option": decision.get("selected_option"),
        "champion_variant_after_decision": decision.get("champion_variant_after_decision"),
        "champion_change_executed": decision.get("champion_change_executed"),
        "e1_operational_applied": decision.get("e1_operational_applied"),
        "decision_summary_de": decision.get("decision_summary_de"),
        "apply_result": apply_result,
        "conflicts": conflicts,
    }
    atomic_write_json(root / "evidence" / "phase_e_strategic_decision_summary.json", summary)
    return decision


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase E strategic champion decision")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument(
        "--allow-champion-change",
        action="store_true",
        help="Only applies if all switch gates pass AND external approval exists (default: retain R3)",
    )
    args = parser.parse_args()
    print(json.dumps(run_phase_e(Path(args.root), allow_champion_change=args.allow_champion_change), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
