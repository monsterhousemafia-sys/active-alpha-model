#!/usr/bin/env python3
"""Run development pipeline without manual intervention (--once or --loop)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

from aa_pipeline_autopilot import load_autopilot_config, run_autopilot_once  # noqa: E402
from aa_pipeline_orchestration import load_pending, loop_may_continue  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(description="Active Alpha development autopilot")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--once", action="store_true", help="Single tick (default)")
    p.add_argument("--loop", action="store_true", help="Repeat while phase work pending or local loop enabled")
    p.add_argument("--interval", type=int, default=0, help="Seconds between loop ticks")
    p.add_argument("--quiet", action="store_true")
    args = p.parse_args()

    root = Path(args.root)
    cfg = load_autopilot_config(root)
    interval = int(args.interval or cfg.get("loop_interval_seconds", 300) or 300)

    tick_timeout = int(cfg.get("tick_timeout_seconds", 900) or 900)

    def _tick() -> int:
        report = run_autopilot_once(root, cfg=cfg)
        if not args.quiet:
            print(json.dumps(report.to_dict(), indent=2, default=str))
        pending = load_pending(root)
        phase_pending = bool(pending.get("has_work")) and str(pending.get("pending_phase", ""))
        if phase_pending:
            return 2
        fails = sum(1 for s in report.steps if s.get("status") == "FAIL")
        return 1 if fails else 0

    def _tick_bounded() -> int:
        with ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_tick)
            try:
                return int(fut.result(timeout=max(120, tick_timeout)))
            except FuturesTimeout:
                if not args.quiet:
                    print(
                        f"[autopilot] tick timeout after {tick_timeout}s — continuing loop",
                        flush=True,
                    )
                return 1

    if not args.loop:
        return _tick_bounded()

    while True:
        rc = _tick_bounded()
        cfg = load_autopilot_config(root)
        may_continue, reason = loop_may_continue(root)
        if not cfg.get("local_loop_enabled", True) and not may_continue:
            if not args.quiet:
                print(f"[autopilot] stop: {reason}", flush=True)
            return rc
        if not args.quiet:
            print(f"[autopilot] sleep {interval}s ({reason or 'maintenance'}) …", flush=True)
        time.sleep(max(30, interval))


if __name__ == "__main__":
    raise SystemExit(main())
