#!/usr/bin/env python3
"""Phase G — Live operations hardening (G1–G6)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_champion_evidence_phase_g import run_phase_g


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase G live operations evidence pipeline")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--skip-pytest", action="store_true", help="Skip Phase-5 pytest suite in G6")
    parser.add_argument("--build-exe", action="store_true", help="Rebuild Marktanalyse.exe before G5/G6 verify")
    args = parser.parse_args()
    summary = run_phase_g(Path(args.root), skip_pytest=args.skip_pytest, build_exe=args.build_exe)
    print(json.dumps(summary, indent=2, ensure_ascii=True))
    ok = bool(summary.get("overall_pass"))
    print(f"\nPhase G — {'PASS' if ok else 'FAIL'}")
    print(f"  evidence: evidence/phase_g_live_operations_summary.json")
    print(f"  matrix:   evidence/phase_g_live_operations_gate_matrix.md")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
