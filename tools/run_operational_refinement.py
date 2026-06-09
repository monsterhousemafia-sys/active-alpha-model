#!/usr/bin/env python3
"""Full operational refinement chain — maximize live prediction capacity."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_config_env import load_aa_env
    from aa_operational_refinement import (
        load_refinement_config,
        run_operational_refinement,
        run_operational_refinement_loop,
        save_refinement_config,
    )

    parser = argparse.ArgumentParser(description="Operational refinement orchestrator")
    parser.add_argument("--force-prices", action="store_true", help="Force OHLCV re-download")
    parser.add_argument("--no-signal", action="store_true", help="Skip signal refresh")
    parser.add_argument("--no-cockpit", action="store_true", help="Skip cockpit snapshot")
    parser.add_argument("--background-research", action="store_true", help="Run background research")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--interval", type=int, default=300, help="Loop interval seconds")
    parser.add_argument("--init-config", action="store_true", help="Write default control/operational_refinement.json")
    args = parser.parse_args()

    if args.init_config:
        from aa_operational_refinement import DEFAULT_REFINEMENT

        path = save_refinement_config(ROOT, DEFAULT_REFINEMENT)
        print(f"Config written: {path}")
        return 0

    cfg = load_refinement_config(ROOT)
    if args.force_prices:
        cfg["force_prices"] = True
    if args.no_signal:
        cfg["refresh_signal"] = False
    if args.no_cockpit:
        cfg["refresh_cockpit_snapshot"] = False
    if args.background_research:
        cfg["run_background_research"] = True

    env = load_aa_env(ROOT)

    if args.loop:
        run_operational_refinement_loop(ROOT, interval_seconds=args.interval)
        return 0

    report = run_operational_refinement(ROOT, env, cfg=cfg, log_print=True)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
