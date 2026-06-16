#!/usr/bin/env python3
"""Full system update — governance, refinement, Stufe B, self-calibration."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_config_env import load_aa_env
    from analytics.system_update import run_system_update

    parser = argparse.ArgumentParser(description="System update orchestrator")
    parser.add_argument("--force-prices", action="store_true", help="Force OHLCV re-download")
    parser.add_argument("--no-signal", action="store_true", help="Skip signal refresh in refinement")
    args = parser.parse_args()

    env = load_aa_env(ROOT)
    doc = run_system_update(
        ROOT,
        env,
        force_prices=args.force_prices,
        refresh_signal=not args.no_signal,
        persist=True,
        log_print=True,
    )
    return 0 if doc.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
