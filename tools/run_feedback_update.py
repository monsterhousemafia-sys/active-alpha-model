#!/usr/bin/env python3
"""Sync prediction outcome ledger and write feedback_report.txt."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_ops_refresh import resolve_out_dir  # noqa: E402
from aa_prediction_outcomes import update_prediction_outcomes  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Update prediction outcome ledger")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--out-dir", type=Path, default="")
    p.add_argument("--variant-id", default="")
    p.add_argument("--run-id", default="manual")
    p.add_argument("--horizon", type=int, default=10)
    args = p.parse_args()
    import os

    out_dir = Path(args.out_dir) if args.out_dir else resolve_out_dir(args.root, os.environ)
    summary = update_prediction_outcomes(
        out_dir,
        variant_id=args.variant_id,
        source_run_id=args.run_id,
        horizon=args.horizon,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
