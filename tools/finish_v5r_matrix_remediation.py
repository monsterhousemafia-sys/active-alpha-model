#!/usr/bin/env python3
"""Finish V5R matrix remediation: wait for cost stress, finalize, risk-governance re-run."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable

EVAL = ROOT / "tools" / "v5r_matrix_remediation_eval.py"
BENCHMARK_REM = ROOT / "validation_runs" / "v5r_matrix_remediation_20260531T175100Z"
COST_SUFFIXES = ("cost_s2_i0", "cost_s5_i0", "cost_s10_i5", "cost_s20_i10")
POLL_SEC = 90
MAX_WAIT_SEC = 6 * 3600


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _scenario_pass(path: Path) -> bool:
    p = path / "integrity_report.json"
    if not p.is_file():
        return False
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("status") == "PASS"
    except Exception:
        return False


def _cost_complete(rem: Path) -> int:
    return sum(1 for s in COST_SUFFIXES if _scenario_pass(rem / "cost_stress" / s))


def _run(cmd: list[str]) -> int:
    print("RUN:", " ".join(cmd), flush=True)
    return int(subprocess.run(cmd, cwd=ROOT).returncode)


def wait_for_benchmark_matrix(rem: Path) -> bool:
    t0 = time.time()
    while time.time() - t0 < MAX_WAIT_SEC:
        base_ok = _scenario_pass(rem / "base_run")
        cost_ok = _cost_complete(rem)
        print(f"poll base={base_ok} cost={cost_ok}/4 elapsed={int(time.time()-t0)}s", flush=True)
        if base_ok and cost_ok >= 4:
            return True
        # fill missing cost scenarios if parent orchestrator died mid-way
        if base_ok and cost_ok < 4:
            _run(
                [
                    PYTHON,
                    str(EVAL),
                    "--execute-runs",
                    "--cost-stress-only",
                    "--skip-completed",
                    "--remediation-dir",
                    str(rem),
                    "--cpu-cores",
                    "4",
                ]
            )
        time.sleep(POLL_SEC)
    return _scenario_pass(rem / "base_run") and _cost_complete(rem) >= 4


def main() -> int:
    rem = BENCHMARK_REM
    if not rem.is_dir():
        print(f"Missing remediation dir: {rem}", file=sys.stderr)
        return 2

    print("=== Phase 1: complete benchmark+cost matrix ===", flush=True)
    if not wait_for_benchmark_matrix(rem):
        print("TIMEOUT waiting for benchmark matrix", file=sys.stderr)
        return 1

    print("=== Phase 2: finalize benchmark remediation ===", flush=True)
    rc = _run(
        [
            PYTHON,
            str(EVAL),
            "--finalize-only",
            "--remediation-dir",
            str(rem),
            "--validation-source",
            str(rem / "base_run"),
        ]
    )
    if rc != 0:
        print(f"finalize benchmark remediation exit={rc} (may be FAIL verdict)", flush=True)

    risk_stamp = _utc_stamp()
    print(f"=== Phase 3: risk-governance full matrix ({risk_stamp}) ===", flush=True)
    rc = _run(
        [
            PYTHON,
            str(EVAL),
            "--execute-runs",
            "--skip-completed",
            "--label",
            "risk_governance",
            "--stamp",
            risk_stamp,
            "--cpu-cores",
            "4",
        ]
    )
    risk_rem = ROOT / "validation_runs" / f"v5r_matrix_remediation_risk_{risk_stamp}"
    if not wait_for_benchmark_matrix(risk_rem):
        print("TIMEOUT waiting for risk governance matrix", file=sys.stderr)
        return 1

    print("=== Phase 4: finalize risk governance remediation ===", flush=True)
    rc2 = _run(
        [
            PYTHON,
            str(EVAL),
            "--finalize-only",
            "--remediation-dir",
            str(risk_rem),
            "--validation-source",
            str(risk_rem / "base_run"),
            "--label",
            "risk_governance",
        ]
    )

    summary = {
        "benchmark_remediation_dir": str(rem),
        "risk_governance_dir": str(risk_rem),
        "benchmark_finalize_rc": rc,
        "risk_finalize_rc": rc2,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    out = ROOT / "validation_runs" / "v5r_matrix_remediation_finish_summary.json"
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    return 0 if rc2 == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
