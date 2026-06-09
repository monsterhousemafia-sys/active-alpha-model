#!/usr/bin/env python3
"""End-to-end EXE integrity loop: tests, static verify, full-function matrix."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PY = ROOT / ".venv" / "Scripts" / "python.exe"
if not PY.is_file():
    PY = Path(sys.executable)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(cmd: list[str], *, label: str) -> dict:
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    return {
        "label": label,
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "stdout_tail": (proc.stdout or "")[-3000:],
        "stderr_tail": (proc.stderr or "")[-1500:],
        "pass": proc.returncode == 0,
    }


def main() -> int:
    steps = [
        _run(
            [str(PY), "-m", "pytest", "tests/test_live_quote_engine.py", "tests/test_learning_pipeline.py", "tests/test_build_integrity.py", "tests/test_aa_doc_paths.py", "tests/test_interactive_cockpit_full_function_matrix.py", "tests/test_decision_cockpit_readonly_launcher.py", "tests/test_v5r_standalone_spec.py", "tests/test_aa_paths.py", "tests/test_marktanalyse_runtime_bootstrap.py", "-q", "--tb=line"],
            label="pytest_core",
        ),
        _run([str(PY), str(ROOT / "tools/static_verify_v5r_standalone_exe.py")], label="static_exe_verify"),
        _run([str(PY), str(ROOT / "tools/run_exe_full_function_test.py")], label="full_function_matrix"),
    ]
    overall = all(s["pass"] for s in steps)
    report = {
        "generated_at_utc": _utc_now(),
        "overall_pass": overall,
        "steps": steps,
        "exe_sha256": None,
    }
    exe = ROOT / "Marktanalyse.exe"
    if exe.is_file():
        from aa_build_integrity import read_recorded_hash, sha256_file, verify_exe_hash_consistency

        report["exe_sha256"] = sha256_file(exe)
        report["recorded_sha256"] = read_recorded_hash(ROOT)
        report["hash_consistent"] = verify_exe_hash_consistency(root=ROOT)
    out = ROOT / "evidence" / "exe_integrity_loop_report.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if overall else 1


if __name__ == "__main__":
    raise SystemExit(main())
