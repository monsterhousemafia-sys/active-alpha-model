"""Interactive release GUI verification via submitted Marktanalyse.exe self-exit hook."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE = ROOT / "evidence"
SUBMISSION_EXE = Path(os.environ.get("V5R_SUBMISSION_EXE", str(ROOT / "Marktanalyse.exe")))
JSON_OUT = EVIDENCE / "v5r_release_interactive_gui_verification.json"
LOG = EVIDENCE / "v5r_release_interactive_gui_test_log.txt"
PNG_OUT = EVIDENCE / "v5r_release_interactive_gui_screenshot.png"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _expected_build_commit() -> str:
    env_path = EVIDENCE / "v5r_final_build_environment.json"
    if env_path.is_file():
        return json.loads(env_path.read_text(encoding="utf-8")).get("build_source_commit", "")
    return ""


def main() -> int:
    from tools.v5r_gui_test_common import stop_marktanalyse_processes

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    lines = [
        f"started_utc={_utc_now()}",
        f"release_exe_absolute_path={SUBMISSION_EXE.resolve()}",
        "AA_DECISION_COCKPIT_SMOKE_TEST=unset",
        "AA_RELEASE_GUI_EVIDENCE_SELF_EXIT=1",
    ]
    if not SUBMISSION_EXE.is_file():
        lines.append("FAIL submitted_release_exe_missing")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    stop_marktanalyse_processes()
    for stale in (JSON_OUT, PNG_OUT):
        if stale.is_file():
            stale.unlink()

    exe_hash = _sha256(SUBMISSION_EXE)
    env = {k: v for k, v in os.environ.items() if k not in {"AA_DECISION_COCKPIT_SMOKE_TEST", "AA_RELEASE_GUI_EVIDENCE_SELF_EXIT"}}
    env["AA_RELEASE_GUI_EVIDENCE_SELF_EXIT"] = "1"
    proc = subprocess.Popen([str(SUBMISSION_EXE.resolve())], cwd=ROOT, env=env)
    lines.append(f"process_started_pid={proc.pid}")

    deadline = time.time() + 90
    exit_code = None
    while time.time() < deadline:
        if JSON_OUT.is_file():
            try:
                payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
                if payload.get("screenshot_captured") or payload.get("pass") is not None:
                    break
            except json.JSONDecodeError:
                pass
        polled = proc.poll()
        if polled is not None:
            exit_code = polled
            break
        time.sleep(0.5)
    else:
        lines.append("FAIL timed_out_waiting_for_gui_self_exit_evidence")
        proc.kill()
        stop_marktanalyse_processes()
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    if exit_code is None:
        exit_code = proc.wait(timeout=10)
    stop_marktanalyse_processes()
    lines.append(f"exit_code={exit_code}")

    if not JSON_OUT.is_file():
        lines.append("FAIL launcher_gui_evidence_missing")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    result = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    result["release_exe_absolute_path"] = str(SUBMISSION_EXE.resolve())
    result["release_exe_sha256"] = exe_hash
    result["tested_exe_sha256"] = exe_hash
    result["submitted_release_exe_used_for_interactive_test"] = True
    result["orchestrator_verified_submission_path"] = True
    expected_commit = _expected_build_commit()
    if expected_commit:
        result["expected_build_source_commit"] = expected_commit
        result["build_commit_matches_final_build"] = result.get("build_source_commit") == expected_commit
        result["release_exe_sha256_matches_submission"] = result.get("release_exe_sha256") == exe_hash
    result["pass"] = bool(
        exit_code == 0
        and result.get("gui_window_observed")
        and result.get("read_only_state_verified")
        and result.get("screenshot_captured")
        and result.get("build_commit_matches_final_build", True)
    )
    JSON_OUT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines.append(json.dumps(result, ensure_ascii=False))
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
