#!/usr/bin/env python3
"""Adaptive Marktanalyse — dynamic orchestration entry point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_adaptive_runtime import (
        load_adaptive_config,
        run_adaptive_loop,
        run_adaptive_marktanalyse,
        save_adaptive_config,
        DEFAULT_ADAPTIVE,
    )
    from aa_config_env import load_aa_env

    parser = argparse.ArgumentParser(description="Adaptive Marktanalyse runtime")
    parser.add_argument("--loop", action="store_true", help="Continuous adaptive loop")
    parser.add_argument("--no-retrain", action="store_true", help="Skip auto exemplar retrain")
    parser.add_argument("--init-config", action="store_true", help="Write control/adaptive_runtime.json")
    parser.add_argument("--fictive", action="store_true", help="Force fictive price data")
    parser.add_argument("--internet", action="store_true", help="Force internet price data")
    args = parser.parse_args()

    if args.init_config:
        path = save_adaptive_config(ROOT, DEFAULT_ADAPTIVE)
        print(f"Config: {path}")
        return 0

    env = load_aa_env(ROOT)
    if args.fictive:
        env["AA_PRICE_DATA_SOURCE"] = "fictive"
    elif args.internet:
        env["AA_PRICE_DATA_SOURCE"] = "internet"
    else:
        env.setdefault("AA_PRICE_DATA_SOURCE", "auto")

    if args.loop:
        run_adaptive_loop(ROOT)
        return 0

    report = run_adaptive_marktanalyse(ROOT, env, log_print=True, allow_retrain=not args.no_retrain)
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
