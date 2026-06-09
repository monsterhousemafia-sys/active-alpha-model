#!/usr/bin/env python3
"""Build codex_champion_evidence_remediation_review.zip (Phase I artefact)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_evidence_phase_i import build_review_zip


def main() -> int:
    info = build_review_zip(ROOT)
    print(f"Wrote {info.get('zip_path')} sha256={info.get('sha256')}")
    missing = info.get("missing") or []
    if missing:
        print(f"WARNING: {len(missing)} missing paths")
        for m in missing[:20]:
            print(f"  - {m}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
