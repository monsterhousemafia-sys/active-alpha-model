"""H1 mom_1_top12 benchmark — fehlende naive returns erzeugen."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from aa_backtest import (
    _naive_artifact_slug,
    run_naive_momentum_baseline_full,
    write_naive_baseline_artifacts,
)
from aa_safe_io import atomic_write_json
from tools.backfill_validated_run import _cfg_from_snapshot

VARIANT = "DAILY_ALPHA_H1"
BENCHMARK_VARIANT = "mom_1_top12"
_EVIDENCE_REL = Path("evidence/h1_benchmark_latest.json")
_LOG_REL = Path("evidence/h1_benchmark_generate.log")
_PROGRESS_REL = Path("evidence/h1_benchmark_progress.json")


def estimate_h1_benchmark_eta_de(*, rebalance_dates: int = 1867) -> str:
    """Realistische ETA für täglichen mom_1_top12-Nachlauf (king_h1, ~1 Rebalance/s)."""
    n = max(1, int(rebalance_dates))
    if n >= 1500:
        return f"~45–60 Min (king_h1, {n} Tages-Rebalances)"
    if n >= 500:
        return f"~15–30 Min (king_h1, {n} Rebalances)"
    return f"~5–12 Min (king_h1, {n} Rebalances)"
_PROC_MARKERS = (
    "tools/generate_h1_naive_benchmark.py",
    "analytics.h1_benchmark",
    "h1-benchmark",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _latest_run(root: Path) -> Optional[Path]:
    vroot = Path(root) / "validation_runs"
    if not vroot.is_dir():
        return None
    runs = sorted(
        (p for p in vroot.iterdir() if p.is_dir() and p.name.endswith(f"_{VARIANT}")),
        key=lambda p: p.name,
        reverse=True,
    )
    for run in runs:
        if (run / "strategy_daily_returns.csv").is_file():
            return run
    return None


def expected_benchmark_path(run_dir: Path, variant: str = BENCHMARK_VARIANT) -> Path:
    slug = _naive_artifact_slug(variant)
    return Path(run_dir) / f"{slug}_daily_returns.csv"


def is_benchmark_generating() -> bool:
    try:
        from analytics.h1_unified_connect import is_benchmark_generating_unified

        return is_benchmark_generating_unified()
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["pgrep", "-af", "generate_h1_naive_benchmark"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            return True
    except (OSError, subprocess.TimeoutExpired):
        pass
    return False


def benchmark_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    run_dir = _latest_run(root)
    if run_dir is None:
        return {
            "ok": False,
            "status": "no_run",
            "reason_de": "Kein abgeschlossener DAILY_ALPHA_H1-Lauf gefunden.",
        }
    target = expected_benchmark_path(run_dir)
    exists = target.is_file()
    generating = is_benchmark_generating()
    st = "ready" if exists else ("generating" if generating else "missing")
    progress_doc: Dict[str, Any] = {}
    progress_path = root / _PROGRESS_REL
    if progress_path.is_file():
        try:
            progress_doc = json.loads(progress_path.read_text(encoding="utf-8"))
        except Exception:
            progress_doc = {}
    eta_de = None if exists else (estimate_h1_benchmark_eta_de() if generating else "sofort startbar")
    if generating and progress_doc.get("progress_pct") is not None:
        eta_de = progress_doc.get("eta_de") or eta_de
    return {
        "ok": True,
        "status": st,
        "run_dir": str(run_dir.relative_to(root)).replace("\\", "/"),
        "benchmark_variant": BENCHMARK_VARIANT,
        "benchmark_path": str(target.relative_to(root)).replace("\\", "/"),
        "exists": exists,
        "generating": generating,
        "size_bytes": int(target.stat().st_size) if exists else 0,
        "eta_de": eta_de,
        "progress_path": str(_PROGRESS_REL).replace("\\", "/"),
        "progress_pct": progress_doc.get("progress_pct"),
        "rebalance_done": progress_doc.get("rebalance_done"),
        "rebalance_dates_total": progress_doc.get("rebalance_dates_total"),
    }


def _append_benchmark_log(root: Path, line: str) -> None:
    path = Path(root) / _LOG_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line.rstrip() + "\n")
        fh.flush()


def _apply_snapshot(cfg, snap: dict) -> None:
    for key, attr, cast in [
        ("start", "start", str),
        ("benchmark", "benchmark", str),
        ("shared_cache_dir", "shared_cache_dir", str),
        ("top_k", "top_k", int),
        ("rebalance_every", "rebalance_every", int),
        ("train_years", "train_years", int),
        ("horizon", "horizon", int),
        ("universe_mode", "universe_mode", str),
        ("universe_top_n", "universe_top_n", int),
        ("backtest_capital", "backtest_capital", float),
        ("fee_model", "fee_model", str),
        ("trading212_policy", "trading212_policy", str),
        ("slippage_bps", "slippage_bps", float),
        ("n_jobs", "n_jobs", str),
        ("cpu_cores", "cpu_cores", int),
        ("parallel_profile", "parallel_profile", str),
        ("parallel_backtest_backend", "parallel_backtest_backend", str),
    ]:
        if key in snap:
            setattr(cfg, attr, cast(snap[key]))


def _load_inputs(root: Path, run_dir: Path, snap: dict):
    cache_root = Path(snap.get("shared_cache_dir") or root / "model_output_sp500_pit_t212")
    returns_path = cache_root / "returns_cache.parquet"
    if not returns_path.is_file():
        raise RuntimeError(f"returns_cache fehlt: {returns_path}")
    features = pd.read_parquet(run_dir / "features.parquet")
    returns = pd.read_parquet(returns_path)
    if "date" in features.columns:
        features["date"] = pd.to_datetime(features["date"])
    if not isinstance(returns.index, pd.DatetimeIndex):
        returns.index = pd.to_datetime(returns.index)
    return features, returns


def _build_cfg(run_dir: Path, snap: dict, *, feature_gb: float = 0.0):
    cfg = _cfg_from_snapshot(run_dir)
    _apply_snapshot(cfg, snap)
    cfg.out_dir = str(run_dir)
    cfg.naive_detailed_reporting = True
    cfg.naive_detailed_variants = snap.get("naive_detailed_variants", BENCHMARK_VARIANT)
    try:
        from analytics.h1_king_runtime import apply_king_h1_profile

        apply_king_h1_profile(cfg, feature_gb=feature_gb)
    except Exception:
        if not getattr(cfg, "n_jobs", None) or str(cfg.n_jobs).strip() in {"", "0", "1"}:
            cfg.n_jobs = snap.get("n_jobs", "auto")
        if not getattr(cfg, "cpu_cores", None):
            cfg.cpu_cores = int(snap.get("cpu_cores", 32) or 32)
        if not getattr(cfg, "parallel_profile", None):
            cfg.parallel_profile = snap.get("parallel_profile", "high")
        setattr(cfg, "naive_benchmark_returns_only", True)
        setattr(cfg, "naive_parallel_prep", True)
        setattr(cfg, "naive_prep_backend", "process")
        setattr(cfg, "naive_gpu_returns", True)
    return cfg


def trigger_evaluate_after_benchmark(root: Path) -> Dict[str, Any]:
    """Nach Benchmark: Evaluate + Seal (h1-watch-Pfad)."""
    root = Path(root)
    try:
        from analytics.live_profile_governance import is_h1_backtest_sealed

        if is_h1_backtest_sealed(root):
            return {"ok": True, "skipped": True, "reason_de": "bereits sealed"}
    except Exception:
        pass
    try:
        from analytics.h1_watch import run_h1_watch

        watch = run_h1_watch(root)
        return {
            "ok": True,
            "sealed": bool(watch.get("sealed")),
            "status": watch.get("status"),
            "evaluation": watch.get("evaluation"),
        }
    except Exception as exc:
        return {"ok": False, "error_de": str(exc)[:200]}


def run_benchmark_sync(root: Path, *, evaluate_after: bool = True) -> Dict[str, Any]:
    root = Path(root)
    run_dir = _latest_run(root)
    if run_dir is None:
        return {"ok": False, "status": "no_run", "reason_de": "Kein H1-Run."}

    snap = {}
    for line in (run_dir / "run_config_snapshot.txt").read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, val = line.split("=", 1)
            snap[key.strip()] = val.strip()

    target = expected_benchmark_path(run_dir)
    if target.is_file():
        out = benchmark_status(root)
        out["message_de"] = "Benchmark bereits vorhanden."
        if evaluate_after:
            out["evaluate"] = trigger_evaluate_after_benchmark(root)
            if out["evaluate"].get("sealed"):
                out["message_de"] = "Benchmark da — H1 SEALED."
        return out

    t0 = time.monotonic()
    try:
        from analytics.h1_king_runtime import configure_king_h1_process

        configure_king_h1_process()
    except Exception:
        pass
    features, returns = _load_inputs(root, run_dir, snap)
    cfg = _build_cfg(run_dir, snap)
    feature_gb = 0.0
    try:
        from aa_parallel import _estimate_dataframe_gb, prepare_features_for_parallel_runtime

        features = prepare_features_for_parallel_runtime(features, cfg)
        feature_gb = _estimate_dataframe_gb(features)
        from analytics.h1_king_runtime import apply_king_h1_profile

        apply_king_h1_profile(cfg, feature_gb=feature_gb)
    except Exception:
        pass
    runtime_doc: Dict[str, Any] = {}
    try:
        from analytics.h1_king_runtime import king_h1_runtime_summary

        runtime_doc = king_h1_runtime_summary(cfg, feature_gb=feature_gb)
    except Exception as exc:
        runtime_doc = {"error_de": str(exc)[:120]}
    rebalance_n = 0
    try:
        dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
        first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
        rebalance_n = sum(1 for idx, d in enumerate(dates) if d >= first_possible and idx % int(cfg.rebalance_every) == 0)
    except Exception:
        rebalance_n = 1867
    setattr(cfg, "naive_progress_path", str(root / _PROGRESS_REL))
    _append_benchmark_log(
        root,
        f"--- naive run {_utc_now()} variant={BENCHMARK_VARIANT} rebalance_dates={rebalance_n} "
        f"eta={estimate_h1_benchmark_eta_de(rebalance_dates=rebalance_n)} ---",
    )
    atomic_write_json(
        root / _PROGRESS_REL,
        {
            "status": "running",
            "variant": BENCHMARK_VARIANT,
            "phase": "loading",
            "rebalance_dates_total": rebalance_n,
            "rebalance_done": 0,
            "progress_pct": 0,
            "eta_de": estimate_h1_benchmark_eta_de(rebalance_dates=rebalance_n),
            "gpu_returns": bool(getattr(cfg, "naive_gpu_returns", False)),
            "updated_at_utc": _utc_now(),
        },
    )
    result = run_naive_momentum_baseline_full(features, returns, cfg, None, variant=BENCHMARK_VARIANT)
    paths = write_naive_baseline_artifacts(run_dir, result)
    elapsed = round(time.monotonic() - t0, 1)
    if not target.is_file():
        return {
            "ok": False,
            "status": "failed",
            "reason_de": f"Export fehlgeschlagen — erwartet {target.name}",
            "elapsed_s": elapsed,
        }
    out = {
        "ok": True,
        "status": "ready",
        "run_dir": str(run_dir.relative_to(root)).replace("\\", "/"),
        "benchmark_path": str(target.relative_to(root)).replace("\\", "/"),
        "exists": True,
        "size_bytes": int(target.stat().st_size),
        "elapsed_s": elapsed,
        "written": [str(p.relative_to(root)).replace("\\", "/") for p in paths],
        "runtime": runtime_doc,
        "gpu": runtime_doc.get("gpu") or {},
        "message_de": (
            f"Benchmark {target.name} erzeugt ({elapsed}s, "
            f"{runtime_doc.get('prep_workers', '?')} Prep-Worker, "
            f"GPU={((runtime_doc.get('gpu') or {}).get('name') or 'CPU')})."
        ),
    }
    _append_benchmark_log(
        root,
        f"--- complete {_utc_now()} elapsed_s={elapsed} size_bytes={out['size_bytes']} path={target.name} ---",
    )
    atomic_write_json(
        root / _PROGRESS_REL,
        {
            "status": "complete",
            "variant": BENCHMARK_VARIANT,
            "progress_pct": 100,
            "elapsed_s": elapsed,
            "benchmark_path": str(target.relative_to(root)).replace("\\", "/"),
            "updated_at_utc": _utc_now(),
        },
    )
    atomic_write_json(root / _EVIDENCE_REL, {**out, "updated_at_utc": _utc_now()})
    if evaluate_after:
        out["evaluate"] = trigger_evaluate_after_benchmark(root)
        if out["evaluate"].get("sealed"):
            out["message_de"] = f"Benchmark {target.name} ({elapsed}s) — H1 SEALED."
        else:
            out["message_de"] = (
                f"Benchmark {target.name} ({elapsed}s) — Evaluate ausgeführt, Seal={out['evaluate'].get('sealed')}"
            )
    return out


def start_benchmark_background(root: Path) -> Dict[str, Any]:
    root = Path(root)
    status = benchmark_status(root)
    if not status.get("ok"):
        return status
    if status.get("exists"):
        status["message_de"] = "Benchmark bereits vorhanden."
        return status
    if status.get("generating"):
        status["message_de"] = "Benchmark-Generierung läuft bereits."
        return status

    py = root / ".venv/bin/python3"
    if not py.is_file():
        py = Path(sys.executable)
    log_path = root / _LOG_REL
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = None
    try:
        from analytics.h1_king_runtime import king_h1_subprocess_env

        env = king_h1_subprocess_env()
    except Exception:
        env = None
    try:
        from analytics.king_hardware import prepare_h1_hardware

        prepare_h1_hardware(root, phase="execute", auto_unload=False)
    except Exception:
        pass
    env = env or {}
    env.setdefault("AA_H1_GPU_RETURNS", "1")
    with open(log_path, "a", encoding="utf-8") as logf:
        logf.write(f"\n--- start {_utc_now()} king_h1 ---\n")
        proc = subprocess.Popen(
            [str(py), "-u", "tools/generate_h1_naive_benchmark.py", "--wait"],
            cwd=str(root),
            stdout=logf,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=env,
        )
    eta = estimate_h1_benchmark_eta_de()
    atomic_write_json(
        root / _PROGRESS_REL,
        {
            "status": "running",
            "variant": BENCHMARK_VARIANT,
            "phase": "starting",
            "progress_pct": 0,
            "pid": proc.pid,
            "eta_de": eta,
            "gpu_returns": env.get("AA_H1_GPU_RETURNS") == "1",
            "started_at_utc": _utc_now(),
            "updated_at_utc": _utc_now(),
        },
    )
    out = {
        "ok": True,
        "status": "started",
        "pid": proc.pid,
        "log_path": str(_LOG_REL).replace("\\", "/"),
        "progress_path": str(_PROGRESS_REL).replace("\\", "/"),
        "benchmark_path": status.get("benchmark_path"),
        "eta_de": eta,
        "message_de": (
            f"Benchmark-Job gestartet (PID {proc.pid}). "
            f"Log: {_LOG_REL}. Nach Abschluss: automatisch Evaluate+Seal."
        ),
    }
    atomic_write_json(root / _EVIDENCE_REL, {**out, "updated_at_utc": _utc_now()})
    return out


def ensure_h1_benchmark(root: Path, *, wait: bool = False) -> Dict[str, Any]:
    root = Path(root)
    status = benchmark_status(root)
    if not status.get("ok"):
        return status
    if status.get("exists"):
        status["message_de"] = "Benchmark bereit — Evaluate mit /h1-watch."
        return status
    if status.get("generating"):
        status["message_de"] = "Benchmark läuft — bitte warten, dann /h1-watch."
        return status
    if wait:
        return run_benchmark_sync(root)
    return start_benchmark_background(root)
