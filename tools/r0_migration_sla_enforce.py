#!/usr/bin/env python3
"""Enforce M1 SLA: single fastest R0 (path-only+cache), turbo R3+M1 after R0 PASS."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CANONICAL_R0_STAMP = "20260604T153044Z"
SLA_DEADLINE = "2026-06-04T21:17:42+00:00"
REPORT = ROOT / "evidence" / "r0_migration" / "sla_enforce.json"


def _is_canonical_backtest_cmd(cmd: str, root: Path) -> bool:
    return "active_alpha_model.py" in cmd and _canonical_stamp(root) in cmd


def sla_fast_path_active(root: Path) -> bool:
    sla = root / "control" / "r0_migration" / "m1_sla_6h.json"
    if not sla.is_file():
        return False
    try:
        data = json.loads(sla.read_text(encoding="utf-8"))
    except Exception:
        return False
    return bool(data.get("deadline_enforced") and data.get("canonical_r0_stamp"))


def _canonical_stamp(root: Path) -> str:
    sla = root / "control" / "r0_migration" / "m1_sla_6h.json"
    if sla.is_file():
        try:
            stamp = str(json.loads(sla.read_text(encoding="utf-8")).get("canonical_r0_stamp") or "").strip()
            if stamp:
                return stamp
        except Exception:
            pass
    return CANONICAL_R0_STAMP


def canonical_r0_dir(root: Path) -> Path:
    return root / "validation_runs" / f"{_canonical_stamp(root)}_R0_LEGACY_ENSEMBLE"


def canonical_r0_incomplete(root: Path) -> bool:
    if not sla_fast_path_active(root):
        return False
    from tools.run_validation_matrix import _is_pass_complete

    r0 = canonical_r0_dir(root)
    return r0.is_dir() and not _is_pass_complete(r0)


def _write_canonical_batch_lock(root: Path, pid: int) -> None:
    from aa_runtime_profile import BATCH_LOCK_FILE
    from aa_safe_io import atomic_write_text

    line = f"{int(pid)} validation_{_canonical_stamp(root)} {_utc_now()}\n"
    atomic_write_text(root / BATCH_LOCK_FILE, line)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sla_hours_left(root: Path) -> float:
    sla_path = root / "control" / "r0_migration" / "m1_sla_6h.json"
    sla = json.loads(sla_path.read_text(encoding="utf-8"))
    deadline = datetime.fromisoformat(str(sla["sla_deadline_utc"]).replace("Z", "+00:00"))
    return (deadline - datetime.now(timezone.utc)).total_seconds() / 3600.0


def _log_idle_minutes(path: Path) -> float | None:
    if not path.is_file():
        return None
    import time

    return (time.time() - path.stat().st_mtime) / 60.0


def _canonical_r0_stalled(root: Path, r0_dir: Path) -> bool:
    """True when cache exists but returns missing and workers/logs look stuck."""
    if not r0_dir.is_dir():
        return False
    if (r0_dir / "strategy_daily_returns.csv").is_file():
        return False
    if not (r0_dir / "prediction_cache.pkl").is_file():
        return False
    turbo_log = r0_dir / "validation_run_path_turbo.log"
    run_log = r0_dir / "validation_run.log"
    logs: list[Path] = []
    if turbo_log.is_file() and (
        not run_log.is_file() or turbo_log.stat().st_mtime >= run_log.stat().st_mtime
    ):
        logs = [turbo_log]
    elif run_log.is_file():
        logs = [run_log]
    idle_vals = [_log_idle_minutes(p) for p in logs]
    if idle_vals and min(idle_vals) < 20.0:
        return False
    from tools.r0_migration_runtime import backtest_workers_cpu_active

    if idle_vals and max(idle_vals) > 10.0:
        return True
    return not bool(backtest_workers_cpu_active(root, sample_sec=2.0).get("active"))


def enforce_sla_fast_path(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_killer_pack import apply_killer_pack

    killer = apply_killer_pack(root)
    from aa_runtime_profile import cleanup_stale_batch_lock, is_batch_work_active
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_commander import _kill_pids, _migration_pids
    from tools.r0_migration_runtime import count_validation_matrix_processes, matrix_work_in_progress
    from tools.run_r0_migration_phase_m1 import build_returns_manifest, launch_validation_matrix
    from tools.run_validation_matrix import _is_pass_complete
    from tools.r0_migration_post_r0_turbo import maybe_relaunch_matrix_turbo_after_r0

    out: Dict[str, Any] = {
        "at_utc": _utc_now(),
        "sla_h_left": round(_sla_hours_left(root), 2),
        "actions": [],
        "killer_pack": killer,
    }
    r0_dir = canonical_r0_dir(root)
    r0_done = r0_dir.is_dir() and _is_pass_complete(r0_dir)

    import time

    kills: List[int] = []
    for p in _migration_pids():
        cmd = p.get("cmd", "")
        pid = int(p["pid"])
        if any(
            x in cmd
            for x in (
                "run_validation_matrix.py",
                "run_r0_migration_watch_loop",
                "run_r0_migration_phase_m1",
                "run_r0_migration_m1_matrix",
                "eliminate_blockers",
            )
        ):
            kills.append(pid)
            continue
        if "active_alpha_model.py" not in cmd:
            continue
        if _is_canonical_backtest_cmd(cmd, root):
            continue
        if "validation_runs" not in cmd:
            continue
        kills.append(pid)
    canon_before = [
        int(p["pid"]) for p in _migration_pids() if _is_canonical_backtest_cmd(p.get("cmd", ""), root)
    ]
    if _canonical_r0_stalled(root, r0_dir) and canon_before:
        for pid in canon_before:
            kills.append(pid)
        out["actions"].append({"canonical_r0_stalled": True, "pids": canon_before})
    kills = sorted(set(kills))
    if kills:
        out["actions"].append({"killed_duplicate_r0_or_matrix": _kill_pids(kills)})
    cleanup_stale_batch_lock(root)
    guard = root / "control" / "r0_migration" / "matrix_launch_guard.lock"
    try:
        guard.unlink(missing_ok=True)
    except OSError:
        pass
    from tools.r0_migration_prune_validation_junk import plan_prune
    import shutil

    for entry in plan_prune(root).get("remove") or []:
        junk = root / "validation_runs" / entry["dir"]
        if junk.is_dir():
            shutil.rmtree(junk, ignore_errors=True)
            out["actions"].append({"removed_junk_dir": entry["dir"]})
    time.sleep(2)
    cleanup_stale_batch_lock(root)

    manifest = build_returns_manifest(root)
    if manifest.get("all_m1_variants_integrity_pass"):
        out["verdict"] = "READY_FOR_SEAL"
        return out

    if r0_done:
        relaunch = maybe_relaunch_matrix_turbo_after_r0(root)
        out["actions"].append({"post_r0_turbo": relaunch})
        out["verdict"] = relaunch.get("action", "post_r0")
        return out

    from tools.r0_migration_runtime import backtest_workers_cpu_active

    canon_workers = [
        int(p["pid"]) for p in _migration_pids() if _is_canonical_backtest_cmd(p.get("cmd", ""), root)
    ]
    canon_runners = [
        int(p["pid"])
        for p in _migration_pids()
        if "r0_migration_run_canonical_r0.py" in p.get("cmd", "")
    ]
    if canon_runners and not canon_workers:
        out["canonical_runners"] = canon_runners
        out["verdict"] = "HOLD_CANONICAL_R0"
        out["matrix_n"] = count_validation_matrix_processes(root)
        out["batch_active"] = is_batch_work_active(root)
        atomic_write_json(REPORT, out)
        return out
    if canon_workers:
        if len(canon_workers) > 1:
            keep = max(canon_workers)
            dup = _kill_pids([p for p in canon_workers if p != keep])
            out["actions"].append({"deduped_canonical_workers": dup, "keep": keep})
            canon_workers = [keep]
        from tools.r0_migration_killer_pack import apply_killer_pack

        out["canonical_workers"] = canon_workers
        out["killer_reboost"] = apply_killer_pack(root)
        out["verdict"] = "HOLD_CANONICAL_R0"
        out["matrix_n"] = count_validation_matrix_processes(root)
        out["batch_active"] = is_batch_work_active(root)
        atomic_write_json(REPORT, out)
        return out

    canon_active = bool(backtest_workers_cpu_active(root, sample_sec=1.5).get("active"))
    has_cache = (r0_dir / "prediction_cache.pkl").is_file()
    if has_cache and not canon_active:
        out["actions"].append({"path_only_turbo": _launch_path_only_r0(root, r0_dir)})
        out["verdict"] = "PATH_ONLY_R0_STARTED"
    elif canon_active:
        from tools.r0_migration_killer_pack import apply_killer_pack

        out["killer_reboost"] = apply_killer_pack(root)
        out["verdict"] = "HOLD_CANONICAL_R0"
    elif has_cache:
        out["actions"].append({"path_only_turbo": _launch_path_only_r0(root, r0_dir)})
        out["verdict"] = "PATH_ONLY_R0_STARTED"
    else:
        out["verdict"] = "STALLED_NEED_PATH_R0"
    out["matrix_n"] = count_validation_matrix_processes(root)
    out["batch_active"] = is_batch_work_active(root)

    atomic_write_json(REPORT, out)
    return out


def _argv_from_canonical_validation_log(r0_dir: Path) -> List[str] | None:
    """Replay argv from the run that produced prediction_cache.pkl (config fingerprint match)."""
    log = r0_dir / "validation_run.log"
    if not log.is_file():
        return None
    line = log.read_text(encoding="utf-8", errors="replace").splitlines()[0].strip()
    marker = "active_alpha_model.py"
    pos = line.find(marker)
    if pos < 0:
        return None
    tail = line[pos + len(marker) :].strip()
    return tail.split() if tail else None


def _build_path_only_cmd(root: Path, r0_dir: Path) -> List[str]:
    import os

    cores = max(1, int(os.cpu_count() or 32))
    # Windows path-only: single worker avoids broken process-pool spawn (WinError 5 / EOFError).
    if os.name == "nt":
        backend = "thread"
        job_count = "1"
    else:
        backend = "process"
        job_count = str(min(16, cores))

    argv = _argv_from_canonical_validation_log(r0_dir)
    if argv:
        patched: List[str] = []
        skip = False
        drop_flags = {
            "--force-rebuild-predictions",
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
        patched.extend(
            [
                "--n-jobs",
                job_count,
                "--cpu-cores",
                str(cores),
                "--parallel-backtest-backend",
                backend,
                "--backtest-scope",
                "path-only",
                "--prediction-cache-dir",
                str(r0_dir),
            ]
        )
        model_argv = patched
    else:
        model_argv = [
            "--mode",
            "backtest",
            "--ticker-source",
            "sp500_pit",
            "--membership-file",
            "ticker_membership.csv",
            "--membership-mode",
            "strict",
            "--benchmark",
            "SPY",
            "--start",
            "2012-01-01",
            "--universe-mode",
            "diy_pit_liquidity",
            "--universe-top-n",
            "100",
            "--rebalance-every",
            "5",
            "--horizon",
            "10",
            "--train-years",
            "7",
            "--ml-retrain-every",
            "2",
            "--alpha-model-mode",
            "ensemble",
            "--exposure-controller",
            "gradual_alpha",
            "--beta-cap-mode",
            "dynamic",
            "--cluster-mode",
            "static",
            "--cluster-constraint-mode",
            "static_only",
            "--slippage-bps",
            "2",
            "--market-impact-bps",
            "0",
            "--fee-model",
            "trading212_us",
            "--backtest-capital",
            "100000",
            "--research-backtest-capital",
            "100000",
            "--reproducibility-mode",
            "strict",
            "--random-seed",
            "42",
            "--n-jobs",
            job_count,
            "--cpu-cores",
            str(cores),
            "--parallel-profile",
            "high",
            "--parallel-backtest-backend",
            backend,
            "--reuse-feature-cache",
            "--skip-download-if-cached",
            "--skip-feature-parquet-write",
            "--no-plot",
            "--no-gui",
            "--plain-progress",
            "--no-naive-momentum-baseline",
            "--no-statistical-diagnostics",
            "--no-custom-benchmarks",
            "--minimal-backtest-reporting",
            "--no-run-manifest",
            "--no-naive-overlap",
            "--backtest-scope",
            "path-only",
            "--prediction-cache-dir",
            str(r0_dir),
            "--shared-cache-dir",
            str(root / "robustness_results_trading212" / "_shared_cache"),
            "--out-dir",
            str(r0_dir),
            "--risk-off-selection-mode",
            "legacy",
            "--risk-off-gate-mode",
            "legacy",
            "--reuse-prediction-cache",
        ]
    return [
        str(root / ".venv" / "Scripts" / "python.exe"),
        "-u",
        str(root / "active_alpha_model.py"),
        *model_argv,
    ]


def _launch_path_only_r0(root: Path, r0_dir: Path) -> Dict[str, Any]:
    import os
    import subprocess

    from tools.r0_migration_commander import _migration_pids

    for p in _migration_pids():
        cmd = p.get("cmd", "")
        if "r0_migration_run_canonical_r0.py" in cmd:
            return {"skipped": "canonical_runner_already_running", "pid": int(p["pid"])}
        if _is_canonical_backtest_cmd(cmd, root):
            return {"skipped": "path_only_already_running", "pid": int(p["pid"])}

    py = root / ".venv" / "Scripts" / "python.exe"
    script = root / "tools" / "r0_migration_run_canonical_r0.py"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.Popen(
        [str(py), str(script)],
        cwd=str(root),
        creationflags=flags,
    )
    _write_canonical_batch_lock(root, 0)
    return {
        "started": "subprocess",
        "pid": int(proc.pid),
        "log": str(r0_dir / "validation_run_path_turbo.log"),
        "report": str(root / "evidence" / "r0_migration" / "canonical_r0_run.json"),
        "argv_from_log": bool(_argv_from_canonical_validation_log(r0_dir)),
    }


def main() -> int:
    result = enforce_sla_fast_path(ROOT)
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
