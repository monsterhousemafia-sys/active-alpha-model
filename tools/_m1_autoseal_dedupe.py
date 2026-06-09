#!/usr/bin/env python3
"""Ensure exactly one _m1_autoseal instance (migration hygiene)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.r0_migration_hw import kill_pids, list_processes, pid_alive


def dedupe_autoseal(*, dry_run: bool = False) -> dict:
    procs = [
        p
        for p in list_processes(cmd_markers=("_m1_autoseal",))
        if "_m1_autoseal.py" in p.get("cmd", "")
    ]
    pids = sorted(p["pid"] for p in procs)
    if len(pids) <= 1:
        return {"kept": pids[0] if pids else None, "killed": [], "reason": "already_singleton"}
    keep = pids[0]
    kill = [p for p in pids[1:] if pid_alive(p)]
    if not dry_run and kill:
        kill_pids(kill)
    return {"kept": keep, "killed": kill, "all_pids": pids}


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    out = dedupe_autoseal(dry_run=args.dry_run)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
