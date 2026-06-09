#!/usr/bin/env python3
"""Parallel R3-aligned tuning matrix — same period as champion (2012-01-01 .. today)."""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TUNING_ROOT = ROOT / "tuning_runs" / "r3_parallel"
SHARED_CACHE = ROOT / "robustness_results_trading212" / "_shared_cache"
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable

R3_START = "2012-01-01"
R3_CAPITAL = "100000"

# Grid around champion R3_w075_q065_noexit
R3_TUNING_VARIANTS: List[Dict[str, str]] = [
    {"name": "R3_champion_w075_q065", "weight": "0.75", "quantile": "0.65"},
    {"name": "R3_w075_q060", "weight": "0.75", "quantile": "0.60"},
    {"name": "R3_w075_q070", "weight": "0.75", "quantile": "0.70"},
    {"name": "R3_w075_q080", "weight": "0.75", "quantile": "0.80"},
    {"name": "R3_w070_q065", "weight": "0.70", "quantile": "0.65"},
    {"name": "R3_w080_q065", "weight": "0.80", "quantile": "0.65"},
    {"name": "R3_w075_q065_train5", "weight": "0.75", "quantile": "0.65", "train_years": "5"},
    {"name": "R3_w075_q065_top12", "weight": "0.75", "quantile": "0.65", "top_k": "12"},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_report_metrics(report_path: Path) -> Dict[str, float]:
    from aa_alpha_vs_momentum import parse_report_sections

    sections = parse_report_sections(report_path)
    return dict(sections.get("strategy", {}))


def _is_complete(out_dir: Path) -> bool:
    if not (out_dir / "backtest_report.txt").is_file():
        return False
    if not (out_dir / "strategy_daily_returns.csv").is_file():
        return False
    pointer = out_dir / "latest_validated_run.json"
    if pointer.is_file():
        try:
            meta = json.loads(pointer.read_text(encoding="utf-8"))
            return str(meta.get("integrity_status", meta.get("status", ""))) == "PASS"
        except Exception:
            pass
    report = out_dir / "integrity_report.json"
    if report.is_file():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            return str(data.get("status", "")) == "PASS" and not data.get("errors")
        except Exception:
            pass
    return True


def build_r3_command(
    variant: Dict[str, str],
    *,
    shared_cache: Path,
    cpu_cores: int,
    price_source: str,
) -> List[str]:
    weight = variant["weight"]
    quantile = variant["quantile"]
    train_years = variant.get("train_years", "7")
    top_k = variant.get("top_k", "15")
    cmd = [
        PYTHON,
        str(ROOT / "active_alpha_model.py"),
        "--mode",
        "both",
        "--ticker-source",
        "sp500_pit",
        "--ticker-cache-dir",
        "universe_snapshots",
        "--membership-file",
        "ticker_membership.csv",
        "--membership-mode",
        "strict",
        "--benchmark",
        "SPY",
        "--start",
        R3_START,
        "--universe-mode",
        "diy_pit_liquidity",
        "--universe-top-n",
        "100",
        "--rebalance-every",
        "5",
        "--horizon",
        "10",
        "--train-years",
        train_years,
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
        R3_CAPITAL,
        "--research-backtest-capital",
        R3_CAPITAL,
        "--reproducibility-mode",
        "strict",
        "--random-seed",
        "42",
        "--n-jobs",
        "auto",
        "--cpu-cores",
        str(cpu_cores),
        "--system-ram-gb",
        "64",
        "--parallel-profile",
        "high",
        "--parallel-backtest-backend",
        "process",
        "--risk-off-selection-mode",
        "mom_blend_blend",
        "--risk-off-momentum-variant",
        "mom_blend_top12",
        "--risk-off-gate-mode",
        "momentum_rescue",
        "--risk-off-momentum-weight",
        weight,
        "--risk-off-momentum-rescue-quantile",
        quantile,
        "--top-k",
        top_k,
        "--shared-cache-dir",
        str(shared_cache),
        "--out-dir",
        str(TUNING_ROOT / variant["name"]),
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
    ]
    return cmd


def seed_r3_price_cache(*, price_source: str) -> None:
    import os

    from aa_config_env import load_aa_env
    from aa_fictive_daily_data import download_fictive_data, is_fictive_price_source
    from aa_live_daily_sync import resolve_prediction_tickers

    env = load_aa_env(ROOT)
    env["AA_PRICE_DATA_SOURCE"] = price_source
    env["AA_START_DATE"] = R3_START
    env["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"
    old = {k: os.environ.get(k) for k in env}
    os.environ.update({str(k): str(v) for k, v in env.items()})
    try:
        tickers, _ = resolve_prediction_tickers(ROOT, env)
        print(f"[INFO] Seeding price cache ({price_source}) for R3 period from {R3_START} …", flush=True)
        if is_fictive_price_source(None, env):
            from aa_config import BacktestConfig, parse_args
            from aa_config_env import build_backtest_argv
            import sys

            old_argv = sys.argv
            try:
                sys.argv = build_backtest_argv(dict(env))
                cfg = BacktestConfig.from_args(parse_args())
                cfg.skip_download_if_cached = False
                download_fictive_data(tickers, R3_START, cfg=cfg)
            finally:
                sys.argv = old_argv
        else:
            from aa_live_daily_sync import sync_live_daily_for_predictions

            sync_live_daily_for_predictions(ROOT, env, force_prices=True, refresh_signal=False, log_print=True)
    finally:
        for key, prior in old.items():
            if prior is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prior


@dataclass
class TuneResult:
    name: str
    returncode: int
    out_dir: str
    sharpe: Optional[float] = None
    cagr: Optional[float] = None
    max_drawdown: Optional[float] = None
    integrity: str = "UNKNOWN"
    elapsed_s: float = 0.0


def run_variant(
    variant: Dict[str, str],
    *,
    shared_cache: Path,
    cpu_cores: int,
    price_source: str,
    skip_completed: bool,
) -> TuneResult:
    name = variant["name"]
    out_dir = TUNING_ROOT / name
    out_dir.mkdir(parents=True, exist_ok=True)

    if skip_completed and _is_complete(out_dir):
        print(f"[SKIP] {name} already complete", flush=True)
        metrics = _parse_report_metrics(out_dir / "backtest_report.txt")
        integrity = "PASS"
        return TuneResult(
            name=name,
            returncode=0,
            out_dir=str(out_dir),
            sharpe=metrics.get("sharpe_0rf"),
            cagr=metrics.get("cagr"),
            max_drawdown=metrics.get("max_drawdown"),
            integrity=integrity,
            elapsed_s=0.0,
        )

    from aa_subprocess_runner import noninteractive_env, run_logged_subprocess

    cmd = build_r3_command(variant, shared_cache=shared_cache, cpu_cores=cpu_cores, price_source=price_source)
    env = noninteractive_env({"AA_PRICE_DATA_SOURCE": price_source, "AA_CPU_CORES": str(cpu_cores)})
    print(f"[RUN] {name} (cores={cpu_cores}, w={variant['weight']}, q={variant['quantile']})", flush=True)
    t0 = time.monotonic()
    rc = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=_is_complete, env=env)
    elapsed = time.monotonic() - t0
    metrics = _parse_report_metrics(out_dir / "backtest_report.txt")
    integrity = "PASS" if _is_complete(out_dir) else "FAIL"
    return TuneResult(
        name=name,
        returncode=rc,
        out_dir=str(out_dir),
        sharpe=metrics.get("sharpe_0rf"),
        cagr=metrics.get("cagr"),
        max_drawdown=metrics.get("max_drawdown"),
        integrity=integrity,
        elapsed_s=elapsed,
    )


def _score_result(r: TuneResult) -> float:
    if r.returncode != 0 or r.integrity != "PASS":
        return -999.0
    sharpe = float(r.sharpe or 0.0)
    cagr = float(r.cagr or 0.0)
    dd = abs(float(r.max_drawdown or 0.0))
    return sharpe * 0.6 + cagr * 0.3 - dd * 0.1


def write_summary(results: List[TuneResult]) -> Path:
    TUNING_ROOT.mkdir(parents=True, exist_ok=True)
    ranked = sorted(results, key=_score_result, reverse=True)
    summary_path = TUNING_ROOT / "r3_tuning_summary.json"
    payload = {
        "generated_at_utc": _utc_now(),
        "period_start": R3_START,
        "capital": R3_CAPITAL,
        "champion_reference": "R3_w075_q065_noexit",
        "results": [
            {
                "name": r.name,
                "returncode": r.returncode,
                "integrity": r.integrity,
                "sharpe_0rf": r.sharpe,
                "cagr": r.cagr,
                "max_drawdown": r.max_drawdown,
                "score": _score_result(r),
                "elapsed_s": round(r.elapsed_s, 1),
                "out_dir": r.out_dir,
            }
            for r in ranked
        ],
        "best": ranked[0].name if ranked and _score_result(ranked[0]) > -999 else None,
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    csv_path = TUNING_ROOT / "r3_tuning_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = ["name", "score", "sharpe_0rf", "cagr", "max_drawdown", "integrity", "elapsed_s", "out_dir"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for r in ranked:
            writer.writerow(
                {
                    "name": r.name,
                    "score": _score_result(r),
                    "sharpe_0rf": r.sharpe,
                    "cagr": r.cagr,
                    "max_drawdown": r.max_drawdown,
                    "integrity": r.integrity,
                    "elapsed_s": round(r.elapsed_s, 1),
                    "out_dir": r.out_dir,
                }
            )
    return summary_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Parallel R3-period tuning runners")
    p.add_argument("--parallel-jobs", type=int, default=3, help="Concurrent backtests (max 3 on 16 cores)")
    p.add_argument("--fictive", action="store_true", help="Fictive daily data (default)")
    p.add_argument("--internet", action="store_true", help="Internet/yfinance OHLCV")
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--no-seed", action="store_true", help="Skip price cache seed step")
    p.add_argument("--only", default="", help="Comma-separated variant name substrings")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    price_source = "internet" if args.internet else "fictive"
    parallel_jobs = max(1, min(int(args.parallel_jobs), 3))
    cpu_cores = max(4, 16 // parallel_jobs)

    variants = list(R3_TUNING_VARIANTS)
    if args.only.strip():
        needles = [x.strip().lower() for x in args.only.split(",") if x.strip()]
        variants = [v for v in variants if any(n in v["name"].lower() for n in needles)]
    if not variants:
        print("[ERROR] No variants selected.", flush=True)
        return 1

    SHARED_CACHE.mkdir(parents=True, exist_ok=True)
    TUNING_ROOT.mkdir(parents=True, exist_ok=True)

    if not args.no_seed:
        seed_r3_price_cache(price_source=price_source)

    print(
        f"[INFO] R3 tuning: {len(variants)} variants, {parallel_jobs} parallel, "
        f"{cpu_cores} cores/job, period={R3_START}, capital={R3_CAPITAL}",
        flush=True,
    )

    results: List[TuneResult] = []
    if parallel_jobs == 1 or len(variants) == 1:
        for v in variants:
            results.append(
                run_variant(
                    v,
                    shared_cache=SHARED_CACHE,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=bool(args.skip_completed),
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=parallel_jobs) as pool:
            futs = {
                pool.submit(
                    run_variant,
                    v,
                    shared_cache=SHARED_CACHE,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=bool(args.skip_completed),
                ): v
                for v in variants
            }
            for fut in as_completed(futs):
                results.append(fut.result())

    summary = write_summary(results)
    best = max(results, key=_score_result)
    print(f"[OK] Summary: {summary}", flush=True)
    if _score_result(best) > -999:
        print(
            f"[OK] Best: {best.name} sharpe={best.sharpe} cagr={best.cagr} dd={best.max_drawdown}",
            flush=True,
        )
    else:
        print("[WARN] No successful PASS runs yet.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
