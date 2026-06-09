#!/usr/bin/env python3
"""Start DAILY_ALPHA_H1 validation on WSL and monitor until evaluate/seal."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EVIDENCE_REL = Path("evidence/daily_alpha_h1_pipeline_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _wsl_repo_path(root: Path) -> str:
    drive = root.drive.rstrip(":").lower()
    tail = str(root.relative_to(root.anchor)).replace("\\", "/")
    return f"/mnt/{drive}/{tail}"


def _write_evidence(root: Path, payload: Dict[str, Any]) -> None:
    path = root / EVIDENCE_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at_utc"] = _utc_now()
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _start_wsl_backtest(root: Path) -> subprocess.Popen[str]:
    wsl_root = _wsl_repo_path(root)
    script = f"""
set -e
if [[ -x "$HOME/active_alpha_model/.venv/bin/python3" ]]; then
  cd "$HOME/active_alpha_model" && bash tools/wsl_conductor.sh m3-daily
elif [[ -x "{wsl_root}/.venv/bin/python3" ]]; then
  cd "{wsl_root}" && bash tools/wsl_conductor.sh m3-daily
else
  echo "[FEHLER] WSL venv fehlt — einmalig: bash tools/wsl_conductor.sh setup" >&2
  exit 2
fi
"""
    cmd = ["wsl", "bash", "-lc", script]
    print(f"[INFO] Starte WSL m3-daily (native oder {wsl_root})")
    return subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _resume_stamp_from_run(run_dir: Optional[str]) -> Optional[str]:
    if not run_dir:
        return None
    name = Path(run_dir).name
    if name.endswith("_DAILY_ALPHA_H1"):
        return name[: -len("_DAILY_ALPHA_H1")]
    return None


def _start_native_linux_backtest(root: Path, *, resume_stamp: Optional[str] = None) -> subprocess.Popen[str]:
    from aa_paths import resolve_venv_python, venv_python_ok
    from aa_runtime_profile import cleanup_stale_batch_lock
    from execution.linux_nvme_storage import apply_nvme_storage_env

    apply_nvme_storage_env(root)
    lock = cleanup_stale_batch_lock(root)
    if not lock.get("removed") and lock.get("reason") == "lock_active":
        print(f"[WARN] Batch-Lock aktiv (pid={lock.get('pid')}) — H1 erzwingt validation-Profil")
    py = resolve_venv_python(root) if venv_python_ok(root) else Path(sys.executable)
    cores = max(1, int(os.cpu_count() or 4))
    cmd = [
        str(py),
        "-u",
        "tools/run_validation_matrix.py",
        "--phase",
        "matrix",
        "--variant",
        "DAILY_ALPHA_H1",
        "--parallel-jobs",
        "1",
        "--cpu-cores",
        str(cores),
        "--runtime-profile",
        os.environ.get("AA_RUNTIME_PROFILE", "turbo"),
    ]
    if resume_stamp:
        cmd.extend(["--stamp", resume_stamp])
        print(f"[INFO] Setze H1-Run fort: validation_runs/{resume_stamp}_DAILY_ALPHA_H1")
    print(f"[INFO] Starte native Linux: {' '.join(cmd)}")
    env = os.environ.copy()
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_RUNTIME_PROFILE"] = os.environ.get("AA_RUNTIME_PROFILE", "turbo")
    env.setdefault("AA_PLAIN_PROGRESS_QUIET", "1")
    log_path = root / "evidence" / "daily_alpha_h1_backtest.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = log_path.open("a", encoding="utf-8")
    log_fh.write(f"\n=== native Linux start {_utc_now()} ===\n")
    log_fh.flush()
    try:
        from execution.h1_cpu_priority import h1_backtest_child_preexec

        preexec = h1_backtest_child_preexec
    except Exception:
        preexec = None
    try:
        from execution.h1_linux_boost import numa_exec_prefix

        prefix = numa_exec_prefix()
        if prefix:
            cmd = prefix + cmd
    except Exception:
        pass
    return subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        preexec_fn=preexec,
    )


def _pick_backtest_starter(root: Path, *, force_wsl: bool, force_windows: bool, force_native: bool):
    if force_windows:
        return _start_windows_backtest
    if force_wsl:
        return _start_wsl_backtest
    if force_native:
        return _start_native_linux_backtest
    try:
        from execution.linux_security_boundary import is_linux_host, is_wsl

        if is_linux_host() and not is_wsl():
            from aa_paths import venv_python_ok

            if venv_python_ok(root):
                return _start_native_linux_backtest
    except Exception:
        pass
    if sys.platform == "win32":
        return _start_windows_backtest
    return _start_wsl_backtest


def _start_windows_backtest(root: Path) -> subprocess.Popen[str]:
    py = sys.executable
    cmd = [
        py,
        "-u",
        "tools/run_validation_matrix.py",
        "--phase",
        "matrix",
        "--variant",
        "DAILY_ALPHA_H1",
        "--parallel-jobs",
        "1",
    ]
    print(f"[INFO] Starte Windows: {' '.join(cmd)}")
    return subprocess.Popen(
        cmd,
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _evaluate(root: Path, *, seal: bool) -> Dict[str, Any]:
    from datetime import datetime, timezone

    from aa_safe_io import atomic_write_json
    from tools.evaluate_daily_alpha_h1 import (
        EVIDENCE_REL as EVAL_EVIDENCE,
        _latest_run,
        _update_trial_ledger,
        evaluate_run,
    )

    run = _latest_run(root)
    if run is None:
        return {"ok": False, "reason": "no_completed_run"}
    evaluation = evaluate_run(root, run)
    evaluation["evaluated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    atomic_write_json(root / EVAL_EVIDENCE, evaluation)
    if seal and evaluation.get("pass_full_seal"):
        _update_trial_ledger(root, evaluation)
    return evaluation


def monitor_until_complete(
    root: Path,
    *,
    timeout_minutes: int = 480,
    poll_seconds: int = 120,
    seal_on_pass: bool = True,
    ignore_zombie_after_restart: bool = False,
) -> Dict[str, Any]:
    from analytics.live_profile_governance import h1_backtest_status, is_h1_backtest_sealed

    root = Path(root)
    deadline = time.time() + timeout_minutes * 60
    last_status: Optional[Dict[str, Any]] = None
    started_at = time.time()
    zombie_grace_s = max(600, poll_seconds * 3)
    zombie_restarts = 0
    max_zombie_restarts = 8

    while time.time() < deadline:
        last_status = h1_backtest_status(root)
        status = str(last_status.get("status") or "MISSING")
        run_dir = last_status.get("run_dir")
        print(f"[{_utc_now()}] H1 status={status} run={run_dir or '-'}")

        if status == "COMPLETE":
            evaluation = _evaluate(root, seal=seal_on_pass)
            sealed = is_h1_backtest_sealed(root)
            out = {
                "ok": True,
                "phase": "complete",
                "h1_backtest_status": last_status,
                "evaluation": evaluation,
                "sealed": sealed,
            }
            _write_evidence(root, out)
            return out

        if status == "ZOMBIE":
            in_grace = ignore_zombie_after_restart and (time.time() - started_at) < zombie_grace_s
            if in_grace:
                print("[INFO] Zombie-Grace nach Neustart — warte auf neuen Run …")
            elif zombie_restarts < max_zombie_restarts:
                zombie_restarts += 1
                print(f"[WARN] Zombie erkannt — Auto-Recovery #{zombie_restarts} …")
                try:
                    from analytics.h1_migration_guard import ensure_h1_migration_healthy

                    rec = ensure_h1_migration_healthy(root, auto_fix=True, poll_seconds=poll_seconds)
                    _write_evidence(
                        root,
                        {
                            "ok": bool(rec.get("ok")),
                            "phase": "recovering",
                            "h1_backtest_status": last_status,
                            "detail_de": str(rec.get("reply_de") or "Auto-Recovery"),
                            "recovery": rec,
                        },
                    )
                    started_at = time.time()
                    ignore_zombie_after_restart = True
                    time.sleep(min(poll_seconds, 30))
                    continue
                except Exception as exc:
                    print(f"[ERR] Auto-Recovery fehlgeschlagen: {exc}")
            else:
                out = {
                    "ok": False,
                    "phase": "zombie",
                    "h1_backtest_status": last_status,
                    "detail_de": "Backtest-Zombie — Auto-Recovery erschöpft (--restart).",
                }
                _write_evidence(root, out)
                return out

        time.sleep(poll_seconds)

    out = {
        "ok": False,
        "phase": "timeout",
        "h1_backtest_status": last_status,
        "timeout_minutes": timeout_minutes,
    }
    _write_evidence(root, out)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restart", action="store_true", help="Start backtest even if RUNNING")
    parser.add_argument("--native", action="store_true", help="Force native Linux backtest")
    parser.add_argument("--wsl", action="store_true", help="Force WSL backtest")
    parser.add_argument("--windows", action="store_true", help="Run matrix on Windows")
    parser.add_argument("--start-only", action="store_true", help="Start backtest and exit (no monitor loop)")
    parser.add_argument("--monitor-only", action="store_true", help="Only poll status + evaluate")
    parser.add_argument("--evaluate-only", action="store_true", help="Run evaluate_daily_alpha_h1 once")
    parser.add_argument("--no-seal", action="store_true", help="Do not seal on pass")
    parser.add_argument("--timeout-minutes", type=int, default=480)
    parser.add_argument("--poll-seconds", type=int, default=120)
    args = parser.parse_args()

    root = ROOT
    seal = not args.no_seal

    if args.evaluate_only:
        evaluation = _evaluate(root, seal=seal)
        print(json.dumps(evaluation, indent=2))
        return 0 if evaluation.get("pass_full_seal") or evaluation.get("ok") else 1

    from analytics.live_profile_governance import h1_backtest_status

    status_doc = h1_backtest_status(root)
    status = str(status_doc.get("status") or "MISSING")

    proc: Optional[subprocess.Popen[str]] = None
    restarted = False
    if not args.monitor_only:
        if status == "COMPLETE":
            print("[OK] H1 Backtest bereits COMPLETE — überspringe Start.")
        elif status == "RUNNING" and not args.restart:
            print(f"[INFO] H1 läuft bereits ({status_doc.get('run_dir')}) — nur Monitor.")
        else:
            resume_stamp = None
            from analytics.live_profile_governance import _h1_backtest_process_active

            run_path = root / str(status_doc.get("run_dir") or "")
            if status in ("ZOMBIE", "FAILED") or (
                status == "RUNNING" and run_path.is_dir() and not _h1_backtest_process_active(root, run_path)
            ):
                resume_stamp = _resume_stamp_from_run(status_doc.get("run_dir"))
                if resume_stamp:
                    print(f"[WARN] Setze H1 fort ({status_doc.get('run_dir')}) …")
                elif status == "ZOMBIE":
                    print(f"[WARN] Zombie-Run {status_doc.get('run_dir')} — Neustart …")
            starter = _pick_backtest_starter(
                root,
                force_wsl=args.wsl,
                force_windows=args.windows,
                force_native=args.native,
            )
            if starter is _start_native_linux_backtest:
                proc = starter(root, resume_stamp=resume_stamp)
            else:
                proc = starter(root)
            restarted = True

    if args.start_only and proc is not None:
        out = {
            "ok": True,
            "phase": "started",
            "pid": proc.pid,
            "detail_de": "H1-Backtest im Hintergrund — Status: python3 tools/ai_kernel.py h1-status",
        }
        _write_evidence(root, out)
        print(json.dumps(out, indent=2, ensure_ascii=False))
        return 0

    result = monitor_until_complete(
        root,
        timeout_minutes=args.timeout_minutes,
        poll_seconds=args.poll_seconds,
        seal_on_pass=seal,
        ignore_zombie_after_restart=restarted,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if proc is not None and proc.poll() is None:
        print("[INFO] Backtest-Prozess läuft weiter im Hintergrund.")

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
