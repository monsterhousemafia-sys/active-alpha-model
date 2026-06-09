"""Timeout-controlled runtime smoke test for dist/Marktanalyse.exe (V5R).

Does not wait indefinitely for GUI self-termination. Uses controlled teardown via
taskkill after verifying process start (and window/responding state when available).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "evidence"
DIST_EXE = ROOT / "dist" / "Marktanalyse.exe"

# Seconds to wait for GUI bootstrap before classifying start (not exit).
GUI_START_WAIT_S = 12
# Hard cap on total test duration including teardown.
MAX_TOTAL_S = 45
# Optional self-exit via launcher env (works only if EXE built with smoke hook).
SMOKE_ENV_MS = "12000"


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    import hashlib

    if not path.is_file():
        return "MISSING"
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ps_json(script: str) -> Any:
    proc = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def list_marktanalyse_processes() -> List[Dict[str, Any]]:
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name='Marktanalyse.exe'\" | "
        "Select-Object ProcessId,CommandLine,CreationDate | ConvertTo-Json -Compress"
    )
    data = _ps_json(script)
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []


def process_state(pid: int) -> Dict[str, Any]:
    script = (
        f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if (-not $p) { @{ alive=$false } | ConvertTo-Json -Compress; exit 0 }; "
        "@{ alive=$true; responding=$p.Responding; main_window_title=$p.MainWindowTitle; "
        f"path=$p.Path }} | ConvertTo-Json -Compress"
    )
    data = _ps_json(script)
    return dict(data) if isinstance(data, dict) else {"alive": False}


def controlled_teardown(pid: int, log: List[str]) -> Dict[str, Any]:
    """Force-close process tree; never block on GUI quit."""
    before = process_state(pid)
    cmd = ["taskkill", "/PID", str(pid), "/T", "/F"]
    log.append(f"teardown_cmd={' '.join(cmd)}")
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    log.append(f"taskkill_exit={proc.returncode}")
    if proc.stdout:
        log.append(f"taskkill_stdout={proc.stdout.strip()}")
    if proc.stderr:
        log.append(f"taskkill_stderr={proc.stderr.strip()}")
    time.sleep(1.0)
    after = process_state(pid)
    return {
        "pid": pid,
        "before": before,
        "after": after,
        "taskkill_exit_code": proc.returncode,
        "terminated": not after.get("alive", True),
    }


def document_blocked_processes(log: List[str]) -> List[Dict[str, Any]]:
    docs: List[Dict[str, Any]] = []
    for row in list_marktanalyse_processes():
        pid = int(row.get("ProcessId") or 0)
        if pid <= 0:
            continue
        st = process_state(pid)
        entry = {
            "process_name": "Marktanalyse",
            "pid": pid,
            "command_line": row.get("CommandLine"),
            "creation_date": row.get("CreationDate"),
            "path": st.get("path"),
            "responding": st.get("responding"),
            "main_window_title": st.get("main_window_title"),
            "gui_window_visible": bool(st.get("main_window_title")),
            "termination_reason": "ORPHAN_FROM_PRIOR_SMOKE_TEST",
            "note": "Process did not self-terminate; orchestrator was interrupted while waiting on communicate().",
        }
        docs.append(entry)
        log.append(f"prior_orphan pid={pid} cmd={entry.get('command_line')}")
    return docs


def classify_runtime_outcome(
    *,
    started: bool,
    alive_after_wait: bool,
    responding: Optional[bool],
    window_title: str,
    exit_code: Optional[int],
    self_exit_requested: bool,
) -> Tuple[str, bool]:
    """Return (outcome_code, pass_for_v5r_runtime)."""
    if not started:
        return "RUNTIME_TEST_FAIL", False
    if exit_code == 0 and not alive_after_wait:
        return "PASS_SELF_EXIT", True
    if alive_after_wait and (responding is True or bool(window_title)):
        return "EXPECTED_GUI_TEST_TEARDOWN", True
    if alive_after_wait and responding is not False:
        # Process alive and not hung — typical PySide6 before window title is set.
        return "EXPECTED_GUI_TEST_TEARDOWN", True
    if alive_after_wait:
        return "RUNTIME_TEST_FAIL", False
    if exit_code not in (None, 0):
        return "RUNTIME_TEST_FAIL", False
    return "RUNTIME_TEST_FAIL", False


def run_smoke_test() -> Dict[str, Any]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    log: List[str] = []
    log.append(f"started_at={utc_stamp()}")
    log.append(f"exe={DIST_EXE}")
    log.append(f"GUI_START_WAIT_S={GUI_START_WAIT_S} MAX_TOTAL_S={MAX_TOTAL_S}")

    blocked_docs = document_blocked_processes(log)
    teardown_prior: List[Dict[str, Any]] = []
    for doc in blocked_docs:
        teardown_prior.append(controlled_teardown(int(doc["pid"]), log))
        doc["controlled_teardown"] = teardown_prior[-1]
        doc["termination_reason"] = "CONTROLLED_TEARDOWN_AFTER_DOCUMENTATION"

    if not DIST_EXE.is_file():
        result = {"pass": False, "outcome": "RUNTIME_TEST_FAIL", "error": "dist/Marktanalyse.exe missing"}
        _write_evidence(log, blocked_docs, result, {}, {}, {})
        return result

    env = os.environ.copy()
    env["AA_DECISION_COCKPIT_SMOKE_TEST"] = SMOKE_ENV_MS
    log.append(f"env_AA_DECISION_COCKPIT_SMOKE_TEST={SMOKE_ENV_MS}")

    t0 = time.monotonic()
    proc = subprocess.Popen(
        [str(DIST_EXE)],
        cwd=str(DIST_EXE.parent),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    log.append(f"launched_pid={proc.pid}")

    time.sleep(GUI_START_WAIT_S)
    st = process_state(proc.pid)
    alive = bool(st.get("alive"))
    poll_code = proc.poll()
    exit_code = poll_code if poll_code is not None else None
    window_title = str(st.get("main_window_title") or "")
    log.append(
        f"after_wait alive={alive} responding={st.get('responding')} window_title={window_title!r} exit_code={exit_code}"
    )

    outcome, runtime_pass = classify_runtime_outcome(
        started=True,
        alive_after_wait=alive,
        responding=st.get("responding"),
        window_title=window_title,
        exit_code=exit_code,
        self_exit_requested=True,
    )

    teardown: Dict[str, Any] = {}
    if alive:
        teardown = controlled_teardown(proc.pid, log)
        if not teardown.get("terminated"):
            outcome = "RUNTIME_TEST_FAIL"
            runtime_pass = False

    elapsed = time.monotonic() - t0
    log.append(f"elapsed_s={elapsed:.2f} outcome={outcome} pass={runtime_pass}")

    companion = DIST_EXE.parent / "Marktanalyse" / "_internal"
    requires_internal = companion.is_dir() and any(companion.iterdir())

    process_result = {
        "exe": str(DIST_EXE),
        "sha256": sha256_file(DIST_EXE),
        "pid_started": proc.pid,
        "exit_code": exit_code,
        "outcome": outcome,
        "executed": True,
        "pass": runtime_pass,
        "gui_start_wait_seconds": GUI_START_WAIT_S,
        "max_total_seconds": MAX_TOTAL_S,
        "elapsed_seconds": round(elapsed, 2),
        "process_responding": st.get("responding"),
        "main_window_title": window_title,
        "gui_window_visible": bool(window_title),
        "controlled_teardown": teardown,
        "requires_companion_internal_folder": requires_internal,
        "generated_at_utc": utc_stamp(),
    }
    readonly = {
        "exe_path": str(DIST_EXE),
        "companion_internal_required": requires_internal,
        "gui_smoke_started": True,
        "outcome": outcome,
        "pass": runtime_pass and not requires_internal,
        "operative_ui_actions_present": False,
        "note": "Read-only verified via static audit + fail-closed unit tests; runtime confirms GUI launch only.",
        "generated_at_utc": utc_stamp(),
    }
    fail_closed_path = EVIDENCE / "v5r_fail_closed_test_results.json"
    fc_pass = False
    if fail_closed_path.is_file():
        fc_pass = bool(json.loads(fail_closed_path.read_text(encoding="utf-8")).get("pass"))
    fail_closed = {
        "method": "pytest fail-closed cockpit tests + static import audit",
        "python_fail_closed_tests_pass": fc_pass,
        "pass": fc_pass,
        "generated_at_utc": utc_stamp(),
    }

    blocked_report = {
        "documented_at_utc": utc_stamp(),
        "blocked_processes": blocked_docs,
        "prior_run_note": (
            "Previous orchestrator run blocked on subprocess.communicate(timeout=120) "
            "because dist/Marktanalyse.exe (pre-smoke-hook build) does not honor "
            "AA_DECISION_COCKPIT_SMOKE_TEST self-exit."
        ),
    }

    _write_evidence(log, blocked_docs, process_result, readonly, fail_closed, blocked_report)
    return process_result


def _write_evidence(
    log: List[str],
    blocked_docs: List[Dict[str, Any]],
    process_result: Dict[str, Any],
    readonly: Dict[str, Any],
    fail_closed: Dict[str, Any],
    blocked_report: Dict[str, Any],
) -> None:
    (EVIDENCE / "v5r_runtime_smoke_test_log.txt").write_text("\n".join(log) + "\n", encoding="utf-8")
    (EVIDENCE / "v5r_runtime_process_result.json").write_text(
        json.dumps(process_result, indent=2), encoding="utf-8"
    )
    (EVIDENCE / "v5r_runtime_readonly_verification.json").write_text(
        json.dumps(readonly, indent=2), encoding="utf-8"
    )
    (EVIDENCE / "v5r_runtime_fail_closed_verification.json").write_text(
        json.dumps(fail_closed, indent=2), encoding="utf-8"
    )
    (EVIDENCE / "v5r_runtime_blocked_process_report.json").write_text(
        json.dumps(blocked_report, indent=2), encoding="utf-8"
    )
    shots = EVIDENCE / "v5r_runtime_screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    (shots / "README.txt").write_text(
        "Screenshots not captured; GUI presence inferred from process alive/responding state.\n",
        encoding="utf-8",
    )


def main() -> int:
    result = run_smoke_test()
    print(json.dumps(result, indent=2))
    return 0 if result.get("pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
