#!/usr/bin/env python3
"""Headless learning catch-up — EOD closes + broker snapshot without GUI."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def main() -> int:
    import argparse
    from datetime import datetime, timezone

    p = argparse.ArgumentParser(description="Daily learning ledger catch-up (no GUI)")
    p.add_argument("--root", type=Path, default=ROOT)
    p.add_argument("--force-eod", action="store_true")
    args = p.parse_args()
    root = Path(args.root)

    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout
    from market.learning_pipeline import run_learning_capture_cycle

    ensure_marktanalyse_runtime_layout(root)
    broker = {"credentials_configured": False}
    try:
        from integrations.trading212.t212_readonly_connection_service import connection_status_summary

        status = connection_status_summary(root, force_sync=False)
        broker = status.to_dict()
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("broker status unavailable for EOD catch-up", exc_info=True)

    out = run_learning_capture_cycle(root, live_snapshot=None, broker=broker, cash={}, force_eod=args.force_eod)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "eod": out.get("eod"),
        "broker_daily": out.get("broker_daily"),
        "readiness": out.get("readiness"),
    }
    dest = root / "evidence" / "learning_eod_catchup_latest.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    readiness = out.get("readiness") or {}
    if readiness.get("capture_errors"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
