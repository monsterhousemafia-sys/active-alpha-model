#!/usr/bin/env python3
"""Phase-10 validation orchestrator: research matrix + optional cost stress."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_runtime_profile import (  # noqa: E402
    PROFILES,
    BatchWorkGuard,
    RuntimeProfileSpec,
    acquire_batch_work,
    resolve_effective_profile,
    subprocess_env_for_profile,
    variant_worker_budget,
)
from aa_single_instance import is_interactive_session_running  # noqa: E402

VALIDATION_ROOT = ROOT / "validation_runs"
SHARED_CACHE = ROOT / "model_output_sp500_pit_t212"
if not (SHARED_CACHE / "feature_cache").exists():
    alt = ROOT / "robustness_results_trading212" / "_shared_cache"
    if alt.is_dir():
        SHARED_CACHE = alt

PYTHON = sys.executable


def _default_cpu_cores() -> int:
    raw = os.environ.get("AA_CPU_CORES", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    return max(1, int(os.cpu_count() or 16))


DEFAULT_CPU = _default_cpu_cores()

BASE_CMD = [
    PYTHON,
    str(ROOT / "active_alpha_model.py"),
    "--mode",
    "both",
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
    "auto",
    "--cpu-cores",
    str(DEFAULT_CPU),
    "--parallel-profile",
    "high",
    "--parallel-backtest-backend",
    "process",
    "--reuse-feature-cache",
    "--skip-download-if-cached",
    "--skip-feature-parquet-write",
    "--no-plot",
    "--no-gui",
    "--plain-progress",
]

# Validation matrix: skip work that does not affect integrity or variant comparison.
# Reference R3 run showed ~720s in Phase C (naive) alone — omit for matrix/cost.
VALIDATION_FAST_FLAGS = [
    "--no-naive-momentum-baseline",
    "--no-statistical-diagnostics",
    "--no-custom-benchmarks",
    "--minimal-backtest-reporting",
    "--no-run-manifest",
    "--no-naive-overlap",
]

DEFAULT_PARALLEL_JOBS = max(2, min(4, int(os.environ.get("AA_VALIDATION_PARALLEL_JOBS", "3") or 3)))


def _m1_race_mode_active() -> bool:
    p = ROOT / "control" / "r0_migration" / "m1_race_mode.json"
    if not p.is_file():
        return False
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("enabled"))
    except Exception:
        return False


def _resolve_hardware_context(
    *,
    profile_name: str,
    parallel_jobs: int,
    cpu_cores: int,
) -> Tuple[RuntimeProfileSpec, int, int, str]:
    interactive = is_interactive_session_running(ROOT) and not _m1_race_mode_active()
    spec = resolve_effective_profile(profile_name, interactive_active=interactive)
    jobs, per_job = variant_worker_budget(cpu_cores, parallel_jobs, profile=spec)
    note = spec.name
    if interactive and profile_name not in {"background", "exe"}:
        note = f"{spec.name} (Marktanalyse aktiv — gedrosselt)"
    return spec, jobs, per_job, note


def _worker_budget(parallel_jobs: int, cpu_cores: int, profile: RuntimeProfileSpec) -> Tuple[str, int]:
    jobs, per_job = variant_worker_budget(cpu_cores, parallel_jobs, profile=profile)
    if profile.n_jobs_cap is not None:
        n_jobs = "1"
    elif jobs == 1:
        n_jobs = "auto"
    else:
        n_jobs = str(per_job)
    return n_jobs, per_job


MATRIX: List[Dict[str, Any]] = [
    {
        "key": "R0_LEGACY_ENSEMBLE",
        "risk_off_selection_mode": "legacy",
        "risk_off_gate_mode": "legacy",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R1_GATE_BASE_ONLY",
        "risk_off_selection_mode": "legacy",
        "risk_off_gate_mode": "base_only",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R2_MOM_BLEND_REPLACE",
        "risk_off_selection_mode": "mom_blend_replace",
        "risk_off_gate_mode": "legacy",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R3_w070_q070_noexit",
        "risk_off_selection_mode": "mom_blend_blend",
        "risk_off_momentum_variant": "mom_blend_top12",
        "risk_off_momentum_weight": "0.70",
        "risk_off_gate_mode": "momentum_rescue",
        "risk_off_momentum_rescue_quantile": "0.70",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R3_w075_q065_noexit",
        "risk_off_selection_mode": "mom_blend_blend",
        "risk_off_momentum_variant": "mom_blend_top12",
        "risk_off_momentum_weight": "0.75",
        "risk_off_gate_mode": "momentum_rescue",
        "risk_off_momentum_rescue_quantile": "0.65",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R4_w070_q070_forceexit",
        "risk_off_selection_mode": "mom_blend_blend",
        "risk_off_momentum_variant": "mom_blend_top12",
        "risk_off_momentum_weight": "0.70",
        "risk_off_gate_mode": "momentum_rescue",
        "risk_off_momentum_rescue_quantile": "0.70",
        "risk_off_force_exit_enabled": True,
    },
    {
        "key": "M1_MOM_BLEND_MATCHED_CONTROLS",
        "risk_off_selection_mode": "legacy",
        "risk_off_gate_mode": "legacy",
        "risk_off_force_exit_enabled": False,
        "naive_detailed_reporting": True,
        "naive_detailed_variants": "mom_blend_matched_controls",
    },
    {
        "key": "R5_rank_only_train5",
        "alpha_model_mode": "rank_only",
        "train_years": "5",
        "top_k": "15",
        "risk_off_selection_mode": "mom_blend_blend",
        "risk_off_momentum_variant": "mom_blend_top12",
        "risk_off_momentum_weight": "0.75",
        "risk_off_gate_mode": "momentum_rescue",
        "risk_off_momentum_rescue_quantile": "0.65",
        "risk_off_force_exit_enabled": False,
    },
    {
        # Echtes Tages-Alpha (option B): ensemble ML on a 1-day horizon, rebalanced
        # daily, benchmarked against 1-day momentum (mom_1_top12). Heavy run, gated
        # behind an explicit go (see control/r0_migration/alpha_objective.json).
        "key": "DAILY_ALPHA_H1",
        "horizon": "1",
        "rebalance_every": "1",
        "force_rebuild_features": True,
        "alpha_model_mode": "ensemble",
        "risk_off_selection_mode": "legacy",
        "risk_off_gate_mode": "legacy",
        "risk_off_force_exit_enabled": False,
        "benchmark_variant": "mom_1_top12",
    },
]

COST_STRESS: List[Dict[str, Any]] = [
    {"suffix": "cost_s2_i0", "slippage_bps": "2", "market_impact_bps": "0"},
    {"suffix": "cost_s5_i0", "slippage_bps": "5", "market_impact_bps": "0"},
    {"suffix": "cost_s10_i5", "slippage_bps": "10", "market_impact_bps": "5"},
    {"suffix": "cost_s20_i10", "slippage_bps": "20", "market_impact_bps": "10"},
]

FINALIST_KEYS = ("R3_w070_q070_noexit", "R3_w075_q065_noexit", "R4_w070_q070_forceexit")
CHALLENGER_COST_KEYS = ("R5_rank_only_train5",)

M1_PHASE_MATRIX_KEYS = (
    "R0_LEGACY_ENSEMBLE",
    "R3_w075_q065_noexit",
    "M1_MOM_BLEND_MATCHED_CONTROLS",
)
M1_VARIANT_KEY = "M1_MOM_BLEND_MATCHED_CONTROLS"
FAST_SEAL_FLAG = ROOT / "control" / "r0_migration" / "m1_fast_seal.flag"
POST_M1_PERF = ROOT / "control" / "r0_migration" / "post_m1_perf.json"


def _post_m1_perf_active() -> bool:
    if os.environ.get("AA_POST_M1_PERF", "").strip() == "1":
        return True
    if not POST_M1_PERF.is_file():
        return False
    try:
        st = str(json.loads(POST_M1_PERF.read_text(encoding="utf-8")).get("status", ""))
        return st.startswith("READY")
    except Exception:
        return False


def _m1_fast_seal_active() -> bool:
    return FAST_SEAL_FLAG.is_file()


def _m1_naive_detailed_enabled(variant: Dict[str, Any]) -> bool:
    """Matched-controls naive export runs BEFORE strategy CSV and is slow.

    When m1_fast_seal.flag is present the seal gate needs only the strategy CSV;
    skip the heavy control-series export for this launch (backfilled out-of-band).
    """
    if str(variant.get("key", "")) != M1_VARIANT_KEY:
        return bool(variant.get("naive_detailed_reporting", False))
    if _m1_fast_seal_active():
        return False
    return bool(variant.get("naive_detailed_reporting", False))


def _is_m1_phase_matrix(variants: List[Dict[str, Any]]) -> bool:
    keys = {str(v["key"]) for v in variants}
    return keys == set(M1_PHASE_MATRIX_KEYS)


def _order_m1_phase_variants(variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    by_key = {str(v["key"]): v for v in variants}
    return [by_key[k] for k in M1_PHASE_MATRIX_KEYS if k in by_key]


def _check_m1_matched_controls(out_dir: Path) -> Optional[str]:
    """Return error message if M1 matched-controls artifact missing or calendar diverges."""
    import pandas as pd

    from aa_integrity import validate_matched_controls_calendar_integrity

    strat_path = out_dir / "strategy_daily_returns.csv"
    matched_path = out_dir / "mom_blend_matched_controls_daily_returns.csv"
    if not matched_path.is_file():
        return "mom_blend_matched_controls_daily_returns.csv missing"
    if not strat_path.is_file():
        return "strategy_daily_returns.csv missing for M1 calendar check"
    strat = pd.read_csv(strat_path, index_col=0)
    scol = "strategy_return" if "strategy_return" in strat.columns else strat.columns[0]
    matched = pd.read_csv(matched_path, index_col=0)
    mcol = matched.columns[0]
    result = validate_matched_controls_calendar_integrity(
        strategy_returns=pd.to_numeric(strat[scol], errors="coerce"),
        matched_returns=pd.to_numeric(matched[mcol], errors="coerce"),
    )
    if not result.passed:
        return "; ".join(result.errors)
    return None


def _integrity_status(out_dir: Path) -> str:
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        return "MISSING"
    try:
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        return str(meta.get("integrity_status", meta.get("status", "UNKNOWN")))
    except Exception:
        return "ERROR"


def _is_pass_complete(out_dir: Path) -> bool:
    if _integrity_status(out_dir) != "PASS":
        return False
    report = out_dir / "integrity_report.json"
    if not report.is_file():
        return False
    try:
        data = json.loads(report.read_text(encoding="utf-8"))
        return str(data.get("status", "")) == "PASS" and not data.get("errors")
    except Exception:
        return False


def _find_pass_dir(variant_key: str) -> Optional[Path]:
    """Reuse any prior validation_runs folder with PASS for this variant."""
    if not VALIDATION_ROOT.is_dir():
        return None
    candidates: List[Path] = []
    for child in VALIDATION_ROOT.iterdir():
        if not child.is_dir():
            continue
        name = child.name
        if name.endswith(f"_{variant_key}") and _is_pass_complete(child):
            candidates.append(child)
    return sorted(candidates)[-1] if candidates else None


def _find_prediction_cache_dir(variant_key: str) -> Optional[Path]:
    """Latest run dir for `variant_key` that already has a Phase-A prediction cache."""
    if not VALIDATION_ROOT.is_dir():
        return None
    candidates: List[Path] = []
    for child in VALIDATION_ROOT.iterdir():
        if not child.is_dir():
            continue
        if child.name.endswith(f"_{variant_key}") and (child / "prediction_cache.pkl").is_file():
            candidates.append(child)
    return sorted(candidates)[-1] if candidates else None


def _seed_prediction_cache(out_dir: Path, source_dir: Path) -> bool:
    """Copy Phase-A cache when only execution costs differ (slippage not in fingerprint)."""
    source_dir = Path(source_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = False
    for name in ("prediction_cache.pkl", "prediction_cache_meta.json"):
        src = source_dir / name
        dst = out_dir / name
        if src.is_file() and (not dst.is_file() or dst.stat().st_size == 0):
            shutil.copy2(src, dst)
            copied = True
    return copied


def _cost_base_key(variant_key: str) -> Optional[str]:
    for cs in COST_STRESS:
        suffix = f"_{cs['suffix']}"
        if variant_key.endswith(suffix):
            return variant_key[: -len(suffix)]
    return None


def _is_default_cost_scenario(extra: Optional[Dict[str, str]]) -> bool:
    if not extra:
        return False
    slip = str(extra.get("--slippage-bps", "")).strip()
    impact = str(extra.get("--market-impact-bps", "")).strip()
    return slip == "2" and impact == "0"


def _variant_fast_profile(variant: Dict[str, Any], fast_profile: bool) -> bool:
    """M1 and other naive-detailed variants need full naive export flags."""
    if _m1_naive_detailed_enabled(variant):
        return False
    return fast_profile


def _variant_needs_serial(variant: Dict[str, Any]) -> bool:
    return _m1_naive_detailed_enabled(variant)


def _build_cmd(
    variant: Dict[str, Any],
    out_dir: Path,
    *,
    extra: Optional[Dict[str, str]] = None,
    run_mode: str = "backtest",
    force_predictions: bool = False,
    fast_profile: bool = True,
    n_jobs: str = "auto",
    cpu_cores: int = DEFAULT_CPU,
    backtest_scope: str = "full",
    prediction_cache_dir: Optional[Path] = None,
    profile: Optional[RuntimeProfileSpec] = None,
    has_prediction_cache: bool = False,
) -> List[str]:
    cmd = list(BASE_CMD)
    use_fast = _variant_fast_profile(variant, fast_profile)
    mode_idx = cmd.index("--mode") + 1
    cmd[mode_idx] = run_mode
    nj_idx = cmd.index("--n-jobs") + 1
    cmd[nj_idx] = str(n_jobs)
    cc_idx = cmd.index("--cpu-cores") + 1
    cmd[cc_idx] = str(cpu_cores)
    if use_fast:
        cmd.extend(VALIDATION_FAST_FLAGS)
    if os.name == "nt":
        bi = cmd.index("--parallel-backtest-backend") + 1
        nj_idx = cmd.index("--n-jobs") + 1
        prof = profile or resolve_effective_profile(
            os.environ.get("AA_RUNTIME_PROFILE", "validation"),
            interactive_active=is_interactive_session_running(ROOT),
        )
        if prof.name == "turbo":
            cmd[bi] = str(prof.parallel_backend or "process")
            nj_use = str(n_jobs)
            if nj_use == "auto":
                nj_use = str(max(1, min(int(cpu_cores), 32)))
            cmd[nj_idx] = nj_use
        else:
            cmd[bi] = "thread"
            cmd[nj_idx] = "4" if str(n_jobs) == "auto" else str(n_jobs)
    if backtest_scope == "path-only":
        cmd += ["--backtest-scope", "path-only", "--n-jobs", "1"]
        if prediction_cache_dir is not None:
            cmd += ["--prediction-cache-dir", str(prediction_cache_dir)]
    elif force_predictions:
        cmd.append("--force-rebuild-predictions")
    elif has_prediction_cache or (out_dir / "prediction_cache.pkl").is_file():
        cmd.append("--reuse-prediction-cache")
    else:
        cmd.append("--force-rebuild-predictions")
    if SHARED_CACHE.is_dir():
        cmd += ["--shared-cache-dir", str(SHARED_CACHE)]
    cmd += ["--out-dir", str(out_dir)]
    cmd += ["--risk-off-selection-mode", str(variant.get("risk_off_selection_mode", "legacy"))]
    cmd += ["--risk-off-gate-mode", str(variant.get("risk_off_gate_mode", "legacy"))]
    if variant.get("risk_off_momentum_variant"):
        cmd += ["--risk-off-momentum-variant", str(variant["risk_off_momentum_variant"])]
    if variant.get("risk_off_momentum_weight") is not None:
        cmd += ["--risk-off-momentum-weight", str(variant["risk_off_momentum_weight"])]
    if variant.get("risk_off_momentum_rescue_quantile") is not None:
        cmd += ["--risk-off-momentum-rescue-quantile", str(variant["risk_off_momentum_rescue_quantile"])]
    if bool(variant.get("risk_off_force_exit_enabled", False)):
        cmd.append("--risk-off-force-exit-enabled")
    if _m1_naive_detailed_enabled(variant):
        cmd.append("--naive-detailed-reporting")
        if variant.get("naive_detailed_variants"):
            cmd += ["--naive-detailed-variants", str(variant["naive_detailed_variants"])]
    if _post_m1_perf_active():
        if "--returns-fast-path" not in cmd:
            cmd.append("--returns-fast-path")
        if "--path-sim-checkpoint" not in cmd:
            cmd.append("--path-sim-checkpoint")
    # M1 path simulation is serial and deadlock-prone with process pools on Windows.
    if os.name == "nt" and str(variant.get("key", "")) == M1_VARIANT_KEY:
        bi = cmd.index("--parallel-backtest-backend") + 1
        nj_idx = cmd.index("--n-jobs") + 1
        cmd[bi] = "thread"
        cmd[nj_idx] = "1"
    if variant.get("alpha_model_mode"):
        ai = cmd.index("--alpha-model-mode") + 1
        cmd[ai] = str(variant["alpha_model_mode"])
    if variant.get("train_years") is not None:
        ti = cmd.index("--train-years") + 1
        cmd[ti] = str(variant["train_years"])
    if variant.get("top_k") is not None:
        cmd += ["--top-k", str(variant["top_k"])]
    if variant.get("lcb_z") is not None:
        cmd += ["--lcb-z", str(variant["lcb_z"])]
    # Daily-alpha overrides (echtes Tages-Alpha): patch the fixed BASE_CMD slots.
    if variant.get("horizon") is not None:
        cmd[cmd.index("--horizon") + 1] = str(variant["horizon"])
    if variant.get("rebalance_every") is not None:
        cmd[cmd.index("--rebalance-every") + 1] = str(variant["rebalance_every"])
    # horizon change alters the target label -> features must be rebuilt (also brings in mom_1).
    # Resume: skip rebuild when features + path-sim checkpoint already exist.
    resume_skip_rebuild = (
        (out_dir / "features.parquet").is_file()
        and (out_dir / "path_sim_checkpoint_meta.json").is_file()
    )
    if (
        variant.get("force_rebuild_features")
        and "--force-rebuild-features" not in cmd
        and not resume_skip_rebuild
    ):
        cmd.append("--force-rebuild-features")
    # Benchmark variant (e.g. mom_1_top12): enable the naive baseline so the benchmark
    # returns are produced (the fast profile otherwise suppresses it).
    if variant.get("benchmark_variant"):
        if "--no-naive-momentum-baseline" in cmd:
            cmd.remove("--no-naive-momentum-baseline")
        if "--naive-detailed-reporting" not in cmd:
            cmd.append("--naive-detailed-reporting")
        cmd += ["--naive-detailed-variants", str(variant["benchmark_variant"])]
    if extra:
        for flag, val in extra.items():
            if flag.startswith("--"):
                cmd += [flag, val]
    return cmd


def _apply_turbo_cmd_boost(cmd: List[str], env: Dict[str, str]) -> None:
    """Patch argv for turbo children (read each spawn; works after post-R0 relaunch)."""
    if env.get("AA_RUNTIME_PROFILE") != "turbo" or os.name != "nt":
        return
    try:
        if cmd[cmd.index("--backtest-scope") + 1] == "path-only":
            return
    except ValueError:
        pass
    cores = max(1, int(env.get("AA_CPU_CORES", "") or _default_cpu_cores()))
    nj = max(1, min(cores, 32))
    try:
        bi = cmd.index("--parallel-backtest-backend") + 1
        cmd[bi] = str(env.get("AA_PARALLEL_BACKTEST_BACKEND", "process") or "process")
        ni = cmd.index("--n-jobs") + 1
        cmd[ni] = str(nj)
        ci = cmd.index("--cpu-cores") + 1
        cmd[ci] = str(cores)
    except ValueError:
        return


def _run_logged(cmd: List[str], log_path: Path, profile: RuntimeProfileSpec) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = subprocess_env_for_profile(profile)
    try:
        from tools.r0_migration_killer_pack import killer_subprocess_env

        env = killer_subprocess_env(env)
    except Exception:
        env["PYTHONUNBUFFERED"] = "1"
        env["AA_PLAIN_PROGRESS_QUIET"] = "1"
    _apply_turbo_cmd_boost(cmd, env)
    run_cmd = list(cmd)
    exe = Path(str(run_cmd[0])).name.lower()
    if exe.startswith("python") and (len(run_cmd) < 2 or run_cmd[1] != "-u"):
        run_cmd.insert(1, "-u")
    with log_path.open("w", encoding="utf-8") as log:
        log.write(" ".join(run_cmd) + "\n")
        log.write(f"runtime_profile={profile.name} priority={profile.process_priority}\n\n")
        log.flush()
        proc = subprocess.run(run_cmd, cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT, env=env)
    return int(proc.returncode)


def _resolve_skip(
    key: str,
    out_dir: Path,
    *,
    skip_complete: bool,
    extra: Optional[Dict[str, str]],
) -> Optional[Dict[str, str]]:
    if not skip_complete:
        return None
    if skip_complete and _is_pass_complete(out_dir):
        return {"status": "SKIP", "integrity": "PASS", "reason": "stamp_dir_pass"}
    if _is_default_cost_scenario(extra):
        base_key = _cost_base_key(key) or key
        prior = _find_pass_dir(base_key)
        if prior is not None:
            return {
                "status": "SKIP",
                "integrity": "PASS",
                "reason": "default_cost_same_as_base",
                "reused_from": str(prior),
            }
    prior = _find_pass_dir(key)
    if prior is not None and prior.resolve() != out_dir.resolve():
        return {"status": "SKIP", "integrity": "PASS", "reason": "prior_pass", "reused_from": str(prior)}
    return None


def _run_one_variant(
    variant: Dict[str, Any],
    *,
    stamp: str,
    skip_complete: bool,
    run_mode: str,
    force_predictions: bool,
    fast_profile: bool,
    n_jobs: str,
    cpu_cores: int,
    dry_run: bool,
    cost_mode: str = "path-only",
    profile: Optional[RuntimeProfileSpec] = None,
) -> Dict[str, Any]:
    key = str(variant["key"])
    out_dir = VALIDATION_ROOT / f"{stamp}_{key}"
    extra = variant.get("_cmd_extra")
    entry: Dict[str, Any] = {"key": key, "out_dir": str(out_dir), "status": "pending"}
    print(f"\n=== {key} -> {out_dir} ===", flush=True)

    skip = _resolve_skip(key, out_dir, skip_complete=skip_complete, extra=extra)
    if skip:
        entry.update(skip)
        print(f"  skip: {skip.get('reason', 'complete')}", flush=True)
        if skip.get("reused_from"):
            print(f"         {skip['reused_from']}", flush=True)
        return entry

    seed_from: Optional[Path] = None
    base_key = _cost_base_key(key)
    use_path_only = bool(base_key and extra and not _is_default_cost_scenario(extra) and cost_mode == "path-only")
    if base_key and extra and not _is_default_cost_scenario(extra):
        seed_from = _find_pass_dir(base_key)
        if seed_from is None:
            candidate = VALIDATION_ROOT / f"{stamp}_{base_key}"
            if (candidate / "prediction_cache.pkl").is_file():
                seed_from = candidate
            else:
                seed_from = None

    pred_cache_dir = seed_from if use_path_only and seed_from else None
    scope = "path-only" if use_path_only and pred_cache_dir else "full"
    prof = profile or resolve_effective_profile(
        os.environ.get("AA_RUNTIME_PROFILE", "validation"),
        interactive_active=is_interactive_session_running(ROOT),
    )
    turbo = prof.name == "turbo" or os.environ.get("AA_FORCE_H1_TURBO", "").strip() in ("1", "true", "yes")
    job_njobs = n_jobs if (scope != "path-only" or turbo) else "1"
    job_cores = int(cpu_cores) if turbo else (min(4, cpu_cores) if scope == "path-only" else cpu_cores)

    cache_seeded_from: Optional[Path] = None
    if scope == "full" and not force_predictions:
        if seed_from is not None:
            cache_seeded_from = seed_from
        else:
            cache_seeded_from = _find_prediction_cache_dir(key)
    elif scope == "path-only" and pred_cache_dir is not None:
        cache_seeded_from = pred_cache_dir

    if not dry_run and cache_seeded_from is not None and scope == "full":
        out_dir.mkdir(parents=True, exist_ok=True)
        if _seed_prediction_cache(out_dir, cache_seeded_from):
            entry["seed_prediction_from"] = str(cache_seeded_from)
            print(f"  seeded prediction cache from {cache_seeded_from.name}", flush=True)
    elif dry_run and cache_seeded_from is not None:
        print(f"  will seed prediction cache from {cache_seeded_from.name}", flush=True)

    has_prediction_cache = bool(
        cache_seeded_from is not None
        and (scope == "path-only" or (out_dir / "prediction_cache.pkl").is_file() or dry_run)
    )

    cmd = _build_cmd(
        variant,
        out_dir,
        extra=extra,
        run_mode=run_mode,
        force_predictions=force_predictions and scope == "full" and not has_prediction_cache,
        fast_profile=fast_profile,
        n_jobs=job_njobs,
        cpu_cores=job_cores,
        backtest_scope=scope,
        prediction_cache_dir=pred_cache_dir,
        profile=prof,
        has_prediction_cache=has_prediction_cache,
    )
    if dry_run:
        if cache_seeded_from:
            print(f"  scope={scope} prediction cache <- {cache_seeded_from}", flush=True)
        print(" ".join(cmd), flush=True)
        entry["status"] = "dry_run"
        entry["backtest_scope"] = scope
        if cache_seeded_from:
            entry["seed_prediction_from"] = str(cache_seeded_from)
        return entry

    if scope == "path-only" and pred_cache_dir:
        entry["backtest_scope"] = "path-only"
        entry["prediction_cache_dir"] = str(pred_cache_dir)
        print(f"  path-only Phase B, predictions from {pred_cache_dir.name}", flush=True)

    prof = profile or resolve_effective_profile(
        os.environ.get("AA_RUNTIME_PROFILE", "validation"),
        interactive_active=is_interactive_session_running(ROOT),
    )

    rc = _run_logged(cmd, out_dir / "validation_run.log", prof)
    entry["returncode"] = rc
    entry["integrity"] = _integrity_status(out_dir)
    if rc == 0 and key == M1_VARIANT_KEY and not _m1_fast_seal_active():
        m1_err = _check_m1_matched_controls(out_dir)
        if m1_err:
            entry["m1_check"] = m1_err
            entry["integrity"] = "INVALID"
            print(f"  M1 check failed: {m1_err}", flush=True)
    entry["status"] = "PASS" if rc == 0 and entry["integrity"] == "PASS" else "FAIL"
    print(f"  rc={rc} integrity={entry['integrity']}", flush=True)
    return entry


def run_matrix(
    *,
    stamp: str,
    variants: List[Dict[str, Any]],
    dry_run: bool = False,
    skip_complete: bool = True,
    run_mode: str = "backtest",
    force_predictions: bool = False,
    fast_profile: bool = True,
    parallel_jobs: int = 1,
    cpu_cores: int = DEFAULT_CPU,
    cost_mode: str = "path-only",
    warm_cache: bool = True,
    profile_name: str = "validation",
    batch_guard: Optional[BatchWorkGuard] = None,
) -> Dict[str, Any]:
    prof, jobs, cores_per_job, prof_note = _resolve_hardware_context(
        profile_name=profile_name,
        parallel_jobs=parallel_jobs,
        cpu_cores=cpu_cores,
    )
    jobs = max(1, min(int(parallel_jobs), jobs))
    n_jobs, cores_per_job = _worker_budget(jobs, cpu_cores, prof)
    summary: Dict[str, Any] = {
        "stamp": stamp,
        "parallel_jobs": jobs,
        "cpu_cores": cpu_cores,
        "cores_per_job": cores_per_job,
        "runtime_profile": prof.name,
        "runtime_profile_note": prof_note,
        "interactive_exe_active": is_interactive_session_running(ROOT),
        "fast_profile": fast_profile,
        "run_mode": run_mode,
        "cost_mode": cost_mode,
        "runs": [],
    }
    if not dry_run:
        print(f"[hardware] {prof_note} | {jobs} variant slot(s), {cores_per_job} core(s)/job, n_jobs={n_jobs}", flush=True)

    pending = list(variants)
    if _is_m1_phase_matrix(pending):
        pending = _order_m1_phase_variants(pending)
        jobs = max(1, min(int(parallel_jobs), 2))
        print(
            f"[m1-phase] R0 warm-cache serial, then R3/M1 (order fixed, parallel_jobs={jobs})",
            flush=True,
        )
    run_kwargs = dict(
        stamp=stamp,
        skip_complete=skip_complete,
        run_mode=run_mode,
        force_predictions=force_predictions,
        fast_profile=fast_profile,
        cost_mode=cost_mode,
        profile=prof,
    )

    def _run_batch(batch: List[Dict[str, Any]], *, nj: str, cores: int, parallel: bool) -> List[Dict[str, Any]]:
        if not batch:
            return []
        if dry_run or not parallel or len(batch) == 1:
            return [
                _run_one_variant(
                    v,
                    n_jobs=nj,
                    cpu_cores=cores,
                    dry_run=dry_run,
                    **run_kwargs,
                )
                for v in batch
            ]
        results: List[Dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = {
                pool.submit(
                    _run_one_variant,
                    v,
                    n_jobs=nj,
                    cpu_cores=cores,
                    dry_run=False,
                    **run_kwargs,
                ): v
                for v in batch
            }
            by_key: Dict[str, Dict[str, Any]] = {}
            for fut in as_completed(futures):
                v = futures[fut]
                try:
                    by_key[str(v["key"])] = fut.result()
                except Exception as exc:
                    key = str(v["key"])
                    by_key[key] = {"key": key, "status": "FAIL", "error": str(exc)}
                    print(f"[ERROR] {key}: {exc}", flush=True)
            results = [by_key[str(v["key"])] for v in batch if str(v["key"]) in by_key]
        return results

    skipped_entries: List[Dict[str, Any]] = []
    runnable: List[Dict[str, Any]] = []
    serial_runnable: List[Dict[str, Any]] = []
    parallel_runnable: List[Dict[str, Any]] = []
    for variant in pending:
        key = str(variant["key"])
        out_dir = VALIDATION_ROOT / f"{stamp}_{key}"
        skip = _resolve_skip(key, out_dir, skip_complete=skip_complete, extra=variant.get("_cmd_extra"))
        if skip:
            skipped_entries.append({"key": key, "out_dir": str(out_dir), **skip})
        elif _variant_needs_serial(variant):
            serial_runnable.append(variant)
        else:
            parallel_runnable.append(variant)
    runnable = parallel_runnable + serial_runnable

    all_runs: List[Dict[str, Any]] = []
    for entry in skipped_entries:
        key = entry["key"]
        print(f"\n=== {key} -> {entry['out_dir']} ===", flush=True)
        print(f"  skip: {entry.get('reason', 'complete')}", flush=True)
        all_runs.append(entry)

    if not runnable:
        summary["runs"] = all_runs
    elif dry_run or jobs == 1 or len(runnable) <= 1:
        all_runs.extend(_run_batch(runnable, nj=n_jobs, cores=cores_per_job, parallel=False))
        summary["runs"] = all_runs
    else:
        warm = parallel_runnable[0] if warm_cache and parallel_runnable else None
        rest = parallel_runnable[1:] if warm_cache and warm is not None else list(parallel_runnable)
        if warm is not None:
            print(f"[warm] serial cache prewarm: {warm['key']}", flush=True)
            all_runs.extend(_run_batch([warm], nj=n_jobs, cores=cpu_cores, parallel=False))
        if rest:
            prof, jobs, _, prof_note = _resolve_hardware_context(
                profile_name=profile_name,
                parallel_jobs=parallel_jobs,
                cpu_cores=cpu_cores,
            )
            nj, cores = _worker_budget(jobs, cpu_cores, prof)
            print(f"[parallel] {min(jobs, len(rest))} workers, {cores} cores/job, n_jobs={nj} ({prof_note})", flush=True)
            for i in range(0, len(rest), jobs):
                chunk = rest[i : i + jobs]
                all_runs.extend(_run_batch(chunk, nj=nj, cores=cores, parallel=len(chunk) > 1))
        if serial_runnable:
            print(f"[serial] naive-detailed variants: {[v['key'] for v in serial_runnable]}", flush=True)
            all_runs.extend(_run_batch(serial_runnable, nj=n_jobs, cores=cpu_cores, parallel=False))
        summary["runs"] = all_runs

    summary_path = VALIDATION_ROOT / f"{stamp}_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _run_variants_main(
    variants: List[Dict[str, Any]],
    *,
    stamp: str,
    dry_run: bool,
    skip_complete: bool,
    run_mode: str,
    force_predictions: bool,
    fast_profile: bool,
    parallel_jobs: int,
    cpu_cores: int,
    cost_mode: str = "path-only",
    warm_cache: bool = True,
    profile_name: str = "validation",
) -> int:
    # unwrap cost extras
    wrapped: List[Dict[str, Any]] = []
    for v in variants:
        item = dict(v)
        extra = item.pop("_cost_extra", None)
        if extra:
            item["_cmd_extra"] = {
                "--slippage-bps": str(extra["slippage_bps"]),
                "--market-impact-bps": str(extra["market_impact_bps"]),
            }
        wrapped.append(item)
    batch_guard: Optional[BatchWorkGuard] = None
    if not dry_run:
        batch_guard = acquire_batch_work(ROOT, label=f"validation_{stamp}")
        if batch_guard is None:
            print("[WARN] Batch-Lock belegt — Hintergrund-Profil", flush=True)
            profile_name = "background"

    try:
        summary = run_matrix(
            stamp=stamp,
            variants=wrapped,
            dry_run=dry_run,
            skip_complete=skip_complete,
            run_mode=run_mode,
            force_predictions=force_predictions,
            fast_profile=fast_profile,
            parallel_jobs=parallel_jobs,
            cpu_cores=cpu_cores,
            cost_mode=cost_mode,
            warm_cache=warm_cache,
            profile_name=profile_name,
            batch_guard=batch_guard,
        )
    finally:
        if batch_guard is not None:
            batch_guard.release()
    if dry_run:
        return 0
    fails = sum(1 for r in summary["runs"] if r.get("status") == "FAIL")
    skips = sum(1 for r in summary["runs"] if r.get("status") == "SKIP")
    passes = sum(1 for r in summary["runs"] if r.get("status") == "PASS")
    print(f"\nSummary: PASS={passes} SKIP={skips} FAIL={fails}")
    return 1 if fails else 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run validation matrix (Phase 10)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--variant", action="append", help="Run only these variant keys")
    p.add_argument("--phase", choices=("matrix", "cost", "all", "reference"), default="reference")
    p.add_argument("--stamp", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    p.add_argument("--skip-complete", action=argparse.BooleanOptionalAction, default=True)
    p.add_argument("--run-mode", choices=("backtest", "both"), default="backtest")
    p.add_argument("--force-predictions", action="store_true", help="Always rebuild prediction cache")
    p.add_argument(
        "--parallel-jobs",
        type=int,
        default=DEFAULT_PARALLEL_JOBS,
        help=f"Run up to N variants in parallel (1-4). Default {DEFAULT_PARALLEL_JOBS}.",
    )
    p.add_argument("--cpu-cores", type=int, default=DEFAULT_CPU, help="Total CPU cores to split across workers.")
    p.add_argument(
        "--full-reporting",
        action="store_true",
        help="Include naive baselines, statistical diagnostics and custom benchmarks (slower).",
    )
    p.add_argument(
        "--cost-mode",
        choices=("path-only", "full"),
        default="path-only",
        help="Cost stress: path-only reuses Phase-A cache and runs Phase B only (default, faster).",
    )
    p.add_argument(
        "--no-warm-cache",
        action="store_true",
        help="Do not run the first pending variant serially before parallel batches.",
    )
    p.add_argument(
        "--runtime-profile",
        default=os.environ.get("AA_RUNTIME_PROFILE", "validation"),
        choices=tuple(PROFILES.keys()),
        help="Hardware/runtime budget (default: validation). Auto-downgrades when Marktanalyse.exe runs.",
    )
    args = p.parse_args()

    profile_name = str(args.runtime_profile).strip().lower()
    fast_profile = not args.full_reporting
    parallel_jobs = max(1, min(int(args.parallel_jobs), 4))
    cpu_cores = max(1, int(args.cpu_cores))

    if args.phase == "matrix" and args.variant:
        allowed = set(args.variant)
        if allowed == set(M1_PHASE_MATRIX_KEYS):
            parallel_jobs = 1

    if args.phase == "reference":
        variants = [v for v in MATRIX if v["key"] == "R3_w070_q070_noexit"]
        run_mode = "both"
        fast_profile = False
    elif args.phase == "matrix":
        variants = list(MATRIX)
        run_mode = args.run_mode
    elif args.phase == "cost":
        base = {v["key"]: v for v in MATRIX}
        variants = []
        for fk in list(FINALIST_KEYS) + list(CHALLENGER_COST_KEYS):
            if fk not in base:
                continue
            for cs in COST_STRESS:
                v = dict(base[fk])
                v["key"] = f"{fk}_{cs['suffix']}"
                v["_cost_extra"] = cs
                variants.append(v)
        run_mode = args.run_mode
    else:
        variants = list(MATRIX)
        run_mode = args.run_mode

    if args.variant:
        allowed = set(args.variant)
        variants = [v for v in variants if v["key"] in allowed or v["key"].split("_cost_")[0] in allowed]

    if args.phase == "all" and not args.dry_run:
        rc_m = _run_variants_main(
            list(MATRIX),
            stamp=args.stamp + "_matrix",
            dry_run=False,
            skip_complete=args.skip_complete,
            run_mode=args.run_mode,
            force_predictions=args.force_predictions,
            fast_profile=fast_profile,
            parallel_jobs=parallel_jobs,
            cpu_cores=cpu_cores,
            cost_mode="full",
            warm_cache=not args.no_warm_cache,
            profile_name=profile_name,
        )
        cost_variants: List[Dict[str, Any]] = []
        base = {v["key"]: v for v in MATRIX}
        for fk in FINALIST_KEYS:
            for cs in COST_STRESS:
                v = dict(base[fk])
                v["key"] = f"{fk}_{cs['suffix']}"
                v["_cost_extra"] = cs
                cost_variants.append(v)
        rc_c = _run_variants_main(
            cost_variants,
            stamp=args.stamp + "_cost",
            dry_run=False,
            skip_complete=args.skip_complete,
            run_mode=args.run_mode,
            force_predictions=args.force_predictions,
            fast_profile=fast_profile,
            parallel_jobs=parallel_jobs,
            cpu_cores=cpu_cores,
            cost_mode=args.cost_mode,
            warm_cache=False,
            profile_name=profile_name,
        )
        return 1 if (rc_m or rc_c) else 0

    ref_parallel = 1 if args.phase == "reference" else parallel_jobs
    phase_cost_mode = args.cost_mode if args.phase == "cost" else "full"
    return _run_variants_main(
        variants,
        stamp=args.stamp,
        dry_run=args.dry_run,
        skip_complete=args.skip_complete,
        run_mode=run_mode,
        force_predictions=args.force_predictions or args.phase == "reference",
        fast_profile=fast_profile,
        parallel_jobs=ref_parallel,
        cpu_cores=cpu_cores,
        cost_mode=phase_cost_mode,
        warm_cache=not args.no_warm_cache and args.phase in ("matrix", "all"),
        profile_name=profile_name if args.phase != "reference" else "research",
    )


if __name__ == "__main__":
    raise SystemExit(main())
