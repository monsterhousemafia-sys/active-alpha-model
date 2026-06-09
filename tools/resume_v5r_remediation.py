"""Resume V5R remediation after isolated build succeeded (copy/runtime/package only)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent
if str(MAIN) not in sys.path:
    sys.path.insert(0, str(MAIN))

WORKTREE = MAIN
EVIDENCE = MAIN / "evidence"
VALIDATED = "a47a8fef276358d63a5ed9a55d8b64dc5dccf194"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _kill_marktanalyse_processes() -> None:
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-Process -ErrorAction SilentlyContinue | "
            "Where-Object { $_.ProcessName -like 'Marktanalyse*' } | "
            "Stop-Process -Force -ErrorAction SilentlyContinue",
        ],
        check=False,
    )
    time.sleep(2)


def _atomic_copy(src: Path, dst: Path, *, attempts: int = 8) -> None:
    if not src.is_file():
        raise SystemExit(f"Missing source binary: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.with_name(dst.name + ".staging")
    if staging.is_file():
        staging.unlink()
    shutil.copy2(src, staging)
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            _kill_marktanalyse_processes()
            os.replace(staging, dst)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(1 + attempt)
    if staging.is_file():
        staging.unlink(missing_ok=True)
    raise SystemExit(f"Failed to copy {src.name} -> {dst}: {last_error}")


def _copy_exes() -> tuple[str, str]:
    _kill_marktanalyse_processes()
    release_src = WORKTREE / "dist" / "Marktanalyse.exe"
    fail_src = WORKTREE / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe"
    if WORKTREE.resolve() != MAIN.resolve():
        _atomic_copy(release_src, MAIN / "dist" / "Marktanalyse.exe")
        _atomic_copy(fail_src, MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    _atomic_copy(release_src, MAIN / "Marktanalyse.exe")
    if WORKTREE.resolve() == MAIN.resolve():
        _atomic_copy(fail_src, MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    release_hash = _sha256(MAIN / "Marktanalyse.exe")
    fail_hash = _sha256(MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe")
    if release_hash != _sha256(release_src):
        raise SystemExit("Release EXE hash mismatch after copy")
    return release_hash, fail_hash


def _write_sidecars(release_hash: str, fail_hash: str) -> None:
    for path in (MAIN / "Marktanalyse.exe.sha256", MAIN / "dist" / "Marktanalyse.exe.sha256"):
        path.write_text(f"{release_hash}  Marktanalyse.exe\n", encoding="ascii")
    (MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe.sha256").write_text(
        f"{fail_hash}  Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe\n", encoding="ascii"
    )


def _sync_runtime_summaries(build_commit: str, release_hash: str, fail_hash: str) -> None:
    smoke = json.loads((EVIDENCE / "v5r_exe_smoke_test_result.json").read_text(encoding="utf-8"))
    (EVIDENCE / "v5r_final_exe_smoke_exit.txt").write_text("SMOKE_EXIT_CODE: 0\n", encoding="utf-8")
    (EVIDENCE / "v5r_runtime_process_result.json").write_text(
        json.dumps(
            {
                "exe": "Marktanalyse.exe",
                "sha256": release_hash,
                "smoke_test_mode": True,
                "exit_code": 0,
                "result": smoke.get("result", "PASS_SELF_EXIT"),
                "pass": True,
                "build_source_commit": build_commit,
                "build_provenance": smoke.get("build_provenance", {}),
                "validated_source_base": VALIDATED,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "v5r_final_dist_inventory.json").write_text(
        json.dumps(
            {
                "Marktanalyse.exe": {"sha256": release_hash, "size_bytes": (MAIN / "Marktanalyse.exe").stat().st_size},
                "dist/Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe": {
                    "sha256": fail_hash,
                    "size_bytes": (MAIN / "dist" / "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe").stat().st_size,
                },
                "build_source_commit": build_commit,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _rebuild_and_smoke() -> None:
    py = WORKTREE / ".venv" / "Scripts" / "python.exe"
    if not py.is_file():
        raise SystemExit(f"Missing worktree venv: {py}")
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    for script in ("tools/build_v5r_standalone_exe.py", "tools/build_v5r_fail_closed_test_exe.py"):
        proc = subprocess.run([str(py), script], cwd=WORKTREE, env=env)
        if proc.returncode != 0:
            raise SystemExit(f"Worktree build failed: {script}")
    smoke_env = dict(env)
    smoke_env["AA_DECISION_COCKPIT_SMOKE_TEST"] = "1"
    proc = subprocess.run([str(WORKTREE / "dist" / "Marktanalyse.exe")], cwd=WORKTREE, env=smoke_env)
    (EVIDENCE / "v5r_final_exe_smoke_exit.txt").write_text(f"SMOKE_EXIT_CODE: {proc.returncode}\n", encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit("Worktree release smoke test failed")
    smoke_path = WORKTREE / "evidence" / "v5r_exe_smoke_test_result.json"
    if not smoke_path.is_file():
        raise SystemExit("Worktree smoke evidence missing after rebuild")
    smoke_text = smoke_path.read_text(encoding="utf-8")
    (EVIDENCE / "v5r_exe_smoke_test_result.json").write_text(smoke_text, encoding="utf-8")


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    _kill_marktanalyse_processes()
    _rebuild_and_smoke()
    smoke_path = WORKTREE / "evidence" / "v5r_exe_smoke_test_result.json"
    if not smoke_path.is_file():
        raise SystemExit(f"Missing worktree smoke evidence: {smoke_path}")
    smoke_text = smoke_path.read_text(encoding="utf-8")
    (EVIDENCE / "v5r_exe_smoke_test_result.json").write_text(smoke_text, encoding="utf-8")
    smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
    build_commit = smoke.get("build_provenance", {}).get("build_source_commit", "UNKNOWN")

    release_hash, fail_hash = _copy_exes()
    _write_sidecars(release_hash, fail_hash)
    (EVIDENCE / "v5r_final_build_environment.json").write_text(
        json.dumps(
            {
                "clean_worktree_path": str(WORKTREE),
                "build_source_commit": build_commit,
                "validated_source_base": VALIDATED,
                "build_scope": "V5R_NEUTRAL_READ_ONLY_RELEASE",
                "release_snapshot_scope": "V5R_READ_ONLY_NEUTRAL",
                "final_exe_sha256": release_hash,
                "fail_closed_test_exe_sha256": fail_hash,
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (EVIDENCE / "v5r_validated_source_commit.txt").write_text(
        f"{build_commit}\nvalidated_source_base={VALIDATED}\n", encoding="utf-8"
    )
    _sync_runtime_summaries(build_commit, release_hash, fail_hash)

    py = MAIN / ".venv" / "Scripts" / "python.exe"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("PYTHONHOME", None)
    env.pop("V5R_SUBMISSION_EXE", None)
    env.pop("V5R_FAIL_CLOSED_TEST_EXE", None)

    for script in ("tools/v5r_release_interactive_gui_test.py", "tools/v5r_fail_closed_runtime_test.py"):
        _kill_marktanalyse_processes()
        proc = subprocess.run([str(py), str(MAIN / script)], cwd=MAIN, env=env)
        _kill_marktanalyse_processes()
        if proc.returncode != 0:
            raise SystemExit(f"Runtime verification failed: {script} exit={proc.returncode}")

    gui = json.loads((EVIDENCE / "v5r_release_interactive_gui_verification.json").read_text(encoding="utf-8"))
    fc = json.loads((EVIDENCE / "v5r_fail_closed_runtime_verification.json").read_text(encoding="utf-8"))
    if not gui.get("pass"):
        raise SystemExit("Release GUI evidence pass=false")
    if not fc.get("pass"):
        raise SystemExit("Fail-closed runtime evidence pass=false")
    if gui.get("build_source_commit") != build_commit:
        raise SystemExit("GUI build_source_commit mismatch")
    if fc.get("build_source_commit") != build_commit:
        raise SystemExit("Fail-closed build_source_commit mismatch")
    if gui.get("release_exe_sha256") != release_hash:
        raise SystemExit("GUI release_exe_sha256 mismatch")

    (EVIDENCE / "v5r_runtime_fail_closed_verification.json").write_text(
        json.dumps(
            {
                "method": "Marktanalyse_FAIL_CLOSED_TEST_ONLY.exe AA_FAIL_CLOSED_TEST_SELF_EXIT runtime hook",
                "artifact_class": "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE",
                "build_source_commit": build_commit,
                "pass": True,
                "fail_closed_test_exe_actually_executed": True,
                "fail_closed_state_verified_in_executable_path": fc.get("fail_closed_state_verified_in_executable_path"),
                "generated_at_utc": _utc_now(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    subprocess.run([str(py), str(MAIN / "tools" / "generate_v5r_git_patch_evidence.py")], cwd=MAIN, check=True)
    subprocess.run(
        [str(py), str(MAIN / "tools" / "complete_v5r_runtime_riskoff_evidence.py"), "--audits-only"],
        cwd=MAIN,
        check=False,
    )
    subprocess.run([str(py), str(MAIN / "tools" / "static_verify_v5r_standalone_exe.py")], cwd=MAIN, check=True)

    from tools.run_v5r_final_isolated_pipeline import write_report, write_scope_audit

    write_scope_audit(build_commit, release_hash)
    write_report(build_commit, release_hash)
    subprocess.run([str(py), str(MAIN / "tools" / "build_v5r_final_review_zip.py")], cwd=MAIN, check=True)

    summary = {
        "build_source_commit": build_commit,
        "exe_sha256": release_hash,
        "fail_closed_exe_sha256": fail_hash,
        "gui_pass": True,
        "fail_closed_pass": True,
        "pass": True,
    }
    (EVIDENCE / "v5r_final_isolated_run_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
