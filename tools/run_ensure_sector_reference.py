"""CLI: refresh sector reference (universe if stale + yfinance fallback)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_config_env import load_aa_env
    from aa_sector_reference import ensure_sector_reference_fresh

    p = argparse.ArgumentParser(description="Ensure sector_reference.csv is fresh.")
    p.add_argument("--root", type=Path, default=ROOT)
    args = p.parse_args()
    root = args.root.resolve()
    env = load_aa_env(root)
    result = ensure_sector_reference_fresh(root, env)
    print(result.get("message_de", ""))
    if result.get("universe_logs"):
        for line in result["universe_logs"]:
            print(line)
    cov = result.get("champion_coverage") or {}
    if cov:
        print(
            f"Champion coverage: {cov.get('mapped_count')}/{cov.get('symbol_count')} "
            f"unknown={cov.get('unknown_tickers')}"
        )
    return 0 if cov.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
