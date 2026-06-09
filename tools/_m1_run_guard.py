"""M1 run guard - anti-confusion safety probe (READ-ONLY).

Prevents the failure mode where two concurrent M1 backtests run and the WRONG
(productive) one gets killed by mistake. Provides two safety mechanisms:

  1. inventory(): enumerate every live M1 backtest process, group them by their
     run directory, and classify each run as PRODUCTIVE vs IDLE_OR_HUNG by
     MEASURED CPU growth over a sampling window -- never by inferring from file
     timestamps (that inference is exactly what caused the earlier mix-up).
     Emits an explicit keep / kill-candidate verdict.

  2. preflight_launch(): report whether it is safe to start a NEW M1 backtest,
     i.e. only when no PRODUCTIVE run already exists -> never spawn a duplicate.

This tool NEVER kills anything. Killing stays a deliberate action and must be
justified by this tool's CPU evidence (verdict CONFLICT_KEEP_PRODUCTIVE lists
the exact dirs that are safe to stop).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
VR = ROOT / "validation_runs"
M1_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"
FAST_SEAL_FLAG = ROOT / "control" / "r0_migration" / "m1_fast_seal.flag"

# CPU-seconds accumulated across the sampling window above which a run is
# considered actively computing (path simulation is ~1 core; 0.5 is a safe
# floor that still rejects a fully idle/hung process at ~0.0).
CPU_ACTIVE_THRESHOLD = 0.5

# Matches the canonical run-dir stamp anywhere in a command line, e.g.
# 20260604T203857Z_M1_MOM_BLEND_MATCHED_CONTROLS.
DIR_RE = re.compile(r"(\d{8}T\d{6}Z_[A-Za-z0-9_]+)")


def _backtest_procs(variant: str) -> List[Dict[str, Any]]:
    """[{pid, run_dir}] for live active_alpha_model backtests of `variant`."""
    from tools.r0_migration_commander import _migration_pids

    out: List[Dict[str, Any]] = []
    for p in _migration_pids():
        cmd = p.get("cmd", "") or ""
        if "active_alpha_model.py" not in cmd or variant not in cmd:
            continue
        m = DIR_RE.search(cmd)
        out.append({"pid": int(p["pid"]), "run_dir": m.group(1) if m else "?"})
    return out


def _cpu_delta(pids: List[int], sample_sec: float = 2.0) -> float:
    """Cumulative CPU-seconds consumed by `pids` over the sampling window."""
    from tools.r0_migration_runtime import _worker_cpu_total

    c0 = _worker_cpu_total(pids)
    time.sleep(max(0.5, min(float(sample_sec), 8.0)))
    c1 = _worker_cpu_total(pids)
    return round(c1 - c0, 2)


def _phase_artifacts(run_dir: str) -> Dict[str, bool]:
    d = VR / run_dir
    return {
        "prediction_cache": (d / "prediction_cache.pkl").is_file(),
        "strategy_csv": (d / "strategy_daily_returns.csv").is_file(),
        "matched_csv": (d / "mom_blend_matched_controls_daily_returns.csv").is_file(),
        "integrity_report": (d / "integrity_report.json").is_file(),
    }


def _verdict(runs: List[Dict[str, Any]]) -> Dict[str, Any]:
    productive = [r for r in runs if r["classification"] == "PRODUCTIVE"]
    if not runs:
        return {"verdict": "NO_RUN", "keep": None, "kill_candidates": []}
    if len(runs) == 1:
        v = "SINGLE_OK" if productive else "SINGLE_IDLE_INVESTIGATE"
        return {"verdict": v, "keep": runs[0]["run_dir"], "kill_candidates": []}
    # more than one run = conflict; the rule is: keep the single productive one.
    if len(productive) == 1:
        keep = productive[0]["run_dir"]
        return {
            "verdict": "CONFLICT_KEEP_PRODUCTIVE",
            "keep": keep,
            "kill_candidates": [r["run_dir"] for r in runs if r["run_dir"] != keep],
        }
    if not productive:
        # never kill blindly when none shows CPU - investigate first.
        return {"verdict": "CONFLICT_ALL_IDLE_INVESTIGATE", "keep": None, "kill_candidates": []}
    return {"verdict": "CONFLICT_MULTIPLE_PRODUCTIVE_DO_NOT_KILL", "keep": None, "kill_candidates": []}


def inventory(variant: str = M1_VARIANT, sample_sec: float = 2.0) -> Dict[str, Any]:
    procs = _backtest_procs(variant)
    by_dir: Dict[str, List[int]] = {}
    for p in procs:
        by_dir.setdefault(p["run_dir"], []).append(p["pid"])

    runs: List[Dict[str, Any]] = []
    for run_dir, pids in by_dir.items():
        delta = _cpu_delta(pids, sample_sec)
        runs.append(
            {
                "run_dir": run_dir,
                "pids": sorted(pids),
                "cpu_delta": delta,
                "classification": "PRODUCTIVE" if delta > CPU_ACTIVE_THRESHOLD else "IDLE_OR_HUNG",
                "artifacts": _phase_artifacts(run_dir),
            }
        )
    runs.sort(key=lambda r: r["run_dir"])
    result: Dict[str, Any] = {"variant": variant, "n_runs": len(runs), "runs": runs}
    result.update(_verdict(runs))
    return result


def preflight_launch(variant: str = M1_VARIANT) -> Dict[str, Any]:
    """Safe to launch a NEW backtest only when no PRODUCTIVE run exists."""
    inv = inventory(variant)
    inv["safe_to_launch"] = inv["n_runs"] == 0 or all(
        r["classification"] != "PRODUCTIVE" for r in inv["runs"]
    )
    return inv


def watch(variant: str = M1_VARIANT, idle_limit: int = 3, interval: float = 56.0) -> int:
    """Babysit a running M1 backtest: emit a sentinel as soon as it FINISHES
    (both CSVs), DIES, or HANGS (idle CPU for `idle_limit` consecutive checks).
    Designed to be run in the background with output-notification so a silent
    hang (like the overnight process-pool deadlock) is caught within minutes."""
    from tools.r0_migration_commander import _migration_pids
    from tools.r0_migration_runtime import _worker_cpu_total

    idle = 0
    while True:
        procs = _backtest_procs(variant)
        if not procs:
            print("M1_WATCH_PROC_GONE", flush=True)
            return 0
        run_dir = procs[0]["run_dir"]
        art = _phase_artifacts(run_dir)
        csvs_ready = art["strategy_csv"] and (
            art["matched_csv"] or FAST_SEAL_FLAG.is_file()
        )
        if csvs_ready:
            print(f"M1_WATCH_CSVS_READY dir={run_dir}", flush=True)
            return 0
        pids = [p["pid"] for p in procs]
        delta = _cpu_delta(pids, 4.0)
        idle = idle + 1 if delta < 0.2 else 0
        print(
            f"M1_WATCH alive pids={len(pids)} cpu_delta={delta} idle_streak={idle} "
            f"strat={art['strategy_csv']} matched={art['matched_csv']}",
            flush=True,
        )
        if idle >= idle_limit:
            print(f"M1_WATCH_HANG_DETECTED dir={run_dir} idle_checks={idle}", flush=True)
            return 2
        time.sleep(max(5.0, float(interval)))


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    mode = argv[0] if argv else "inventory"
    if mode == "watch":
        variant = M1_VARIANT
        idle_limit = 3
        interval = 56.0
        i = 1
        while i < len(argv):
            if argv[i] == "--idle-limit" and i + 1 < len(argv):
                idle_limit = int(argv[i + 1])
                i += 2
            elif argv[i] == "--interval" and i + 1 < len(argv):
                interval = float(argv[i + 1])
                i += 2
            elif not argv[i].startswith("-"):
                variant = argv[i]
                i += 1
            else:
                i += 1
        return watch(variant, idle_limit=idle_limit, interval=interval)
    variant = argv[1] if len(argv) > 1 else M1_VARIANT
    res = preflight_launch(variant) if mode == "preflight" else inventory(variant)
    print(json.dumps(res, indent=2))
    # exit code communicates the safety state for scripted callers.
    if mode == "preflight":
        return 0 if res.get("safe_to_launch") else 2
    return 0 if res.get("verdict") in ("NO_RUN", "SINGLE_OK") else 2


if __name__ == "__main__":
    raise SystemExit(main())
