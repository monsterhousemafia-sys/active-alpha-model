#!/usr/bin/env python3
"""Wait for M1 validation PASS, then run cost-stress phase."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
POLL_SEC = 90
MAX_WAIT_SEC = 3 * 3600


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _m1_pass(m1_dir: Path) -> bool:
    pointer = m1_dir / "latest_validated_run.json"
    if pointer.is_file():
        try:
            meta = json.loads(pointer.read_text(encoding="utf-8"))
            if str(meta.get("integrity_status", meta.get("status", ""))) == "PASS":
                matched = m1_dir / "mom_blend_matched_controls_daily_returns.csv"
                return matched.is_file()
        except Exception:
            pass
    report = m1_dir / "integrity_report.json"
    if report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            if str(data.get("status", "")) == "PASS" and not data.get("errors"):
                return (m1_dir / "mom_blend_matched_controls_daily_returns.csv").is_file()
        except Exception:
            pass
    return False


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument(
        "--m1-dir",
        type=Path,
        default=ROOT / "validation_runs" / "20260530T152945Z_M1_MOM_BLEND_MATCHED_CONTROLS",
    )
    p.add_argument("--parallel-jobs", type=int, default=3)
    p.add_argument("--poll-sec", type=int, default=POLL_SEC)
    args = p.parse_args()
    m1_dir = Path(args.m1_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    t0 = time.monotonic()
    print(f"[{_utc()}] Waiting for M1 PASS in {m1_dir}", flush=True)
    while time.monotonic() - t0 < MAX_WAIT_SEC:
        if _m1_pass(m1_dir):
            print(f"[{_utc()}] M1 PASS — starting cost stress (stamp={stamp}_cost)", flush=True)
            break
        elapsed = int(time.monotonic() - t0)
        print(f"[{_utc()}] M1 not ready yet ({elapsed // 60} min elapsed)", flush=True)
        time.sleep(max(15, int(args.poll_sec)))
    else:
        print(f"[{_utc()}] Timeout waiting for M1", flush=True)
        return 2

    cmd = [
        PYTHON,
        str(ROOT / "tools" / "run_validation_matrix.py"),
        "--phase",
        "cost",
        "--stamp",
        stamp,
        "--parallel-jobs",
        str(max(1, min(4, int(args.parallel_jobs)))),
        "--runtime-profile",
        "validation",
        "--cost-mode",
        "path-only",
    ]
    print(f"[{_utc()}] {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT))
    print(f"[{_utc()}] Cost stress finished rc={proc.returncode}", flush=True)
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
