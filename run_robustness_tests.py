#!/usr/bin/env python3
"""Trading-212-only robustness lab for Active Alpha.

Runs a broader stress and ablation matrix:
- FX0/FX15, slippage 2/5/10/15 bps and small market-impact stress
- conservative/balanced/active/threshold policies
- Top-N universe 100/150/250/500
- beta cap 1.10/1.25/1.35/1.50 and fixed-vs-dynamic beta-cap modes
- top_k 8/12/20/30
- alpha model ablations: ensemble, rank_only, ml_only, elastic_only, gbm_only
- tail-prune on/off and residual sweep stresses

Shared feature/price caches live under ``--shared-cache-dir`` (default:
``robustness_results_trading212/_shared_cache``). Each variant still writes its
own reports under ``robustness_results_trading212/<variant>/``.

Outputs:
- robustness_results_trading212/robustness_summary.csv
- robustness_results_trading212/robustness_summary.txt
- robustness_results_trading212/<variant>/run.log
- per-variant model outputs including benchmark_comparison.csv, factor_proxy_regression.csv, run_manifest.json
"""
from __future__ import annotations

import argparse
import csv
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path.cwd()
RESULTS_DIR = ROOT / "robustness_results_trading212"
DEFAULT_SHARED_CACHE = RESULTS_DIR / "_shared_cache"

DEFAULT_EXTRA_BENCHMARKS = "QQQ,RSP,MTUM,QUAL,VUG,VLUE,USMV,SMH"

BASE = [
    sys.executable, "active_alpha_model.py",
    "--mode", "both",
    "--ticker-source", "sp500_pit",
    "--membership-file", "ticker_membership.csv",
    "--membership-mode", "strict",
    "--benchmark", "SPY",
    "--extra-benchmarks", DEFAULT_EXTRA_BENCHMARKS,
    "--start", "2012-01-01",
    "--universe-mode", "diy_pit_liquidity",
    "--universe-top-n", "100",
    "--fee-model", "trading212_us",
    "--backtest-capital", "1000",
    "--execution-policy-mode", "capital_curve",
    "--max-gross-exposure", "1.0",
    "--order-value-rounding", "1.0",
    "--broker-min-remaining-position-value", "1.0",
    "--n-jobs", "auto",
    "--cpu-cores", "16",
    "--system-ram-gb", "64",
    "--parallel-profile", "high",
    "--parallel-backtest-backend", "thread",
    "--reuse-feature-cache",
    "--reuse-prediction-cache",
    "--skip-download-if-cached",
    "--no-naive-overlap",
    "--plain-progress",
    "--no-gui",
    "--cluster-mode",
    "static",
    "--risk-off-selection-mode", "mom_blend_blend",
    "--risk-off-momentum-variant", "mom_blend_top12",
    "--risk-off-momentum-weight", "0.70",
    "--risk-off-gate-mode", "momentum_rescue",
    "--risk-off-momentum-rescue-quantile", "0.70",
]

# Keep this intentionally finite. Full robustness is expensive because every run
# downloads/builds features and performs walk-forward ML. Add variants by editing
# the list; no hidden grid expansion is performed.
VARIANTS: List[Dict[str, Any]] = [
    {"name": "core_alpha_return_staticcluster_spycompletion_k15_pos12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 15, "max_position": 0.12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "soft_cap": 35, "hard_cap": 45, "cluster_constraint_mode": "static_only", "static_cluster_cap": 0.40, "dynamic_cluster_cap": 0.50, "cash_filler_mode": "benchmark_completion", "benchmark_completion_ticker": "SPY", "benchmark_completion_max_weight": 0.25, "dynamic_beta_risk_on": 1.40, "dynamic_beta_strong": 1.50, "description": "Recommended single Active Alpha Core model."},
    # Baselines / policies
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "soft_cap": 35, "hard_cap": 45, "description": "Current research baseline."},
    {"name": "threshold_tail005_fx15_slip2_top100_beta125_k12", "policy": "threshold", "fx": 15, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "FX stress."},
    {"name": "conservative_fx0_slip2_top100_beta125_k12", "policy": "conservative", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Slower/lower-turnover policy."},
    {"name": "balanced_fx0_slip2_top100_beta125_k12", "policy": "balanced", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Balanced policy."},
    {"name": "active_fx0_slip2_top100_beta125_k12", "policy": "active", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "More active policy."},

    # Execution costs
    {"name": "threshold_tail005_fx0_slip5_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 5, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "5 bps slippage."},
    {"name": "threshold_tail005_fx0_slip10_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 10, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "10 bps slippage."},
    {"name": "threshold_tail005_fx0_slip15_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 15, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "15 bps severe slippage."},
    {"name": "threshold_tail005_fx0_slip2_impact2_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "impact": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Small market-impact buffer."},

    # Universe breadth
    {"name": "threshold_tail005_fx0_slip2_top150_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 150, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Universe top 150."},
    {"name": "threshold_tail005_fx0_slip2_top250_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 250, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Universe top 250."},
    {"name": "threshold_tail005_fx0_slip2_top500_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 500, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Fuller S&P 500 liquidity universe."},

    # Beta cap sensitivity
    {"name": "threshold_tail005_fx0_slip2_top100_beta110_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.10, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Tighter beta cap."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta135_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.35, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Looser beta cap."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta150_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.50, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Aggressive beta cap stress."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_fixedbeta", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "beta_cap_mode": "fixed", "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Fixed beta cap control versus dynamic beta."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_nolowbetafiller", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "cash_filler_mode": "balanced", "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Cash filler without low-beta diversification sleeve."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_staticcluster", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "cluster_constraint_mode": "static_only", "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Static cluster cap only."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_bothcluster", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "cluster_constraint_mode": "both_restrictive", "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Static and dynamic cluster caps enforced restrictively."},

    # Concentration sensitivity
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k8", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 8, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "More concentrated top_k."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k20", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 20, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Broader top_k."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k30", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 30, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "description": "Much broader top_k."},

    # Alpha-stack ablations
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_rank_only", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "rank_only", "tail_prune": True, "residual_floor": 0.005, "description": "No ML; rank_score only."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_ml_only", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ml_only", "tail_prune": True, "residual_floor": 0.005, "description": "ML only; excludes rank fallback."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_elastic_only", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "elastic_only", "tail_prune": True, "residual_floor": 0.005, "description": "Linear model ablation."},
    {"name": "threshold_tail005_fx0_slip2_top100_beta125_k12_gbm_only", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "gbm_only", "tail_prune": True, "residual_floor": 0.005, "description": "Tree model ablation."},

    # Tail-prune / hygiene sensitivity
    {"name": "threshold_no_tail_fx0_slip2_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": False, "description": "No tail-prune hygiene."},
    {"name": "threshold_tail010_fx0_slip2_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.010, "description": "Stricter residual sweep."},
    {"name": "threshold_tail005_soft30_fx0_slip2_top100_beta125_k12", "policy": "threshold", "fx": 0, "slip": 2, "topn": 100, "beta": 1.25, "top_k": 12, "model_mode": "ensemble", "tail_prune": True, "residual_floor": 0.005, "soft_cap": 30, "hard_cap": 45, "description": "Tighter soft position cap."},
]

METRIC_KEYS = [
    "strategy_total_return", "strategy_cagr", "strategy_annual_vol", "strategy_sharpe_0rf", "strategy_max_drawdown",
    "information_ratio", "tracking_error", "excess_cagr_approx",
    "benchmark_total_return", "benchmark_cagr", "benchmark_annual_vol", "benchmark_sharpe_0rf", "benchmark_max_drawdown",
    "vs_QQQ_cagr_diff", "vs_QQQ_information_ratio", "vs_QQQ_correlation",
    "vs_RSP_cagr_diff", "vs_MTUM_cagr_diff", "vs_QUAL_cagr_diff", "vs_VUG_cagr_diff", "vs_SMH_cagr_diff",
    "vs_NAIVE_MOMENTUM_TOPK_RANK_cagr_diff", "vs_NAIVE_MOMENTUM_TOPK_RANK_information_ratio",
    "factor_r_squared", "factor_intercept_annualized",
    "avg_tx_cost", "avg_tx_cost_dollars", "avg_fx_fee_cost", "avg_slippage_cost", "approx_annual_turnover",
    "avg_portfolio_exposure", "avg_portfolio_beta", "avg_exposure_when_risk_on", "avg_beta_when_risk_on", "risk_on_share",
    "avg_n_positions", "max_n_positions", "avg_constraint_violations", "max_constraint_violations",
    "avg_tail_prune_constraint_failure", "max_tail_prune_constraint_failure",
    "avg_hard_position_cap_breach", "max_hard_position_cap_breach",
]


def parse_report(path: Path) -> Dict[str, float | str]:
    out: Dict[str, float | str] = {}
    if not path.exists():
        out["error"] = "missing backtest_report.txt"
        return out
    section = ""
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in {"Strategy metrics", "Benchmark metrics", "Portfolio diagnostics"}:
            section = line
            continue
        if ":" not in line or line.startswith("-"):
            continue
        k, v = [x.strip() for x in line.split(":", 1)]
        prefix = ""
        if section == "Strategy metrics":
            prefix = "strategy_" if k not in {"information_ratio", "tracking_error", "excess_cagr_approx"} else ""
        elif section == "Benchmark metrics":
            prefix = "benchmark_"
        key = prefix + k
        try:
            out[key] = float(v)
        except Exception:
            out[key] = v
    return out


def parse_benchmark_comparison(path: Path) -> Dict[str, float | str]:
    out: Dict[str, float | str] = {}
    if not path.exists():
        return out
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                bm = str(row.get("benchmark", "")).strip()
                if not bm:
                    continue
                safe = bm.replace("-", "_").replace("^", "").replace(".", "_")
                for k in ["cagr_diff", "information_ratio", "correlation", "beta_to_benchmark", "benchmark_cagr", "benchmark_sharpe_0rf"]:
                    try:
                        out[f"vs_{safe}_{k}"] = float(row.get(k, ""))
                    except Exception:
                        pass
    except Exception as exc:
        out["benchmark_comparison_error"] = str(exc)
    return out


def parse_factor_regression(path: Path) -> Dict[str, float | str]:
    out: Dict[str, float | str] = {}
    if not path.exists():
        return out
    try:
        with path.open("r", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                term = str(row.get("term", "")).strip()
                if term == "intercept_daily":
                    out["factor_intercept_daily"] = float(row.get("coefficient", "nan"))
                    out["factor_intercept_annualized"] = float(row.get("annualized", "nan"))
                    out["factor_r_squared"] = float(row.get("r_squared", "nan"))
                elif term:
                    key = term.replace("-", "_").replace("^", "").replace(".", "_")
                    try:
                        out[f"factor_beta_{key}"] = float(row.get("coefficient", "nan"))
                    except Exception:
                        pass
    except Exception as exc:
        out["factor_regression_error"] = str(exc)
    return out


def f(row: Dict[str, object], key: str, default: float = 0.0) -> float:
    try:
        val = float(row.get(key, default))
        return val if val == val else default
    except Exception:
        return default


def score(row: Dict[str, object]) -> tuple[float, str]:
    ir = f(row, "information_ratio")
    sharpe_delta = f(row, "strategy_sharpe_0rf") - f(row, "benchmark_sharpe_0rf")
    excess = f(row, "excess_cagr_approx")
    qqq_diff = f(row, "vs_QQQ_cagr_diff")
    naive_diff = f(row, "vs_NAIVE_MOMENTUM_TOPK_RANK_cagr_diff")
    dd_penalty = max(0.0, abs(f(row, "strategy_max_drawdown")) - abs(f(row, "benchmark_max_drawdown")))
    annual_cost = f(row, "avg_tx_cost") * (252.0 / max(1.0, f(row, "policy_rebalance_every", 10)))
    overturnover = max(0.0, f(row, "approx_annual_turnover") - 20.0) / 20.0
    s = (
        0.28 * ir + 0.20 * sharpe_delta + 0.20 * excess
        + 0.12 * qqq_diff + 0.15 * naive_diff
        - 0.10 * dd_penalty - 0.05 * annual_cost - 0.05 * overturnover
    )
    reasons = []
    if f(row, "avg_exposure_when_risk_on") < 0.85:
        reasons.append("risk_on_exposure_below_85pct")
    if f(row, "information_ratio") <= 0:
        reasons.append("non_positive_IR")
    if f(row, "max_constraint_violations") > 0:
        reasons.append("constraint_violation")
    if f(row, "max_hard_position_cap_breach") > 0:
        reasons.append("hard_position_cap_breach")
    if f(row, "max_tail_prune_constraint_failure") > 0:
        reasons.append("tail_prune_constraint_failure")
    if annual_cost > 0.03:
        reasons.append("annual_cost_above_3pct")
    if f(row, "approx_annual_turnover") > 25:
        reasons.append("turnover_high")
    if "vs_NAIVE_MOMENTUM_TOPK_RANK_cagr_diff" in row and f(row, "vs_NAIVE_MOMENTUM_TOPK_RANK_cagr_diff") <= 0:
        reasons.append("does_not_beat_naive_momentum")
    if "vs_QQQ_cagr_diff" in row and f(row, "vs_QQQ_cagr_diff") <= 0:
        reasons.append("does_not_beat_QQQ")
    return s, ";".join(reasons) if reasons else "PASS"


def variant_output_dir(name: str) -> Path:
    return RESULTS_DIR / name


def variant_is_complete(out_dir: Path) -> bool:
    """True when a prior variant run produced a usable backtest report."""
    report = out_dir / "backtest_report.txt"
    if not report.exists() or report.stat().st_size < 40:
        return False
    text = report.read_text(encoding="utf-8", errors="ignore")
    return "Strategy metrics" in text and "total_return" in text


def partition_variants(
    variants: List[Dict[str, Any]],
    *,
    skip_completed: bool,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not skip_completed:
        return list(variants), []
    pending: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for v in variants:
        out_dir = variant_output_dir(str(v["name"]))
        if variant_is_complete(out_dir):
            skipped.append(v)
        else:
            pending.append(v)
    return pending, skipped


def build_variant_command(v: Dict[str, object], shared_cache_dir: Path) -> List[str]:
    name = str(v["name"])
    out_dir = RESULTS_DIR / name
    cmd = list(BASE)
    cmd += ["--trading212-policy", str(v.get("policy", "threshold"))]
    cmd += ["--trading212-fx-bps", str(v.get("fx", 0))]
    cmd += ["--slippage-bps", str(v.get("slip", 2))]
    cmd += ["--market-impact-bps", str(v.get("impact", 0))]
    cmd += ["--universe-top-n", str(v.get("topn", 100))]
    cmd += ["--max-portfolio-beta", str(v.get("beta", 1.25))]
    cmd += ["--beta-cap-mode", str(v.get("beta_cap_mode", "dynamic"))]
    cmd += ["--dynamic-beta-risk-off", str(v.get("dynamic_beta_risk_off", 1.10))]
    cmd += ["--dynamic-beta-normal", str(v.get("dynamic_beta_normal", 1.25))]
    cmd += ["--dynamic-beta-risk-on", str(v.get("dynamic_beta_risk_on", 1.40))]
    cmd += ["--dynamic-beta-strong", str(v.get("dynamic_beta_strong", 1.50))]
    cmd += ["--static-cluster-cap", str(v.get("static_cluster_cap", 0.40))]
    cmd += ["--dynamic-cluster-cap", str(v.get("dynamic_cluster_cap", 0.50))]
    cmd += ["--cluster-constraint-mode", str(v.get("cluster_constraint_mode", "static_only"))]
    cmd += ["--cash-filler-mode", str(v.get("cash_filler_mode", "benchmark_completion"))]
    cmd += ["--benchmark-completion-ticker", str(v.get("benchmark_completion_ticker", "SPY"))]
    cmd += ["--benchmark-completion-max-weight", str(v.get("benchmark_completion_max_weight", 0.25))]
    cmd += ["--low-beta-filler-max-position", str(v.get("low_beta_filler_max_position", 0.015))]
    cmd += ["--low-beta-filler-beta-max", str(v.get("low_beta_filler_beta_max", 0.90))]
    cmd += ["--low-beta-filler-min-score", str(v.get("low_beta_filler_min_score", -0.05))]
    cmd += ["--low-beta-filler-max-vol-63", str(v.get("low_beta_filler_max_vol_63", 0.75))]
    cmd += ["--research-backtest-capital", str(v.get("research_backtest_capital", 100000))]
    cmd += ["--top-k", str(v.get("top_k", 15))]
    cmd += ["--alpha-model-mode", str(v.get("model_mode", "ensemble"))]
    cmd += ["--shared-cache-dir", str(shared_cache_dir)]
    cmd += ["--out-dir", str(out_dir)]
    if "max_position" in v:
        cmd += ["--max-position", str(v["max_position"])]
    if bool(v.get("tail_prune", False)):
        cmd += [
            "--tail-prune-enabled",
            "--residual-weight-floor", str(v.get("residual_floor", 0.005)),
            "--max-n-positions-soft", str(v.get("soft_cap", 35)),
            "--max-n-positions-hard", str(v.get("hard_cap", 45)),
            "--residual-sell-min-value", str(v.get("residual_sell_min_value", 0.01)),
            "--max-tail-reallocation-per-name", str(v.get("max_tail_reallocation_per_name", 0.01)),
            "--tail-reallocation-step", str(v.get("tail_reallocation_step", 0.0025)),
            "--tail-reallocation-rounds", str(v.get("tail_reallocation_rounds", 10)),
            "--tail-prune-min-exposure-buffer", str(v.get("tail_prune_min_exposure_buffer", 0.02)),
        ]
    for arg in v.get("extra_args", []):
        cmd.append(str(arg))
    return cmd


def run_variant(v: Dict[str, object], shared_cache_dir: Path) -> Dict[str, object]:
    from aa_subprocess_runner import run_logged_subprocess

    name = str(v["name"])
    out_dir = RESULTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_variant_command(v, shared_cache_dir)
    print(f"[RUN] {name}")
    returncode = run_logged_subprocess(cmd, cwd=ROOT, out_dir=out_dir, is_complete=variant_is_complete)
    row: Dict[str, object] = {
        "name": name,
        "description": v.get("description", ""),
        "returncode": returncode,
        "policy": v.get("policy", ""),
        "fx_bps": v.get("fx", ""),
        "slippage_bps": v.get("slip", ""),
        "market_impact_bps": v.get("impact", 0),
        "universe_top_n": v.get("topn", ""),
        "max_portfolio_beta": v.get("beta", ""),
        "beta_cap_mode": v.get("beta_cap_mode", "dynamic"),
        "cluster_constraint_mode": v.get("cluster_constraint_mode", "static_only"),
        "cash_filler_mode": v.get("cash_filler_mode", "benchmark_completion"),
        "top_k": v.get("top_k", ""),
        "alpha_model_mode": v.get("model_mode", "ensemble"),
        "tail_prune": bool(v.get("tail_prune", False)),
        "residual_floor": v.get("residual_floor", ""),
        "soft_cap": v.get("soft_cap", ""),
        "hard_cap": v.get("hard_cap", ""),
        "shared_cache_dir": str(shared_cache_dir),
        "out_dir": str(out_dir),
    }
    row.update(parse_report(out_dir / "backtest_report.txt"))
    row.update(parse_benchmark_comparison(out_dir / "benchmark_comparison.csv"))
    row.update(parse_factor_regression(out_dir / "factor_proxy_regression.csv"))
    report = (out_dir / "backtest_report.txt").read_text(encoding="utf-8", errors="ignore") if (out_dir / "backtest_report.txt").exists() else ""
    for line in report.splitlines():
        if line.startswith("rebalance_every:") or line.startswith("policy_rebalance_every:"):
            try:
                row["policy_rebalance_every"] = float(line.split(":", 1)[1].strip())
            except Exception:
                pass
    sc, flag = score(row)
    row["robustness_score"] = sc
    row["status"] = "FAIL" if returncode != 0 else flag
    row["command"] = " ".join(cmd)
    return row


def run_variants(selected: List[Dict[str, Any]], shared_cache_dir: Path, parallel_jobs: int) -> List[Dict[str, object]]:
    jobs = max(1, min(int(parallel_jobs), 4))
    if jobs == 1 or len(selected) <= 1:
        return [run_variant(v, shared_cache_dir) for v in selected]
    rows: List[Dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(run_variant, v, shared_cache_dir): v for v in selected}
        for fut in as_completed(futures):
            rows.append(fut.result())
    rows.sort(key=lambda r: str(r.get("name", "")))
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Active Alpha robustness and ablation variants.")
    parser.add_argument("--list", action="store_true", help="List variant names and exit.")
    parser.add_argument("--only", default="", help="Comma-separated variant names or substrings to run.")
    parser.add_argument("--max-variants", type=int, default=0, help="Run at most this many selected variants. 0 = no limit.")
    parser.add_argument("--shared-cache-dir", default=str(DEFAULT_SHARED_CACHE), help="Shared feature/price cache root for all variants.")
    parser.add_argument("--parallel-jobs", type=int, default=2, help="Run up to N variants in parallel (1-4). Default 2.")
    parser.add_argument("--dry-run", action="store_true", help="Print selected variants and commands without running them.")
    parser.add_argument("--skip-completed", action="store_true", help="Skip variants that already have backtest_report.txt in their out_dir.")
    return parser.parse_args()


def select_variants(args: argparse.Namespace) -> List[Dict[str, Any]]:
    selected = list(VARIANTS)
    if args.only.strip():
        needles = [x.strip().lower() for x in args.only.split(",") if x.strip()]
        selected = [v for v in selected if any(n in str(v.get("name", "")).lower() for n in needles)]
    if args.max_variants and args.max_variants > 0:
        selected = selected[: int(args.max_variants)]
    return selected


def main() -> int:
    args = parse_args()
    selected = select_variants(args)
    pending, skipped = partition_variants(selected, skip_completed=bool(args.skip_completed))
    shared_cache_dir = Path(args.shared_cache_dir)
    if args.list:
        for v in selected:
            mark = " [done]" if v in skipped else ""
            print(f"{v['name']}{mark}  --  {v.get('description','')}")
        return 0
    if args.dry_run:
        print(f"shared_cache_dir: {shared_cache_dir.resolve()}")
        print(f"parallel_jobs: {max(1, min(int(args.parallel_jobs), 4))}")
        print(f"variants: {len(pending)} run / {len(skipped)} skip (skip_completed={bool(args.skip_completed)})")
        print("")
        for v in pending:
            cmd = build_variant_command(v, shared_cache_dir)
            print(f"# {v['name']}")
            print(" ".join(cmd))
            print("")
        if skipped:
            print("# skipped (already complete):")
            for v in skipped:
                print(f"#   {v['name']}")
        return 0
    if skipped:
        print(f"[INFO] Skipping {len(skipped)} completed variant(s).")
    if not pending:
        print("[OK] All selected variants already complete.")
        return 0
    shared_cache_dir.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = run_variants(pending, shared_cache_dir, args.parallel_jobs)
    fields = [
        "name", "description", "returncode", "status", "robustness_score", "policy", "fx_bps", "slippage_bps",
        "market_impact_bps", "universe_top_n", "max_portfolio_beta", "beta_cap_mode", "cluster_constraint_mode", "cash_filler_mode", "top_k", "alpha_model_mode", "tail_prune",
        "residual_floor", "soft_cap", "hard_cap", "shared_cache_dir", "out_dir",
    ] + METRIC_KEYS
    fields = list(dict.fromkeys(fields + sorted({k for r in rows for k in r.keys()})))
    csv_path = RESULTS_DIR / "robustness_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    txt_path = RESULTS_DIR / "robustness_summary.txt"
    ranked = sorted(rows, key=lambda r: float(r.get("robustness_score", -999)), reverse=True)
    lines = [
        "Trading-212 Robustness Summary",
        "==============================",
        "",
        f"variants: {len(rows)}",
        f"shared_cache_dir: {shared_cache_dir.resolve()}",
        f"parallel_jobs: {max(1, min(int(args.parallel_jobs), 4))}",
        f"csv: {csv_path}",
        "",
        "Top variants by robustness_score:",
    ]
    for r in ranked[:15]:
        lines.append(
            f"- {r.get('name')}: score={float(r.get('robustness_score',0)):.4f}, status={r.get('status')}, "
            f"CAGR={float(r.get('strategy_cagr',0)):.2%}, SPY={float(r.get('benchmark_cagr',0)):.2%}, "
            f"QQQdiff={float(r.get('vs_QQQ_cagr_diff',0)):.2%}, NaiveDiff={float(r.get('vs_NAIVE_MOMENTUM_TOPK_RANK_cagr_diff',0)):.2%}, "
            f"IR={float(r.get('information_ratio',0)):.3f}, DD={float(r.get('strategy_max_drawdown',0)):.2%}, TO={float(r.get('approx_annual_turnover',0)):.2f}x"
        )
    lines.append("")
    lines.append("Failures / caution flags:")
    for r in ranked:
        if str(r.get("status", "")) not in {"PASS", ""}:
            lines.append(f"- {r.get('name')}: {r.get('status')}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[OK] {csv_path}")
    print(f"[OK] {txt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
