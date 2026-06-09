"""Runtime fail-closed verification for Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe."""
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
FAIL_CLOSED_EXE = Path(
    os.environ.get("V5R_FAIL_CLOSED_TEST_EXE", str(ROOT / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"))
)
RELEASE_EXE = ROOT / "Marktanalyse.exe"
RUNTIME_JSON = EVIDENCE / "v5r_fail_closed_runtime_test_result.json"
VERIFY_JSON = EVIDENCE / "v5r_fail_closed_runtime_verification.json"
LOG = EVIDENCE / "v5r_fail_closed_runtime_test_log.txt"
SUPPLEMENTARY_PNG = EVIDENCE / "v5r_fail_closed_runtime_supplementary_render.png"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _release_exe_hash_unchanged(before: str | None) -> bool:
    if not RELEASE_EXE.is_file() or before is None:
        return RELEASE_EXE.is_file() and before is None
    return _sha256(RELEASE_EXE) == before


def main() -> int:
    from tools.v5r_gui_test_common import stop_marktanalyse_processes

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    stop_marktanalyse_processes()
    for stale in (RUNTIME_JSON, VERIFY_JSON, ROOT / "evidence" / "v5r_fail_closed_runtime_test_result.json"):
        if stale.is_file():
            stale.unlink()
    lines = [f"started_utc={_utc_now()}"]
    if not FAIL_CLOSED_EXE.is_file():
        lines.append(f"FAIL missing_test_exe={FAIL_CLOSED_EXE}")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    exe_path = FAIL_CLOSED_EXE.resolve()
    exe_hash = _sha256(FAIL_CLOSED_EXE)
    release_before = _sha256(RELEASE_EXE) if RELEASE_EXE.is_file() else None
    lines.append(f"fail_closed_test_exe_absolute_path={exe_path}")
    lines.append(f"fail_closed_test_exe_sha256={exe_hash}")
    lines.append("AA_FAIL_CLOSED_TEST_SELF_EXIT=1")

    env = {k: v for k, v in os.environ.items() if k not in {"AA_DECISION_COCKPIT_SMOKE_TEST", "AA_FAIL_CLOSED_TEST_SELF_EXIT"}}
    env["AA_FAIL_CLOSED_TEST_SELF_EXIT"] = "1"
    launcher_result_path = ROOT / "evidence" / "v5r_fail_closed_runtime_test_result.json"
    proc = subprocess.Popen([str(exe_path)], cwd=ROOT, env=env)
    deadline = time.time() + 90
    exit_code = None
    while time.time() < deadline:
        if launcher_result_path.is_file():
            try:
                json.loads(launcher_result_path.read_text(encoding="utf-8"))
                break
            except json.JSONDecodeError:
                pass
        polled = proc.poll()
        if polled is not None:
            exit_code = polled
            break
        time.sleep(0.5)
    else:
        proc.kill()
        stop_marktanalyse_processes()
        lines.append("FAIL timed_out_waiting_for_fail_closed_self_exit_evidence")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1
    if exit_code is None:
        exit_code = proc.wait(timeout=10)
    stop_marktanalyse_processes()
    lines.append(f"exit_code={exit_code}")

    if not launcher_result_path.is_file():
        lines.append("FAIL launcher_runtime_evidence_missing")
        LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 1

    launcher_payload = json.loads(launcher_result_path.read_text(encoding="utf-8"))
    RUNTIME_JSON.write_text(json.dumps(launcher_payload, indent=2) + "\n", encoding="utf-8")

    supplementary_render = False
    try:
        from tools.v5r_interactive_invalid_evidence_test import _render_embedded_snapshot_ui_png

        render_info = _render_embedded_snapshot_ui_png(SUPPLEMENTARY_PNG)
        supplementary_render = bool(render_info.get("render_saved"))
        lines.append(f"supplementary_render={json.dumps(render_info, ensure_ascii=False)}")
    except Exception as exc:
        lines.append(f"supplementary_render_skipped={exc}")

    build_commit = launcher_payload.get("build_source_commit") or (
        (launcher_payload.get("build_provenance") or {}).get("build_source_commit")
    )
    verified = {
        "fail_closed_test_exe_absolute_path": str(exe_path),
        "fail_closed_test_exe_sha256": exe_hash,
        "fail_closed_test_exe_actually_executed": True,
        "exit_code": exit_code,
        "build_source_commit": build_commit,
        "validated_source_base": launcher_payload.get("validated_source_base")
        or (launcher_payload.get("build_provenance") or {}).get("validated_source_base"),
        "artifact_class": "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE",
        "invalid_evidence_condition_confirmed": launcher_payload.get("invalid_evidence_condition_confirmed"),
        "fail_closed_state_verified_in_executable_path": launcher_payload.get(
            "fail_closed_state_verified_in_executable_path"
        ),
        "operative_ui_actions_present": launcher_payload.get("operative_ui_actions_present"),
        "operative_jobs_executed": launcher_payload.get("operative_jobs_executed"),
        "release_exe_modified_by_negative_test": not _release_exe_hash_unchanged(release_before),
        "runtime_evidence_source": str(launcher_result_path.relative_to(ROOT)).replace("\\", "/"),
        "supplementary_render_path": str(SUPPLEMENTARY_PNG.relative_to(ROOT)).replace("\\", "/")
        if supplementary_render
        else None,
        "supplementary_render_only_not_runtime_substitute": True,
        "generated_at_utc": _utc_now(),
        "pass": bool(
            exit_code == 0
            and launcher_payload.get("result") == "PASS_SELF_EXIT"
            and launcher_payload.get("invalid_evidence_condition_confirmed")
            and launcher_payload.get("fail_closed_state_verified_in_executable_path")
            and _release_exe_hash_unchanged(release_before)
        ),
    }
    VERIFY_JSON.write_text(json.dumps(verified, indent=2) + "\n", encoding="utf-8")
    lines.append(json.dumps(verified, ensure_ascii=False))
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(verified, indent=2))
    return 0 if verified["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
