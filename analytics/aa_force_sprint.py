"""Force-Sprint — H1 mit maximaler Kraft neu fahren (Checkpoint bleibt)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/aa_force_sprint_latest.json")


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _kill_h1_tree(root: Path) -> List[int]:
    killed: List[int] = []
    try:
        from execution.h1_cpu_priority import find_h1_backtest_pids

        pids = find_h1_backtest_pids(root)
    except Exception:
        pids = []
    patterns = (
        "run_validation_matrix.py.*DAILY_ALPHA_H1",
        "active_alpha_model.py.*DAILY_ALPHA_H1",
        "run_daily_alpha_h1_pipeline.py",
    )
    for pattern in patterns:
        try:
            proc = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            for line in (proc.stdout or "").splitlines():
                try:
                    pids.append(int(line.strip()))
                except ValueError:
                    pass
        except (OSError, subprocess.TimeoutExpired):
            pass
    for pid in sorted(set(pids)):
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except OSError:
            pass
    if killed:
        time.sleep(1.5)
        for pid in killed:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
    return killed


def _stop_optional_user_services() -> List[str]:
    stopped: List[str] = []
    for unit in ("active-alpha-preview-hub.service", "active-alpha-remote-tunnel.service"):
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-active", unit],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            )
            if (proc.stdout or "").strip() == "active":
                subprocess.run(["systemctl", "--user", "stop", unit], check=False, timeout=8)
                stopped.append(unit)
        except (OSError, subprocess.TimeoutExpired):
            pass
    return stopped


def _h1_run_dir(root: Path, status: Dict[str, Any]) -> Optional[Path]:
    rel = str(status.get("run_dir") or "").strip()
    if not rel.endswith("_DAILY_ALPHA_H1"):
        return None
    return root / rel


def _checkpoint_resume_pending(run_dir: Path) -> Tuple[bool, Optional[Dict[str, Any]]]:
    meta_path = run_dir / "path_sim_checkpoint_meta.json"
    if not (
        (run_dir / "features.parquet").is_file()
        and (run_dir / "prediction_cache.pkl").is_file()
        and meta_path.is_file()
    ):
        return False, None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, None
    last_n = int(meta.get("last_n", -1))
    n_daily = int(meta.get("n_daily", 0))
    if n_daily <= 0 or last_n >= n_daily:
        return False, meta
    if (run_dir / "strategy_daily_returns.csv").is_file():
        return False, meta
    return True, meta


def _argv_from_validation_log(run_dir: Path) -> Optional[List[str]]:
    log = run_dir / "validation_run.log"
    if not log.is_file():
        return None
    line = log.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    marker = "active_alpha_model.py"
    pos = line.find(marker)
    if pos < 0:
        return None
    tail = line[pos + len(marker) :].strip()
    return tail.split() if tail else None


def _build_path_only_resume_cmd(root: Path, run_dir: Path, cores: int) -> List[str]:
    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    argv = _argv_from_validation_log(run_dir)
    if argv:
        patched: List[str] = []
        skip = False
        drop_flags = {
            "--force-rebuild-predictions",
            "--force-rebuild-features",
            "--backtest-scope",
            "--prediction-cache-dir",
        }
        drop_with_value = {"--n-jobs", "--cpu-cores", "--parallel-backtest-backend"}
        for tok in argv:
            if skip:
                skip = False
                continue
            if tok in drop_flags:
                continue
            if tok in drop_with_value:
                skip = True
                continue
            patched.append(tok)
        if "--reuse-prediction-cache" not in patched:
            patched.append("--reuse-prediction-cache")
        if "--path-sim-checkpoint" not in patched:
            patched.append("--path-sim-checkpoint")
        nj = "auto" if os.name != "nt" else "1"
        patched.extend(
            [
                "--n-jobs",
                nj,
                "--cpu-cores",
                str(cores),
                "--parallel-backtest-backend",
                "process",
                "--backtest-scope",
                "path-only",
                "--prediction-cache-dir",
                str(run_dir),
            ]
        )
        model_argv = patched
    else:
        model_argv = [
            "--mode",
            "backtest",
            "--out-dir",
            str(run_dir),
            "--reuse-prediction-cache",
            "--path-sim-checkpoint",
            "--backtest-scope",
            "path-only",
            "--prediction-cache-dir",
            str(run_dir),
            "--n-jobs",
            "1",
            "--cpu-cores",
            str(cores),
        ]
    return [str(py), "-u", str(root / "active_alpha_model.py"), *model_argv]


def run_force_h1_sprint(root: Path) -> Dict[str, Any]:
    """Turbo-Lean + H1-Kill + Neustart mit allen Kernen, kein Feature-Rebuild."""
    root = Path(root)
    from analytics.operator_sovereignty import assert_privileged_action

    ok, block = assert_privileged_action(root, "h1-force")
    if not ok:
        return {"schema_version": 1, "ok": False, **block}
    from analytics.live_profile_governance import h1_backtest_status

    status = h1_backtest_status(root)
    from analytics.aa_lean_linux import enable_lean_mode

    lean = enable_lean_mode(root, turbo=True)
    stopped = _stop_optional_user_services()
    killed = _kill_h1_tree(root)

    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    cores = max(1, int(os.cpu_count() or 8))
    env = os.environ.copy()
    env["AA_RUNTIME_PROFILE"] = "turbo"
    env["AA_FORCE_H1_TURBO"] = "1"
    env["AA_PROJECT_ROOT"] = str(root)
    env["AA_LINUX_NATIVE_APP"] = "1"
    env["AA_CPU_CORES"] = str(cores)

    from aa_runtime_profile import cleanup_stale_batch_lock

    cleanup_stale_batch_lock(root)

    h1_dir = _h1_run_dir(root, status)
    resume_pending, ck_meta = (False, None)
    if h1_dir is not None:
        resume_pending, ck_meta = _checkpoint_resume_pending(h1_dir)

    stamp = "20260606T102626Z"
    if h1_dir is not None:
        stamp = h1_dir.name[: -len("_DAILY_ALPHA_H1")]

    if resume_pending and h1_dir is not None:
        cmd = _build_path_only_resume_cmd(root, h1_dir, cores)
        mode = "path-only-checkpoint"
        headline = (
            f"Force-Sprint path-only — Checkpoint Rebalance "
            f"{int(ck_meta.get('last_n', 0)) + 1} ({int(ck_meta.get('n_daily', 0))} Tage)"
        )
        run_log = h1_dir / "validation_run.log"
    else:
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
            "--stamp",
            stamp,
            "--runtime-profile",
            "turbo",
        ]
        mode = "matrix-turbo"
        headline = f"Force-Sprint — H1 neu mit {cores} Kernen (Checkpoint bleibt)"
        run_log = root / "evidence" / "daily_alpha_h1_backtest.log"

    log_fh = run_log.open("a", encoding="utf-8")
    log_fh.write(f"\n=== force sprint {_utc_now()} mode={mode} cores={cores} ===\n")
    if mode == "path-only-checkpoint":
        log_fh.write(" ".join(cmd) + "\n")
    log_fh.flush()
    proc = subprocess.Popen(
        cmd,
        cwd=str(root),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    doc = {
        "schema_version": 1,
        "ok": True,
        "killed_pids": killed,
        "stopped_services": stopped,
        "lean": lean.get("headline_de"),
        "h1_status_before": status,
        "restart_pid": proc.pid,
        "cpu_cores": cores,
        "profile": "turbo",
        "mode": mode,
        "checkpoint_meta": ck_meta,
        "headline_de": headline,
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc
