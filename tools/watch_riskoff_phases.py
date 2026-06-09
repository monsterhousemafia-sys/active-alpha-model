#!/usr/bin/env python3
"""Poll risk-off research dirs and emit phase-completion events."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from run_active_alpha_riskoff_experiments import EXPERIMENTS, RESEARCH_ROOT  # noqa: E402

STATUS_FILE = RESEARCH_ROOT / "phase_status.json"
EVENT_PREFIX = "RISKOFF_PHASE"


def _is_complete(out_dir: Path) -> bool:
    report = out_dir / "backtest_report.txt"
    if not report.exists() or report.stat().st_size < 40:
        return False
    text = report.read_text(encoding="utf-8", errors="ignore")
    return "Strategy metrics" in text and "total_return" in text


def load_status() -> dict:
    if STATUS_FILE.exists():
        try:
            return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"completed": [], "last_event": ""}


def save_status(status: dict) -> None:
    RESEARCH_ROOT.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")


def poll_once() -> list[str]:
    status = load_status()
    done = set(status.get("completed", []))
    events: list[str] = []
    for exp in EXPERIMENTS:
        key = str(exp["key"])
        if key in done:
            continue
        if _is_complete(RESEARCH_ROOT / key):
            done.add(key)
            msg = f"{EVENT_PREFIX}_DONE {key}"
            events.append(msg)
            status["completed"] = sorted(done)
            status["last_event"] = key
            save_status(status)
    reports = RESEARCH_ROOT / "risk_off_variant_comparison.csv"
    if reports.exists() and not status.get("reports_done"):
        events.append(f"{EVENT_PREFIX}_DONE ALL_REPORTS")
        status["reports_done"] = True
        save_status(status)
    return events


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="Watch risk-off research phase completion.")
    p.add_argument("--once", action="store_true")
    p.add_argument("--interval", type=float, default=60.0)
    args = p.parse_args()
    if args.once:
        for ev in poll_once():
            print(ev, flush=True)
        return 0
    while True:
        for ev in poll_once():
            print(ev, flush=True)
        time.sleep(max(float(args.interval), 15.0))


if __name__ == "__main__":
    raise SystemExit(main())
