#!/usr/bin/env python3
"""Run Marktanalyse.exe full-function matrix and fail on any broken feature."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
from aa_paths import canonical_marktanalyse_exe

EXE = canonical_marktanalyse_exe(ROOT)
EVIDENCE = ROOT / "evidence" / "interactive_cockpit_full_function_matrix.json"
PY = ROOT / ".venv" / "Scripts" / "python.exe"


def _kill_running() -> None:
    if sys.platform != "win32":
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -Name 'Marktanalyse*' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
    )


def run_python_matrix() -> dict:
    py = PY if PY.is_file() else Path(sys.executable)
    proc = subprocess.run(
        [str(py), "-m", "pytest", "tests/test_interactive_cockpit_full_function_matrix.py", "-q", "--tb=short"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return {"channel": "pytest", "exit_code": proc.returncode, "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-2000:]}


def run_exe_matrix() -> dict:
    if not EXE.is_file():
        return {"channel": "exe", "exit_code": 2, "error": f"missing {EXE}"}
    _kill_running()
    env = os.environ.copy()
    for key in (
        "AA_DECISION_COCKPIT_SMOKE_TEST",
        "AA_INTERACTIVE_COCKPIT_SMOKE_TEST",
        "AA_FAIL_CLOSED_TEST_SELF_EXIT",
        "AA_RELEASE_GUI_EVIDENCE_SELF_EXIT",
    ):
        env.pop(key, None)
    env["AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST"] = "1"
    env["AA_ALLOW_MULTI_INSTANCE"] = "1"
    env["AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"] = "1"
    proc = subprocess.run([str(EXE)], cwd=ROOT, env=env, capture_output=True, text=True, timeout=180)
    report = {}
    if EVIDENCE.is_file():
        report = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    return {
        "channel": "exe",
        "exit_code": proc.returncode,
        "report": report,
        "stdout": proc.stdout[-2000:],
        "stderr": proc.stderr[-2000:],
    }


def main() -> int:
    py_result = run_python_matrix()
    exe_result = run_exe_matrix()
    summary = {
        "python_matrix": py_result,
        "exe_matrix": exe_result,
        "overall_pass": py_result.get("exit_code") == 0
        and exe_result.get("exit_code") == 0
        and (exe_result.get("report") or {}).get("overall") == "PASS",
    }
    out = ROOT / "evidence" / "exe_full_function_test_summary.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    if not summary["overall_pass"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
