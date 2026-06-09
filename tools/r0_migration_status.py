#!/usr/bin/env python3
"""Unified migration status (WSL + Windows) — replaces scattered status bats/scripts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools._m1_autoseal import complete_dirs, is_sealed, _fast_seal
from tools.r0_migration_hw import cpu_delta, list_processes, nproc


def main() -> int:
    procs = list_processes()
    m1 = [p for p in procs if "M1_MOM_BLEND" in p.get("cmd", "")]
    bt_pids = [p["pid"] for p in m1 if "active_alpha_model.py" in p.get("cmd", "")]
    delta = cpu_delta(bt_pids, 2.0) if bt_pids else 0.0
    snap = {
        "host": "windows" if __import__("os").name == "nt" else "linux",
        "cpu_cores": nproc(),
        "migration_procs": len(procs),
        "m1_backtest_pids": bt_pids,
        "m1_cpu_delta_2s": delta,
        "m1_productive": delta >= 0.5,
        "fast_seal": _fast_seal(),
        "m1_sealed": is_sealed(),
        "autoseal_ready": {
            v: complete_dirs(v) for v in (
                "R0_LEGACY_ENSEMBLE",
                "R3_w075_q065_noexit",
                "M1_MOM_BLEND_MATCHED_CONTROLS",
            )
        },
    }
    print(json.dumps(snap, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
