#!/usr/bin/env python3
"""M2.5 — risk-off episode attribution for R0 vs R3 (research evidence)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json


def main() -> int:
    """Placeholder metrics until full episode engine wired; writes manifest for M2 seal."""
    out = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "phase": "M2.5",
        "status": "PLACEHOLDER",
        "note": "Run full episode engine when risk_off flags available in returns CSV.",
        "variants": ["R0_LEGACY_ENSEMBLE", "R3_w075_q065_noexit"],
    }
    atomic_write_json(ROOT / "evidence" / "r0_migration" / "risk_off_episode_attribution.csv.json", out)
    atomic_write_json(ROOT / "research_evidence" / "risk_off_episode_attribution.csv.json", out)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
