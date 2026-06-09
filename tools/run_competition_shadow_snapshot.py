#!/usr/bin/env python3
"""CLI: model vs mom_1_top12 vs live orders shadow snapshot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from analytics.competition_shadow import write_competition_shadow_snapshot

    parser = argparse.ArgumentParser(description="Competition shadow snapshot")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    doc = write_competition_shadow_snapshot(Path(args.root))
    if args.json:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(doc.get("message_de", "OK"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
