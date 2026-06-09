#!/usr/bin/env python3
"""Iteratively tune R3-style variants until alpha beats momentum by a meaningful margin."""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_alpha_vs_momentum import (  # noqa: E402
    AlphaMomentumComparison,
    AlphaMomentumThresholds,
    alpha_beats_momentum_significantly,
    extract_alpha_vs_momentum,
    parse_report_sections,
    score_alpha_vs_momentum,
    write_alpha_momentum_status,
)
from aa_subprocess_runner import noninteractive_env, run_logged_subprocess  # noqa: E402

TUNING_ROOT = ROOT / "tuning_runs" / "alpha_momentum"
SHARED_CACHE = ROOT / "robustness_results_trading212" / "_shared_cache"
PYTHON = str(ROOT / ".venv" / "Scripts" / "python.exe")
if not Path(PYTHON).is_file():
    PYTHON = sys.executable

R3_START = "2012-01-01"
R3_CAPITAL = "100000"

ROUND_1_VARIANTS: List[Dict[str, str]] = [
    {"name": "alpha_r3_champion", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "ensemble"},
    {"name": "alpha_rank_only", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only"},
    {"name": "alpha_ml_only", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "ml_only"},
    {"name": "alpha_lcb05", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "ensemble", "lcb_z": "0.05"},
    {"name": "alpha_lcb02", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "ensemble", "lcb_z": "0.02"},
    {"name": "alpha_w050", "weight": "0.50", "quantile": "0.65", "alpha_model_mode": "ensemble"},
    {"name": "alpha_w060_q070", "weight": "0.60", "quantile": "0.70", "alpha_model_mode": "ensemble"},
    {"name": "alpha_top12", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "ensemble", "top_k": "12"},
]

RANK_FOCUS_VARIANTS: List[Dict[str, str]] = [
    {"name": "rank_r2_champion", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only"},
    {"name": "rank_r2_lcb02", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only", "lcb_z": "0.02"},
    {"name": "rank_r2_lcb05", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only", "lcb_z": "0.05"},
    {"name": "rank_r2_top12", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only", "top_k": "12"},
    {"name": "rank_r2_top18", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only", "top_k": "18"},
    {"name": "rank_r2_w050", "weight": "0.50", "quantile": "0.65", "alpha_model_mode": "rank_only"},
    {"name": "rank_r2_w060_q070", "weight": "0.60", "quantile": "0.70", "alpha_model_mode": "rank_only"},
    {"name": "rank_r2_train5", "weight": "0.75", "quantile": "0.65", "alpha_model_mode": "rank_only", "train_years": "5"},
]

RANK_ONLY_BASE = next(v for v in ROUND_1_VARIANTS if v["name"] == "alpha_rank_only")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def build_alpha_command(variant: Dict[str, str], *, shared_cache: Path, cpu_cores: int) -> List[str]:
    weight = variant.get("weight", "0.75")
    quantile = variant.get("quantile", "0.65")
    train_years = variant.get("train_years", "7")
    top_k = variant.get("top_k", "15")
    alpha_mode = variant.get("alpha_model_mode", "ensemble")
    lcb_z = variant.get("lcb_z", "0.10")
    min_edge = variant.get("min_edge", "0.001")
    return [
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
        alpha_mode,
        "--lcb-z",
        lcb_z,
        "--min-edge",
        min_edge,
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
        "--naive-momentum-variants",
        "mom_blend_top12",
        "--extra-benchmarks",
        "MTUM",
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
        "--no-statistical-diagnostics",
        "--no-custom-benchmarks",
        "--no-run-manifest",
    ]


@dataclass
class TuneResult:
    name: str
    returncode: int
    out_dir: str
    integrity: str
    elapsed_s: float
    strategy_sharpe: Optional[float] = None
    strategy_cagr: Optional[float] = None
    alpha_vs_momentum: Optional[AlphaMomentumComparison] = None
    alpha_score: float = -999.0
    beats_momentum: bool = False
    gate_reason: str = ""


def run_variant(
    variant: Dict[str, str],
    *,
    shared_cache: Path,
    cpu_cores: int,
    price_source: str,
    skip_completed: bool,
    thresholds: AlphaMomentumThresholds,
) -> TuneResult:
    name = variant["name"]
    out_dir = TUNING_ROOT / name
    out_dir.mkdir(parents=True, exist_ok=True)

    if skip_completed and _is_complete(out_dir):
        print(f"[SKIP] {name} already complete", flush=True)
    else:
        cmd = build_alpha_command(variant, shared_cache=shared_cache, cpu_cores=cpu_cores)
        env = noninteractive_env({"AA_PRICE_DATA_SOURCE": price_source, "AA_CPU_CORES": str(cpu_cores)})
        print(f"[RUN] {name} mode={variant.get('alpha_model_mode', 'ensemble')}", flush=True)
        t0 = time.monotonic()
        rc = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=_is_complete, env=env)
        elapsed = time.monotonic() - t0
        integrity = "PASS" if _is_complete(out_dir) else "FAIL"
        if rc != 0:
            return TuneResult(name=name, returncode=rc, out_dir=str(out_dir), integrity=integrity, elapsed_s=elapsed)

    sections = parse_report_sections(out_dir / "backtest_report.txt")
    cmp = extract_alpha_vs_momentum(out_dir)
    beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
    score = score_alpha_vs_momentum(cmp)
    return TuneResult(
        name=name,
        returncode=0,
        out_dir=str(out_dir),
        integrity="PASS" if _is_complete(out_dir) else "FAIL",
        elapsed_s=0.0,
        strategy_sharpe=sections.get("strategy", {}).get("sharpe_0rf"),
        strategy_cagr=sections.get("strategy", {}).get("cagr"),
        alpha_vs_momentum=cmp,
        alpha_score=score,
        beats_momentum=beats,
        gate_reason=reason,
    )


def _pick_best_result(results: List[TuneResult], variants: List[Dict[str, str]]) -> tuple[Optional[TuneResult], Dict[str, str]]:
    ranked = sorted(results, key=lambda r: r.alpha_score, reverse=True)
    best = ranked[0] if ranked else None
    if best is None or best.alpha_score <= -999:
        return best, dict(RANK_ONLY_BASE)
    variant = next((v for v in variants if v["name"] == best.name), dict(RANK_ONLY_BASE))
    return best, variant


def collect_all_results(thresholds: AlphaMomentumThresholds) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not TUNING_ROOT.is_dir():
        return rows
    for child in sorted(TUNING_ROOT.iterdir()):
        if not child.is_dir() or not (child / "backtest_report.txt").is_file():
            continue
        sections = parse_report_sections(child / "backtest_report.txt")
        cmp = extract_alpha_vs_momentum(child)
        beats, reason = alpha_beats_momentum_significantly(cmp, thresholds)
        rows.append(
            {
                "name": child.name,
                "integrity": "PASS" if (child / "latest_validated_run.json").is_file() else "UNKNOWN",
                "strategy_sharpe": sections.get("strategy", {}).get("sharpe_0rf"),
                "strategy_cagr": sections.get("strategy", {}).get("cagr"),
                "alpha_score": score_alpha_vs_momentum(cmp),
                "beats_momentum": beats,
                "gate_reason": reason,
                "alpha_vs_momentum": cmp.as_dict() if cmp else None,
                "out_dir": str(child),
            }
        )
    return sorted(rows, key=lambda r: float(r.get("alpha_score") or -999), reverse=True)


def write_final_results(thresholds: AlphaMomentumThresholds, *, target_met: bool) -> Path:
    rows = collect_all_results(thresholds)
    passing = [r for r in rows if r.get("beats_momentum")]
    payload = {
        "generated_at_utc": _utc_now(),
        "target_met": target_met,
        "thresholds": thresholds.as_dict(),
        "best_overall": rows[0]["name"] if rows else None,
        "winners": [r["name"] for r in passing],
        "results": rows,
    }
    out = TUNING_ROOT / "alpha_momentum_final_results.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    txt = TUNING_ROOT / "alpha_momentum_final_results.txt"
    lines = [
        "Alpha vs Momentum — Final Results",
        "=================================",
        f"Target met: {target_met}",
        f"Thresholds: CAGR diff >= {thresholds.min_cagr_diff}, Sharpe diff >= {thresholds.min_sharpe_diff}, IR >= {thresholds.min_information_ratio}",
        "",
    ]
    for row in rows[:15]:
        cmp = row.get("alpha_vs_momentum") or {}
        lines.append(
            f"{row['name']}: score={row.get('alpha_score')} CAGR={row.get('strategy_cagr')} Sharpe={row.get('strategy_sharpe')} "
            f"cagr_diff={cmp.get('cagr_diff')} sharpe_diff={cmp.get('sharpe_diff')} IR={cmp.get('information_ratio')} "
            f"gate={row.get('gate_reason')}"
        )
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out
    out = dict(base)
    out.update(changes)
    out["name"] = f"{base['name']}_{suffix}"
    return out


def _mutate_variant(base: Dict[str, str], suffix: str, **changes: str) -> Dict[str, str]:
    out = dict(base)
    out.update(changes)
    out["name"] = f"{base['name']}_{suffix}"
    return out


def expand_round_variants(best: Dict[str, str], round_index: int) -> List[Dict[str, str]]:
    """Generate a focused follow-up grid around the best alpha candidate."""
    w = float(best.get("weight", "0.75"))
    q = float(best.get("quantile", "0.65"))
    lcb = float(best.get("lcb_z", "0.10"))
    mode = best.get("alpha_model_mode", "ensemble")
    top_k = best.get("top_k", "15")
    variants = [
        _mutate_variant(best, f"r{round_index}_w{w:.2f}", weight=f"{max(0.45, w - 0.05):.2f}"),
        _mutate_variant(best, f"r{round_index}_w{w + 0.05:.2f}", weight=f"{min(0.85, w + 0.05):.2f}"),
        _mutate_variant(best, f"r{round_index}_q{q:.2f}", quantile=f"{max(0.55, q - 0.05):.2f}"),
        _mutate_variant(best, f"r{round_index}_q{q + 0.05:.2f}", quantile=f"{min(0.85, q + 0.05):.2f}"),
        _mutate_variant(best, f"r{round_index}_lcb{max(0.01, lcb - 0.03):.2f}", lcb_z=f"{max(0.01, lcb - 0.03):.2f}"),
        _mutate_variant(best, f"r{round_index}_lcb{lcb + 0.03:.2f}", lcb_z=f"{min(0.25, lcb + 0.03):.2f}"),
    ]
    if mode != "rank_only":
        variants.append(_mutate_variant(best, f"r{round_index}_rank", alpha_model_mode="rank_only"))
    if mode != "ml_only":
        variants.append(_mutate_variant(best, f"r{round_index}_ml", alpha_model_mode="ml_only"))
    if top_k != "12":
        variants.append(_mutate_variant(best, f"r{round_index}_top12", top_k="12"))
    if top_k != "15":
        variants.append(_mutate_variant(best, f"r{round_index}_top15", top_k="15"))
    if top_k != "18":
        variants.append(_mutate_variant(best, f"r{round_index}_top18", top_k="18"))
    if best.get("train_years", "7") != "5":
        variants.append(_mutate_variant(best, f"r{round_index}_train5", train_years="5"))
    if base_min := best.get("min_edge"):
        variants.append(_mutate_variant(best, f"r{round_index}_edge075", min_edge=f"{max(0.0005, float(base_min) * 0.75):.4f}"))
    else:
        variants.append(_mutate_variant(best, f"r{round_index}_edge075", min_edge="0.00075"))
    seen = set()
    unique: List[Dict[str, str]] = []
    for v in variants:
        if v["name"] in seen:
            continue
        seen.add(v["name"])
        unique.append(v)
    return unique


def write_summary(results: List[TuneResult], *, round_index: int, thresholds: AlphaMomentumThresholds) -> Path:
    TUNING_ROOT.mkdir(parents=True, exist_ok=True)
    ranked = sorted(results, key=lambda r: r.alpha_score, reverse=True)
    summary_path = TUNING_ROOT / f"alpha_momentum_round_{round_index}_summary.json"
    payload = {
        "generated_at_utc": _utc_now(),
        "round_index": round_index,
        "thresholds": thresholds.as_dict(),
        "results": [
            {
                "name": r.name,
                "returncode": r.returncode,
                "integrity": r.integrity,
                "alpha_score": r.alpha_score,
                "beats_momentum": r.beats_momentum,
                "gate_reason": r.gate_reason,
                "strategy_sharpe": r.strategy_sharpe,
                "strategy_cagr": r.strategy_cagr,
                "alpha_vs_momentum": r.alpha_vs_momentum.as_dict() if r.alpha_vs_momentum else None,
                "elapsed_s": round(r.elapsed_s, 1),
                "out_dir": r.out_dir,
            }
            for r in ranked
        ],
        "best": ranked[0].name if ranked else None,
        "target_met": any(r.beats_momentum for r in ranked),
    }
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    csv_path = TUNING_ROOT / f"alpha_momentum_round_{round_index}_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "name",
            "alpha_score",
            "beats_momentum",
            "cagr_diff",
            "sharpe_diff",
            "information_ratio",
            "strategy_sharpe",
            "strategy_cagr",
            "integrity",
            "gate_reason",
            "out_dir",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for r in ranked:
            cmp = r.alpha_vs_momentum
            writer.writerow(
                {
                    "name": r.name,
                    "alpha_score": r.alpha_score,
                    "beats_momentum": r.beats_momentum,
                    "cagr_diff": cmp.cagr_diff if cmp else None,
                    "sharpe_diff": cmp.sharpe_diff if cmp else None,
                    "information_ratio": cmp.information_ratio if cmp else None,
                    "strategy_sharpe": r.strategy_sharpe,
                    "strategy_cagr": r.strategy_cagr,
                    "integrity": r.integrity,
                    "gate_reason": r.gate_reason,
                    "out_dir": r.out_dir,
                }
            )
    return summary_path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tune until alpha beats momentum significantly")
    p.add_argument("--parallel-jobs", type=int, default=3)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--start-round", type=int, default=1)
    p.add_argument("--resume-rank-only", action="store_true", help="Skip round 1; start rank_only-focused grid")
    p.add_argument("--no-seed", action="store_true")
    p.add_argument("--fictive", action="store_true", default=True)
    p.add_argument("--internet", action="store_true")
    p.add_argument("--skip-completed", action="store_true", default=True)
    p.add_argument("--min-cagr-diff", type=float, default=0.03)
    p.add_argument("--min-sharpe-diff", type=float, default=0.08)
    p.add_argument("--min-ir", type=float, default=0.20)
    return p.parse_args()


def run_round(
    variants: List[Dict[str, str]],
    *,
    round_index: int,
    parallel_jobs: int,
    cpu_cores: int,
    price_source: str,
    skip_completed: bool,
    thresholds: AlphaMomentumThresholds,
) -> List[TuneResult]:
    results: List[TuneResult] = []
    if parallel_jobs <= 1 or len(variants) == 1:
        for variant in variants:
            results.append(
                run_variant(
                    variant,
                    shared_cache=SHARED_CACHE,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=skip_completed,
                    thresholds=thresholds,
                )
            )
    else:
        with ThreadPoolExecutor(max_workers=parallel_jobs) as pool:
            futs = {
                pool.submit(
                    run_variant,
                    variant,
                    shared_cache=SHARED_CACHE,
                    cpu_cores=cpu_cores,
                    price_source=price_source,
                    skip_completed=skip_completed,
                    thresholds=thresholds,
                ): variant
                for variant in variants
            }
            for fut in as_completed(futs):
                results.append(fut.result())
    write_summary(results, round_index=round_index, thresholds=thresholds)
    comparisons = [r.alpha_vs_momentum for r in results if r.alpha_vs_momentum is not None]
    best = max(results, key=lambda r: r.alpha_score, default=None)
    write_alpha_momentum_status(
        TUNING_ROOT / "alpha_momentum_status.json",
        comparisons=[c for c in comparisons if c is not None],
        thresholds=thresholds,
        best_name=best.name if best else "",
        round_index=round_index,
        target_met=any(r.beats_momentum for r in results),
        notes=f"round {round_index} complete",
    )
    return results


def main() -> int:
    args = parse_args()
    price_source = "internet" if args.internet else "fictive"
    parallel_jobs = max(1, min(int(args.parallel_jobs), 3))
    cpu_cores = max(4, 16 // parallel_jobs)
    thresholds = AlphaMomentumThresholds(
        min_cagr_diff=float(args.min_cagr_diff),
        min_sharpe_diff=float(args.min_sharpe_diff),
        min_information_ratio=float(args.min_ir),
    )

    SHARED_CACHE.mkdir(parents=True, exist_ok=True)
    TUNING_ROOT.mkdir(parents=True, exist_ok=True)

    if not args.no_seed:
        from tools.run_r3_parallel_tuning import seed_r3_price_cache  # noqa: WPS433

        seed_r3_price_cache(price_source=price_source)

    start_round = max(1, int(args.start_round))
    if args.resume_rank_only:
        start_round = max(start_round, 2)
        variants = list(RANK_FOCUS_VARIANTS)
        best_variant = dict(RANK_ONLY_BASE)
        scheduled_names = {v["name"] for v in ROUND_1_VARIANTS} | {v["name"] for v in RANK_FOCUS_VARIANTS}
    else:
        variants = list(ROUND_1_VARIANTS)
        best_variant = dict(RANK_ONLY_BASE)
        scheduled_names = {v["name"] for v in ROUND_1_VARIANTS}

    target_met = False
    end_round = int(args.max_rounds)

    for round_index in range(start_round, end_round + 1):
        print(
            f"[INFO] Alpha-vs-momentum round {round_index}: {len(variants)} variants, "
            f"thresholds cagr>={thresholds.min_cagr_diff}, sharpe>={thresholds.min_sharpe_diff}, "
            f"IR>={thresholds.min_information_ratio}",
            flush=True,
        )
        results = run_round(
            variants,
            round_index=round_index,
            parallel_jobs=parallel_jobs,
            cpu_cores=cpu_cores,
            price_source=price_source,
            skip_completed=bool(args.skip_completed),
            thresholds=thresholds,
        )
        passing = [r for r in results if r.beats_momentum]
        best, best_variant = _pick_best_result(results, variants)
        if best is not None:
            cmp = best.alpha_vs_momentum
            print(
                f"[ROUND {round_index}] Best={best.name} score={best.alpha_score:.4f} "
                f"cagr_diff={getattr(cmp, 'cagr_diff', None)} sharpe_diff={getattr(cmp, 'sharpe_diff', None)} "
                f"IR={getattr(cmp, 'information_ratio', None)} gate={best.gate_reason}",
                flush=True,
            )
        if passing:
            winner = max(passing, key=lambda r: r.alpha_score)
            print(
                f"[OK] Target met in round {round_index}: {winner.name} beats momentum ({winner.gate_reason})",
                flush=True,
            )
            target_met = True
            break
        if round_index >= end_round:
            break
        candidates = expand_round_variants(best_variant, round_index + 1)
        variants = []
        for candidate in candidates:
            if candidate["name"] in scheduled_names:
                continue
            scheduled_names.add(candidate["name"])
            variants.append(candidate)
        if not variants:
            print("[WARN] No new variants to explore.", flush=True)
            break

    final_path = write_final_results(thresholds, target_met=target_met)
    print(f"[OK] Final results: {final_path}", flush=True)
    if not target_met:
        print("[WARN] Max rounds reached without meeting alpha-vs-momentum target.", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
