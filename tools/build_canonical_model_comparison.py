#!/usr/bin/env python3
"""Phase C — Build canonical aligned model comparison evidence."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_canonical_comparison import build_canonical_model_comparison, format_canonical_comparison_md
from aa_safe_io import atomic_write_json, atomic_write_text

EVIDENCE_JSON = "evidence/canonical_model_comparison.json"
EVIDENCE_MD = "evidence/canonical_model_comparison.md"
SUMMARY_JSON = "evidence/phase_c_canonical_comparison_summary.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canonical model comparison (Phase C)")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = Path(args.root).resolve()

    doc = build_canonical_model_comparison(root)
    md = format_canonical_comparison_md(doc)

    atomic_write_json(root / EVIDENCE_JSON, doc)
    atomic_write_text(root / EVIDENCE_MD, md)
    summary = {
        "schema_version": 1,
        "phase": "C",
        "generated_at_utc": doc.get("generated_at_utc"),
        "status": "COMPLETE",
        "alignment_mode": doc.get("alignment_mode"),
        "matrix_embedded_sharpe_leader": (doc.get("headline") or {}).get("matrix_embedded_sharpe_leader"),
        "aligned_intersection_sharpe_leader": (doc.get("headline") or {}).get("aligned_intersection_sharpe_leader"),
        "champion_sharpe_rank_matrix": (doc.get("headline") or {}).get("champion_sharpe_rank_matrix"),
        "outputs": [EVIDENCE_JSON, EVIDENCE_MD],
        "governance_blockers": doc.get("governance_blockers"),
    }
    atomic_write_json(root / SUMMARY_JSON, summary)

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
