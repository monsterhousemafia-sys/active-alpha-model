#!/usr/bin/env python3
"""Zero-error gate — full tests + EXE integrity; fails on any error."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_build_integrity import authenticode_status, verify_exe_hash_consistency, write_build_integrity_manifest

PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.is_file():
    PY = Path(sys.executable)
REPORT = ROOT / "evidence" / "zero_error_gate_report.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(label: str, cmd: list[str]) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "label": label,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "pass": proc.returncode == 0,
        "stdout_tail": (proc.stdout or "")[-2000:],
        "stderr_tail": (proc.stderr or "")[-1000:],
    }


def _hash_integrity_step() -> dict:
    exe = ROOT / "Marktanalyse.exe"
    verify = verify_exe_hash_consistency(root=ROOT)
    manifest = write_build_integrity_manifest(root=ROOT, exe_path=exe if exe.is_file() else None)
    signing = authenticode_status(exe) if exe.is_file() else {"status": "exe_missing"}
    ok = bool(verify.get("ok"))
    return {
        "label": "exe_hash_integrity",
        "pass": ok,
        "verify": verify,
        "manifest": str(manifest),
        "authenticode": signing,
    }


def main() -> int:
    steps = [
        _run("pytest_full", [str(PY), "-m", "pytest", "tests/", "-q", "--tb=no"]),
        _run("exe_integrity_loop", [str(PY), str(ROOT / "tools/run_exe_integrity_loop.py")]),
        _hash_integrity_step(),
    ]
    overall = all(s["pass"] for s in steps)
    report = {"generated_at_utc": _utc_now(), "overall_pass": overall, "steps": steps}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
