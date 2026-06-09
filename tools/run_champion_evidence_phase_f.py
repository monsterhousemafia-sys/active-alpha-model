#!/usr/bin/env python3
"""Phase F — Statistical gate evidence (DSR, robustness, cost stress matrix)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_evidence_phase_f import run_phase_f


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase F statistical evidence pipeline")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(json.dumps(run_phase_f(Path(args.root)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
