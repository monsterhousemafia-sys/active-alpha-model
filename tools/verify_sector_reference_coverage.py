"""CLI: Champion-14 sector coverage + optional rollout evidence (S6/S7)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_REL = "evidence/sector_reference_rollout_summary.json"


def main() -> int:
    from aa_safe_io import atomic_write_json
    from aa_sector_reference import build_sector_rollout_summary, champion_sector_coverage
    from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

    p = argparse.ArgumentParser(description="Verify sector reference coverage (Champion-14).")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument(
        "--write-evidence",
        action="store_true",
        help=f"Write {EVIDENCE_REL} (read-only audit, no network refresh).",
    )
    p.add_argument("--json", action="store_true", help="Print full report JSON to stdout.")
    args = p.parse_args()
    root = args.root.resolve()

    summary = build_sector_rollout_summary(root)
    cov = summary.get("champion_coverage") or champion_sector_coverage(root, CHAMPION_SYMBOLS)

    if args.write_evidence:
        out_path = atomic_write_json(root / EVIDENCE_REL, summary)
        print(f"Evidence: {out_path}")

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        mapped = cov.get("mapped_count", 0)
        total = cov.get("symbol_count", 0)
        unknown = cov.get("unknown_tickers") or []
        snap = summary.get("sp500_latest_snapshot") or {}
        print(
            f"Champion coverage: {mapped}/{total} "
            f"unknown={unknown if unknown else 'none'}"
        )
        print(
            f"sector_reference.csv: {'yes' if summary.get('reference_file_exists') else 'no'} "
            f"({summary.get('reference_path', '')})"
        )
        print(
            f"sp500_latest sector_gics: "
            f"{'yes' if snap.get('has_sector_gics') else 'no'} "
            f"({snap.get('path') or 'missing'})"
        )
        print(f"rollout_status: {summary.get('rollout_status', '—')}")

    ok = bool(cov.get("ok"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
