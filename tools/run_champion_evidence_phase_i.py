#!/usr/bin/env python3
"""Phase I — External review submission (ZIP, docs, registry, progress)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_evidence_phase_i import run_phase_i


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase I champion evidence external review submission")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    summary = run_phase_i(Path(args.root))
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"\nPhase I — {summary['status']}")
    print(f"  ZIP: {summary['review_zip']}")
    print(f"  SHA256: {summary['review_zip_sha256']}")
    print(f"  Champion unchanged: {summary['authoritative_champion']}")
    ok_status = summary.get("status") == "AWAITING_EXTERNAL_REVIEW"
    return 0 if ok_status and not summary.get("conflicts") else (0 if ok_status else 1)


if __name__ == "__main__":
    raise SystemExit(main())
