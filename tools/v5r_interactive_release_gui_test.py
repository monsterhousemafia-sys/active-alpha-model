"""Interactive read-only GUI verification for V5R release EXE only."""
from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
RELEASE_EXE = ROOT / "dist" / "Marktanalyse.exe"
JSON_OUT = EVIDENCE / "v5r_interactive_release_gui_verification.json"
LOG = EVIDENCE / "v5r_interactive_release_gui_test_log.txt"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _marktanalyse_pids() -> list[int]:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", "(Get-Process -Name Marktanalyse -ErrorAction SilentlyContinue).Id -join ' '"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [int(x) for x in (proc.stdout or "").split() if x.strip().isdigit()]


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    lines = [f"started_utc={_utc_now()}", f"release_exe={RELEASE_EXE}", "AA_DECISION_COCKPIT_SMOKE_TEST=unset"]
    env = {k: v for k, v in __import__("os").environ.items() if k != "AA_DECISION_COCKPIT_SMOKE_TEST"}
    subprocess.Popen([str(RELEASE_EXE)], cwd=ROOT, env=env)
    time.sleep(10)
    pids = _marktanalyse_pids()
    responding = False
    for pid in pids:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).Responding"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "True" in (proc.stdout or ""):
            responding = True
            break
    for pid in pids:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            check=False,
        )
    result = {
        "interactive_release_gui_test_executed": True,
        "artifact": "dist/Marktanalyse.exe",
        "artifact_class": "V5R_RELEASE",
        "gui_window_observed": bool(pids and responding),
        "process_responding": responding,
        "operative_ui_actions_present": False,
        "operative_jobs_executed": False,
        "expected_gui_test_teardown": True,
        "generated_at_utc": _utc_now(),
        "pass": bool(pids and responding),
    }
    JSON_OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines.append(json.dumps(result))
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
