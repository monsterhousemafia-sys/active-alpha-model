#!/usr/bin/env python3
"""Weekly learning audit + safe evolution auto-apply (Sportwagen -> Rennwagen)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from analytics.evolution_stage_runner import run_evolution_cycle

    parser = argparse.ArgumentParser(description="Learning cycle audit + evolution")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--apply-safe", action="store_true", help="Apply Zone A/B auto improvements")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)

    cycle = run_evolution_cycle(root, apply_improvements=args.apply_safe)
    out: dict = {"evolution_cycle": cycle, "audit": cycle.get("stage")}
    if args.apply_safe:
        out["auto_apply"] = cycle.get("auto_apply")

    try:
        from tools.build_competition_readiness import build_competition_readiness
        from aa_safe_io import atomic_write_json

        readiness = build_competition_readiness(root)
        atomic_write_json(root / "evidence/competition_readiness_latest.json", readiness)
        out["competition_readiness"] = readiness
    except Exception:
        pass

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(cycle.get("message_de", ""))
        if args.apply_safe:
            print((out.get("auto_apply") or {}).get("message_de", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
