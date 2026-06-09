#!/usr/bin/env python3
"""CLI: ensure predict is ready (auto-run if configured). Exit 0=ok, 3=blocked."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import argparse

    from analytics.prediction_operations import ensure_prediction_before_orders, orders_config

    parser = argparse.ArgumentParser(description="Ensure prediction readiness before orders")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--no-auto-run", action="store_true")
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--force-prices", action="store_true", help="Alias for --force-refresh")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    ocfg = orders_config(root)
    if not ocfg.get("require_prediction_ready", True):
        out = {"ok": True, "skipped": True}
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0
    auto = not args.no_auto_run and bool(
        ocfg.get("auto_run_predict_before_orders")
        or ocfg.get("auto_run_predict_on_scheduled_mark")
    )
    force = bool(args.force_refresh or args.force_prices)
    result = ensure_prediction_before_orders(
        root,
        auto_run=auto,
        force_refresh=force,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(result.get("message_de") or ("OK" if result.get("ok") else "BLOCKED"))
    if result.get("ok") or result.get("skipped"):
        return 0
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
