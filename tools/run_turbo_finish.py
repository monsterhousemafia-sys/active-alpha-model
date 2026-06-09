#!/usr/bin/env python3
"""Finish validation on max CPU: cost s5 retry, then M1 (sequential, turbo profile)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_runtime_profile import apply_process_priority_from_env  # noqa: E402


def main() -> int:
    os.environ["AA_CPU_CORES"] = os.environ.get("AA_CPU_CORES", "16")
    os.environ["AA_RESERVE_CPU_CORES"] = "0"
    os.environ["AA_RUNTIME_PROFILE"] = "turbo"
    os.environ["AA_PROCESS_PRIORITY"] = "high"
    os.environ["AA_PARALLEL_PROFILE"] = "high"
    apply_process_priority_from_env()

    m1_out = ROOT / "validation_runs" / "20260530T161109Z_M1_MOM_BLEND_MATCHED_CONTROLS"
    if not (m1_out / "prediction_cache.pkl").is_file():
        m1_out = None

    steps = [
        [
            PYTHON,
            str(ROOT / "tools" / "run_validation_matrix.py"),
            "--phase",
            "cost",
            "--variant",
            "R3_w075_q065_noexit_cost_s5_i0",
            "--parallel-jobs",
            "1",
            "--cpu-cores",
            os.environ["AA_CPU_CORES"],
            "--runtime-profile",
            "turbo",
            "--cost-mode",
            "path-only",
            "--no-skip-complete",
        ],
        [
            PYTHON,
            str(ROOT / "tools" / "run_validation_matrix.py"),
            "--phase",
            "matrix",
            "--variant",
            "M1_MOM_BLEND_MATCHED_CONTROLS",
            "--parallel-jobs",
            "1",
            "--cpu-cores",
            os.environ["AA_CPU_CORES"],
            "--runtime-profile",
            "turbo",
            "--no-skip-complete",
        ],
    ]

    rc = 0
    for cmd in steps:
        print(f"\n=== turbo: {' '.join(cmd[2:])} ===", flush=True)
        proc = subprocess.run(cmd, cwd=str(ROOT), env=dict(os.environ))
        if proc.returncode != 0:
            rc = int(proc.returncode)
            print(f"[FAIL] rc={rc}", flush=True)
            return rc
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
