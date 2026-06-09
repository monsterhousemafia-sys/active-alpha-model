#!/usr/bin/env python3
"""R5 challenger pipeline: internet validation, alpha-vs-momentum, cost stress, fine-tune."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_alpha_vs_momentum import (  # noqa: E402
    AlphaMomentumThresholds,
    alpha_beats_momentum_significantly,
    extract_alpha_vs_momentum,
    parse_report_sections,
    score_alpha_vs_momentum,
)
from aa_subprocess_runner import noninteractive_env, run_logged_subprocess  # noqa: E402

VALIDATION_ROOT = ROOT / "validation_runs"
R5_ROOT = ROOT / "validation_runs" / "r5_challenger"
SHARED_CACHE = ROOT / "robustness_results_trading212" / "_shared_cache"
CONTROL = ROOT / "control"
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable

R5_KEY = "R5_rank_only_train5"
R5_BASE: Dict[str, str] = {
    "name": R5_KEY,
    "weight": "0.75",
    "quantile": "0.65",
    "alpha_model_mode": "rank_only",
    "train_years": "5",
    "top_k": "15",
}

R5_FINETUNE: List[Dict[str, str]] = [
    {**R5_BASE, "name": "R5_rank_only_train4", "train_years": "4"},
    {**R5_BASE, "name": "R5_rank_only_train6", "train_years": "6"},
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _is_pass(out_dir: Path) -> bool:
    pointer = out_dir / "latest_validated_run.json"
    if not pointer.is_file():
        return False
    try:
        meta = json.loads(pointer.read_text(encoding="utf-8"))
        return str(meta.get("integrity_status", meta.get("status", ""))) == "PASS"
    except Exception:
        return False


def build_r5_command(
    variant: Dict[str, str],
    *,
    out_dir: Path,
    cpu_cores: int,
    price_source: str,
    full_reporting: bool,
) -> List[str]:
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
        variant.get("train_years", "5"),
        "--ml-retrain-every",
        "2",
        "--alpha-model-mode",
        variant.get("alpha_model_mode", "rank_only"),
        "--exposure-controller",
        "gradual_alpha",
        "--beta-cap-mode",
        "dynamic",
        "--cluster-mode",
        "static",
        "--cluster-constraint-mode",
        "static_only",
        "--slippage-bps",
        str(variant.get("slippage_bps", "2")),
        "--market-impact-bps",
        str(variant.get("market_impact_bps", "0")),
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
        variant.get("weight", "0.75"),
        "--risk-off-momentum-rescue-quantile",
        variant.get("quantile", "0.65"),
        "--top-k",
        variant.get("top_k", "15"),
        "--naive-momentum-variants",
        "mom_blend_top12",
        "--extra-benchmarks",
        "MTUM",
        "--shared-cache-dir",
        str(SHARED_CACHE),
        "--out-dir",
        str(out_dir),
        "--reuse-feature-cache",
        "--skip-download-if-cached",
        "--skip-feature-parquet-write",
        "--no-plot",
        "--no-gui",
        "--plain-progress",
        "--no-statistical-diagnostics",
        "--no-custom-benchmarks",
        "--no-run-manifest",
    ]
    if not full_reporting:
        cmd += ["--no-naive-momentum-baseline", "--minimal-backtest-reporting"]
    return cmd


def run_r5_variant(
    variant: Dict[str, str],
    *,
    cpu_cores: int,
    price_source: str,
    skip_completed: bool,
    full_reporting: bool,
) -> Dict[str, Any]:
    name = variant["name"]
    out_dir = R5_ROOT / name
    out_dir.mkdir(parents=True, exist_ok=True)
    thresholds = AlphaMomentumThresholds()

    if skip_completed and _is_pass(out_dir):
        cmp = extract_alpha_vs_momentum(out_dir)
        beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
        sections = parse_report_sections(out_dir / "backtest_report.txt")
        return {
            "name": name,
            "status": "SKIP",
            "integrity": "PASS",
            "beats_momentum": beats,
            "gate_reason": reason,
            "alpha_score": score_alpha_vs_momentum(cmp),
            "alpha_vs_momentum": cmp.as_dict() if cmp else None,
            "strategy_sharpe": sections.get("strategy", {}).get("sharpe_0rf"),
            "strategy_cagr": sections.get("strategy", {}).get("cagr"),
            "out_dir": str(out_dir),
        }

    cmd = build_r5_command(variant, out_dir=out_dir, cpu_cores=cpu_cores, price_source=price_source, full_reporting=full_reporting)
    env = noninteractive_env({"AA_PRICE_DATA_SOURCE": price_source, "AA_CPU_CORES": str(cpu_cores)})
    print(f"[RUN] {name} ({price_source}, train_years={variant.get('train_years')})", flush=True)
    t0 = time.monotonic()
    rc = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=_is_pass, env=env)
    elapsed = time.monotonic() - t0
    integrity = "PASS" if _is_pass(out_dir) else "FAIL"
    cmp = extract_alpha_vs_momentum(out_dir)
    beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
    sections = parse_report_sections(out_dir / "backtest_report.txt")
    return {
        "name": name,
        "status": "PASS" if integrity == "PASS" and rc == 0 else "FAIL",
        "returncode": rc,
        "integrity": integrity,
        "beats_momentum": beats,
        "gate_reason": reason,
        "alpha_score": score_alpha_vs_momentum(cmp),
        "alpha_vs_momentum": cmp.as_dict() if cmp else None,
        "strategy_sharpe": sections.get("strategy", {}).get("sharpe_0rf"),
        "strategy_cagr": sections.get("strategy", {}).get("cagr"),
        "elapsed_s": round(elapsed, 1),
        "out_dir": str(out_dir),
    }


def run_matrix_base(*, stamp: str, skip_complete: bool) -> Dict[str, Any]:
    cmd = [
        PYTHON,
        str(ROOT / "tools" / "run_validation_matrix.py"),
        "--phase",
        "matrix",
        "--variant",
        R5_KEY,
        "--stamp",
        stamp,
        "--run-mode",
        "backtest",
        "--runtime-profile",
        "validation",
    ]
    if not skip_complete:
        cmd.append("--no-skip-complete")
    print(f"[RUN] matrix base: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    base_dir = VALIDATION_ROOT / f"{stamp}_{R5_KEY}"
    has_cache = (base_dir / "prediction_cache.pkl").is_file()
    integrity = "PASS" if _is_pass(base_dir) else "FAIL"
    return {
        "returncode": proc.returncode,
        "integrity": integrity,
        "prediction_cache": has_cache,
        "out_dir": str(base_dir),
        "log_tail": out[-4000:] if out else "",
    }


def run_cost_stress(*, stamp: str, skip_complete: bool) -> Dict[str, Any]:
    cmd = [
        PYTHON,
        str(ROOT / "tools" / "run_validation_matrix.py"),
        "--phase",
        "cost",
        "--variant",
        R5_KEY,
        "--stamp",
        stamp,
        "--run-mode",
        "backtest",
        "--runtime-profile",
        "validation",
    ]
    if not skip_complete:
        cmd.append("--no-skip-complete")
    print(f"[RUN] cost stress: {' '.join(cmd)}", flush=True)
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    return {"returncode": proc.returncode, "log_tail": out[-4000:] if out else ""}


def write_control_files(payload: Dict[str, Any], *, best: Dict[str, Any]) -> None:
    CONTROL.mkdir(parents=True, exist_ok=True)
    registry = {
        "active": False,
        "auto_promotion": "DISABLED",
        "role": "CHALLENGER",
        "variant_id": R5_KEY,
        "source_tuning_winner": "rank_r2_train5",
        "fictive_tuning_pass": True,
        "internet_validation": payload.get("internet_validation"),
        "best_run_dir": best.get("out_dir", ""),
        "updated_at_utc": _utc_now(),
        "note": "R5 operational champion (manual promotion). Auto-promotion remains DISABLED.",
    }
    (CONTROL / "r5_challenger_registry.json").write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    (CONTROL / "r5_challenger_status.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="R5 rank_only train5 challenger validation pipeline")
    p.add_argument("--internet", action="store_true", help="Use internet/yfinance OHLCV (default)")
    p.add_argument("--fictive", action="store_true", help="Use fictive data instead of internet")
    p.add_argument("--parallel-jobs", type=int, default=2)
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--skip-cost-stress", action="store_true")
    p.add_argument("--skip-finetune", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    price_source = "fictive" if args.fictive else "internet"
    parallel = max(1, min(int(args.parallel_jobs), 3))
    cpu_cores = max(4, 16 // parallel)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    R5_ROOT.mkdir(parents=True, exist_ok=True)
    SHARED_CACHE.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(json.dumps({"variants": [R5_BASE] + R5_FINETUNE, "price_source": price_source}, indent=2))
        return 0

    if price_source == "internet":
        from tools.run_r3_parallel_tuning import seed_r3_price_cache  # noqa: WPS433

        seed_r3_price_cache(price_source="internet")

    # Phase 1: primary internet/fictive validation with momentum comparison
    primary = run_r5_variant(
        R5_BASE,
        cpu_cores=cpu_cores,
        price_source=price_source,
        skip_completed=bool(args.skip_completed),
        full_reporting=True,
    )
    results: List[Dict[str, Any]] = [primary]

    # Phase 2: fine-tune train_years 4 and 6
    if not args.skip_finetune:
        finetune_variants = list(R5_FINETUNE)
        if parallel <= 1 or len(finetune_variants) == 1:
            for v in finetune_variants:
                results.append(
                    run_r5_variant(
                        v,
                        cpu_cores=cpu_cores,
                        price_source=price_source,
                        skip_completed=bool(args.skip_completed),
                        full_reporting=True,
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=parallel) as pool:
                futs = {
                    pool.submit(
                        run_r5_variant,
                        v,
                        cpu_cores=cpu_cores,
                        price_source=price_source,
                        skip_completed=bool(args.skip_completed),
                        full_reporting=True,
                    ): v
                    for v in finetune_variants
                }
                for fut in as_completed(futs):
                    results.append(fut.result())

    # Phase 3: validation matrix base (prediction cache) + cost stress
    matrix_base: Optional[Dict[str, Any]] = None
    cost_result: Optional[Dict[str, Any]] = None
    if not args.skip_cost_stress:
        matrix_base = run_matrix_base(stamp=stamp, skip_complete=bool(args.skip_completed))
        if not matrix_base.get("prediction_cache"):
            print("[WARN] Matrix base missing prediction cache — cost stress skipped.", flush=True)
        else:
            cost_result = run_cost_stress(stamp=stamp, skip_complete=bool(args.skip_completed))

    ranked = sorted(results, key=lambda r: float(r.get("alpha_score") or -999), reverse=True)
    best = ranked[0] if ranked else primary
    payload = {
        "generated_at_utc": _utc_now(),
        "price_source": price_source,
        "stamp": stamp,
        "internet_validation": primary,
        "matrix_base": matrix_base,
        "cost_stress": cost_result,
        "finetune_results": [r for r in results if r["name"] != R5_KEY],
        "ranked": ranked,
        "best_variant": best.get("name"),
        "target_met_on_source": bool(primary.get("beats_momentum")),
        "thresholds": AlphaMomentumThresholds().as_dict(),
    }
    summary_path = R5_ROOT / "r5_challenger_pipeline_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_control_files(payload, best=best)

    print(f"[OK] Summary: {summary_path}", flush=True)
    print(
        f"[OK] Best={best.get('name')} score={best.get('alpha_score')} "
        f"gate={best.get('gate_reason')} integrity={best.get('integrity')}",
        flush=True,
    )
    if cost_result and cost_result.get("returncode", 0) != 0:
        print("[WARN] Cost stress reported non-zero exit.", flush=True)
    if not primary.get("beats_momentum"):
        print("[WARN] Primary R5 run did not beat momentum on this data source.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
