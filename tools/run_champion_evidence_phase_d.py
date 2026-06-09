#!/usr/bin/env python3
"""Phase D — Champion governance charter and cockpit panel refresh."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_governance import (
    CHARTER_PATH,
    CRITERIA_PATH,
    build_champion_governance_de,
    load_champion_change_criteria,
)
from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_phase_d(root: Path) -> dict:
    root = Path(root)
    charter = root / CHARTER_PATH
    criteria = root / CRITERIA_PATH
    crit_doc, crit_st = load_champion_change_criteria(root)
    panel = build_champion_governance_de(root)
    conflicts = []
    if not charter.is_file():
        conflicts.append("D1_charter_missing")
    if crit_st != "OK":
        conflicts.append("D2_criteria_missing_or_invalid")
    if panel.get("canonical_comparison_status") != "OK":
        conflicts.append("D3_canonical_comparison_missing_run_phase_c_first")

    summary = {
        "schema_version": 1,
        "phase": "D",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE" if not conflicts else "PARTIAL",
        "steps": {
            "D1_charter": {"path": str(CHARTER_PATH), "present": charter.is_file()},
            "D2_criteria_yaml": {"path": str(CRITERIA_PATH), "status": crit_st},
            "D3_cockpit_panel": panel,
            "D4_governance_doc": "CHAMPION_CHALLENGER_GOVERNANCE.md",
        },
        "conflicts": conflicts,
        "authoritative_champion": crit_doc.get("authoritative_champion"),
    }
    atomic_write_json(root / "evidence" / "phase_d_governance_summary.json", summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase D champion governance")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(run_phase_d(Path(args.root)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
