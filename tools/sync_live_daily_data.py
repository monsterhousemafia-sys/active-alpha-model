#!/usr/bin/env python3
"""Sync live daily OHLCV for portfolio tickers and refresh model signal."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from aa_config_env import load_aa_env
    from aa_live_daily_sync import sync_live_daily_for_predictions

    parser = argparse.ArgumentParser(description="Live daily data sync for prediction refinement")
    parser.add_argument("--force-prices", action="store_true", help="Force OHLCV re-download")
    parser.add_argument("--no-signal", action="store_true", help="Skip signal/portfolio recompute")
    parser.add_argument("--full", action="store_true", help="Run full operational refinement chain")
    args = parser.parse_args()

    env = load_aa_env(ROOT)
    env["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0" if args.force_prices else env.get("AA_SKIP_DOWNLOAD_IF_CACHED", "1")

    if args.full:
        from aa_operational_refinement import load_refinement_config, run_operational_refinement

        cfg = load_refinement_config(ROOT)
        if args.force_prices:
            cfg["force_prices"] = True
        if args.no_signal:
            cfg["refresh_signal"] = False
        report = run_operational_refinement(ROOT, env, cfg=cfg, log_print=True)
        return 0 if report.ok else 1

    report = sync_live_daily_for_predictions(
        ROOT,
        env,
        force_prices=args.force_prices,
        refresh_signal=not args.no_signal,
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
