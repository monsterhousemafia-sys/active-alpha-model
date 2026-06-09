#!/usr/bin/env python3
"""Sync strategic governance manifest and derived control artifacts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from analytics.strategic_governance import sync_strategic_governance
    from tools.build_competition_readiness import build_competition_readiness

    from aa_safe_io import atomic_write_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    result = sync_strategic_governance(root)
    readiness = build_competition_readiness(root)
    atomic_write_json(root / "evidence/competition_readiness_latest.json", readiness)
    result["competition_readiness_regenerated"] = True
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"Governance sync OK — {result.get('governance_champion')} | "
            f"Signal {result.get('active_signal_variant')} | "
            f"Orders-Profil {result.get('effective_orders_profile')}"
        )
        if not result.get("coherence_ok"):
            print("Coherence issues:", result.get("coherence_issues"))
    return 0 if result.get("coherence_ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
