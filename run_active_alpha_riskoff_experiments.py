#!/usr/bin/env python3
"""Run Risk-Off Momentum Rescue research matrix (R0–R4, M1) in separate output dirs."""
from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_risk_off_reporting import write_risk_off_research_reports  # noqa: E402
from aa_subprocess_runner import run_logged_subprocess  # noqa: E402

RESEARCH_ROOT = ROOT / "research_riskoff_experiments"
DEFAULT_SHARED_CACHE = ROOT / "robustness_results_trading212" / "_shared_cache"
SHARED_CACHE = DEFAULT_SHARED_CACHE if DEFAULT_SHARED_CACHE.exists() else RESEARCH_ROOT / "_shared_cache"
DEFAULT_CPU_CORES = int(os.environ.get("AA_CPU_CORES", "16") or 16)
DEFAULT_RAM_GB = int(os.environ.get("AA_SYSTEM_RAM_GB", "64") or 64)

COMMON_ARGS = [
    sys.executable,
    "active_alpha_model.py",
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
    "--alpha-model-mode",
    "ensemble",
    "--exposure-controller",
    "gradual_alpha",
    "--beta-cap-mode",
    "dynamic",
    "--dynamic-beta-risk-off",
    "1.10",
    "--max-gross-exposure",
    "1.00",
    "--max-position",
    "0.12",
    "--max-issuer",
    "0.15",
    "--max-sector",
    "0.55",
    "--static-cluster-cap",
    "0.40",
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
    str(DEFAULT_CPU_CORES),
    "--system-ram-gb",
    str(DEFAULT_RAM_GB),
    "--parallel-profile",
    "high",
    "--parallel-backtest-backend",
    "process",
    "--reuse-feature-cache",
    "--reuse-prediction-cache",
    "--skip-download-if-cached",
    "--no-statistical-diagnostics",
    "--no-custom-benchmarks",
    "--skip-feature-parquet-write",
    "--no-plot",
    "--no-naive-overlap",
    "--no-naive-momentum-baseline",
    "--plain-progress",
    "--no-gui",
    "--cluster-mode",
    "static",
]

EXPERIMENTS: List[Dict[str, Any]] = [
    {
        "key": "R0_LEGACY_ENSEMBLE",
        "risk_off_selection_mode": "legacy",
        "risk_off_gate_mode": "legacy",
        "risk_off_force_exit_enabled": False,
        "naive_detailed_reporting": True,
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
        "legacy_key": "R3_RISK_OFF_MOMENTUM_RESCUE",
        "risk_off_selection_mode": "mom_blend_blend",
        "risk_off_momentum_variant": "mom_blend_top12",
        "risk_off_momentum_weight": "0.70",
        "risk_off_gate_mode": "momentum_rescue",
        "risk_off_momentum_rescue_quantile": "0.70",
        "risk_off_force_exit_enabled": False,
    },
    {
        "key": "R4_w070_q070_forceexit",
        "legacy_key": "R4_RISK_OFF_MOMENTUM_RESCUE_FORCE_EXIT",
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
]


def _is_complete(out_dir: Path) -> bool:
    pointer = out_dir / "latest_validated_run.json"
    if pointer.is_file():
        try:
            meta = json.loads(pointer.read_text(encoding="utf-8"))
            if str(meta.get("integrity_status", meta.get("status", ""))) == "PASS":
                return True
        except Exception:
            pass
    report = out_dir / "backtest_report.txt"
    if not report.exists() or report.stat().st_size < 40:
        return False
    text = report.read_text(encoding="utf-8", errors="ignore")
    return "Strategy metrics" in text and "total_return" in text


def _needs_serial_slot(exp: Dict[str, Any]) -> bool:
    return bool(exp.get("naive_detailed_reporting"))


def _seed_prediction_cache(out_dir: Path, source_dir: Path) -> None:
    import shutil

    source_dir = Path(source_dir)
    out_dir = Path(out_dir)
    for name in ("prediction_cache.pkl", "prediction_cache_meta.json"):
        src = source_dir / name
        dst = out_dir / name
        if src.exists() and (not dst.exists() or dst.stat().st_size == 0):
            shutil.copy2(src, dst)


def _worker_budget(parallel_jobs: int, cpu_cores: int) -> tuple[str, int]:
    jobs = max(1, min(int(parallel_jobs), 4))
    cores = max(1, int(cpu_cores))
    if jobs == 1:
        return "auto", cores
    per_job = max(1, cores // jobs)
    return str(per_job), per_job


def build_command(
    exp: Dict[str, Any],
    *,
    research_root: Path,
    shared_cache: Path,
    n_jobs: str = "auto",
    cpu_cores: int = DEFAULT_CPU_CORES,
    out_dir: Path | None = None,
) -> List[str]:
    if out_dir is None:
        rel = str(exp.get("out_subdir", "") or "").strip()
        out_dir = research_root / rel / str(exp["key"]) if rel else research_root / str(exp["key"])
    cmd = list(COMMON_ARGS)
    n_jobs_idx = cmd.index("--n-jobs") + 1
    cpu_idx = cmd.index("--cpu-cores") + 1
    slip_idx = cmd.index("--slippage-bps") + 1
    cmd[n_jobs_idx] = str(n_jobs)
    cmd[cpu_idx] = str(cpu_cores)
    if exp.get("slippage_bps") is not None:
        cmd[slip_idx] = str(exp["slippage_bps"])
    cmd += ["--shared-cache-dir", str(shared_cache)]
    cmd += ["--out-dir", str(out_dir)]
    cmd += ["--risk-off-selection-mode", str(exp.get("risk_off_selection_mode", "legacy"))]
    cmd += ["--risk-off-gate-mode", str(exp.get("risk_off_gate_mode", "legacy"))]
    if exp.get("risk_off_momentum_variant"):
        cmd += ["--risk-off-momentum-variant", str(exp["risk_off_momentum_variant"])]
    if exp.get("risk_off_momentum_weight") is not None:
        cmd += ["--risk-off-momentum-weight", str(exp["risk_off_momentum_weight"])]
    if exp.get("risk_off_momentum_rescue_quantile") is not None:
        cmd += ["--risk-off-momentum-rescue-quantile", str(exp["risk_off_momentum_rescue_quantile"])]
    if bool(exp.get("risk_off_force_exit_enabled", False)):
        cmd.append("--risk-off-force-exit-enabled")
    if bool(exp.get("naive_detailed_reporting", False)):
        cmd.append("--naive-detailed-reporting")
        cmd += [
            "--naive-detailed-variants",
            str(exp.get("naive_detailed_variants", "mom_blend_top12,mom_63_top12,mom_blend_matched_controls")),
        ]
    return cmd


def experiment_out_dir(exp: Dict[str, Any], research_root: Path) -> Path:
    rel = str(exp.get("out_subdir", "") or "").strip()
    key = str(exp["key"])
    return research_root / rel / key if rel else research_root / key


def run_experiment(
    exp: Dict[str, Any],
    *,
    research_root: Path,
    shared_cache: Path,
    n_jobs: str = "auto",
    cpu_cores: int = DEFAULT_CPU_CORES,
    grace_seconds: int = 90,
    seed_prediction_from: Path | None = None,
) -> int:
    key = str(exp["key"])
    out_dir = experiment_out_dir(exp, research_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    if _is_complete(out_dir):
        print(f"[SKIP] {key} already complete", flush=True)
        return 0
    if seed_prediction_from is not None:
        _seed_prediction_cache(out_dir, seed_prediction_from)
    cmd = build_command(
        exp,
        research_root=research_root,
        shared_cache=shared_cache,
        n_jobs=n_jobs,
        cpu_cores=cpu_cores,
        out_dir=out_dir,
    )
    print(f"[RUN] {key} (n_jobs={n_jobs}, cpu_cores={cpu_cores}, backend=process)", flush=True)
    return run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=_is_complete, grace_seconds=grace_seconds)


def plan_batches(exps: List[Dict[str, Any]], parallel_jobs: int) -> List[List[Dict[str, Any]]]:
    jobs = max(1, min(int(parallel_jobs), 4))
    batches: List[List[Dict[str, Any]]] = []
    idx = 0
    while idx < len(exps):
        exp = exps[idx]
        if _needs_serial_slot(exp):
            batches.append([exp])
            idx += 1
            continue
        batch: List[Dict[str, Any]] = []
        while idx < len(exps) and len(batch) < jobs:
            if _needs_serial_slot(exps[idx]):
                break
            batch.append(exps[idx])
            idx += 1
        if batch:
            batches.append(batch)
    return batches


def run_batch(
    batch: List[Dict[str, Any]],
    *,
    research_root: Path,
    shared_cache: Path,
    parallel_jobs: int,
    cpu_cores: int,
    grace_seconds: int,
) -> int:
    pending = [e for e in batch if not _is_complete(experiment_out_dir(e, research_root))]
    if not pending:
        return 0
    n_jobs, cores_per_job = _worker_budget(len(pending) if len(pending) > 1 else 1, cpu_cores)
    if len(pending) == 1:
        return run_experiment(
            pending[0],
            research_root=research_root,
            shared_cache=shared_cache,
            n_jobs=n_jobs,
            cpu_cores=cores_per_job,
            grace_seconds=grace_seconds,
            seed_prediction_from=Path(pending[0]["seed_prediction_from"]) if pending[0].get("seed_prediction_from") else None,
        )
    n_jobs, cores_per_job = _worker_budget(len(pending), cpu_cores)
    rc = 0
    with ThreadPoolExecutor(max_workers=len(pending)) as pool:
        futures = {
            pool.submit(
                run_experiment,
                exp,
                research_root=research_root,
                shared_cache=shared_cache,
                n_jobs=n_jobs,
                cpu_cores=cores_per_job,
                grace_seconds=grace_seconds,
                seed_prediction_from=Path(exp["seed_prediction_from"]) if exp.get("seed_prediction_from") else None,
            ): exp
            for exp in pending
        }
        for fut in as_completed(futures):
            exp = futures[fut]
            try:
                result = int(fut.result())
            except Exception as exc:
                print(f"[ERROR] {exp['key']} raised {exc}", flush=True)
                return 1
            if result != 0:
                rc = result
    return rc


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Risk-Off Momentum Rescue research matrix.")
    p.add_argument("--research-root", default=str(RESEARCH_ROOT))
    p.add_argument("--shared-cache-dir", default=str(SHARED_CACHE))
    p.add_argument("--only", default="", help="Comma-separated experiment keys to run.")
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--parallel-jobs", type=int, default=2, help="Run up to N light variants in parallel (1-4). Heavy R0/M1 always run alone.")
    p.add_argument("--cpu-cores", type=int, default=DEFAULT_CPU_CORES)
    p.add_argument("--grace-seconds", type=int, default=90, help="Seconds to wait after report completion before killing a hung subprocess.")
    p.add_argument("--reports-only", action="store_true", help="Only write comparison reports from existing dirs.")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    research_root = Path(args.research_root)
    shared_cache = Path(args.shared_cache_dir)
    research_root.mkdir(parents=True, exist_ok=True)
    shared_cache.mkdir(parents=True, exist_ok=True)
    exps = EXPERIMENTS
    if args.only.strip():
        needles = [x.strip().upper() for x in args.only.split(",") if x.strip()]
        exps = [e for e in EXPERIMENTS if any(n in str(e["key"]).upper() for n in needles)]
    variant_dirs = {str(e["key"]): research_root / str(e["key"]) for e in EXPERIMENTS}
    variant_dirs["NAIVE_MOM_BLEND_TOP12"] = research_root / "R0_LEGACY_ENSEMBLE"
    variant_dirs["NAIVE_MOM_63_TOP12"] = research_root / "R0_LEGACY_ENSEMBLE"
    parallel_jobs = max(1, min(int(args.parallel_jobs), 4))
    cpu_cores = max(1, int(args.cpu_cores))
    if args.dry_run:
        print(f"parallel_jobs={parallel_jobs} cpu_cores={cpu_cores} backend=process")
        for exp in exps:
            n_jobs, cores = _worker_budget(1 if _needs_serial_slot(exp) else parallel_jobs, cpu_cores)
            print(" ".join(build_command(exp, research_root=research_root, shared_cache=shared_cache, n_jobs=n_jobs, cpu_cores=cores)))
        return 0
    if not args.reports_only:
        batches = plan_batches(exps, parallel_jobs)
        for batch in batches:
            keys = ", ".join(str(e["key"]) for e in batch)
            print(f"[BATCH] {keys}", flush=True)
            rc = run_batch(
                batch,
                research_root=research_root,
                shared_cache=shared_cache,
                parallel_jobs=parallel_jobs,
                cpu_cores=cpu_cores,
                grace_seconds=max(30, int(args.grace_seconds)),
            )
            if rc != 0:
                print(f"[ERROR] batch failed ({keys}) code={rc}", flush=True)
                return rc
            for exp in batch:
                if _is_complete(experiment_out_dir(exp, research_root)):
                    print(f"[DONE] {exp['key']}", flush=True)
    paths = write_risk_off_research_reports(research_root, variant_dirs)
    for p in paths:
        print(f"[OK] {p}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
