#!/usr/bin/env python3
"""Follow-up research: cost-stress K0–K3 (R0 vs R3) and rescue-quantile tuning."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_risk_off_reporting import _load_daily_returns, _parse_report_metrics, write_risk_off_research_reports  # noqa: E402
from aa_reporting import calculate_metrics  # noqa: E402
from run_active_alpha_riskoff_experiments import (  # noqa: E402
    DEFAULT_CPU_CORES,
    RESEARCH_ROOT,
    SHARED_CACHE,
    _is_complete,
    experiment_out_dir,
    run_batch,
)

R0_BASE = RESEARCH_ROOT / "R0_LEGACY_ENSEMBLE"
R3_BASE = RESEARCH_ROOT / "R3_w070_q070_noexit"
R3_BASE_LEGACY = RESEARCH_ROOT / "R3_RISK_OFF_MOMENTUM_RESCUE"

R0_SPEC: Dict[str, Any] = {
    "risk_off_selection_mode": "legacy",
    "risk_off_gate_mode": "legacy",
    "risk_off_force_exit_enabled": False,
}
R3_SPEC: Dict[str, Any] = {
    "risk_off_selection_mode": "mom_blend_blend",
    "risk_off_momentum_variant": "mom_blend_top12",
    "risk_off_momentum_weight": "0.70",
    "risk_off_gate_mode": "momentum_rescue",
    "risk_off_force_exit_enabled": False,
}

COST_LEVELS = [
    ("K0", 2),
    ("K1", 5),
    ("K2", 10),
    ("K3", 15),
]

QUANTILE_LEVELS = [
    ("R3_q060", "0.60"),
    ("R3_q070", "0.70"),
    ("R3_q080", "0.80"),
]


def _metrics_row(out_dir: Path, *, label: str, slippage_bps: float, variant: str) -> Dict[str, Any]:
    daily = _load_daily_returns(out_dir / "strategy_daily_returns.csv")
    report = _parse_report_metrics(out_dir / "backtest_report.txt")
    m = calculate_metrics(daily) if not daily.empty else {}
    return {
        "label": label,
        "variant": variant,
        "slippage_bps": slippage_bps,
        "out_dir": str(out_dir),
        "cagr": m.get("cagr", report.get("strategy_cagr")),
        "sharpe_0rf": m.get("sharpe_0rf"),
        "max_drawdown": m.get("max_drawdown"),
        "total_tx_cost": report.get("total_tx_cost"),
        "approx_annual_turnover": report.get("approx_annual_turnover"),
    }


def build_cost_stress_experiments() -> List[Dict[str, Any]]:
    exps: List[Dict[str, Any]] = []
    for level, slip in COST_LEVELS:
        if level == "K0":
            continue
        for tag, spec, seed in (
            ("R0", R0_SPEC, R0_BASE),
            ("R3", R3_SPEC, R3_BASE),
        ):
            exps.append(
                {
                    "key": f"{level}_{tag}_SLIP{slip}",
                    "out_subdir": "cost_stress",
                    "slippage_bps": slip,
                    "seed_prediction_from": str(seed),
                    **spec,
                }
            )
    return exps


def build_quantile_experiments() -> List[Dict[str, Any]]:
    exps: List[Dict[str, Any]] = []
    for key, q in QUANTILE_LEVELS:
        if key == "R3_q070":
            continue
        exps.append(
            {
                "key": key,
                "out_subdir": "quantile_tune",
                "risk_off_momentum_rescue_quantile": q,
                **R3_SPEC,
            }
        )
    return exps


def write_cost_stress_summary(research_root: Path) -> Path:
    rows: List[Dict[str, Any]] = []
    for level, slip in COST_LEVELS:
        for tag in ("R0", "R3"):
            if level == "K0":
                out_dir = R0_BASE if tag == "R0" else R3_BASE
            else:
                out_dir = research_root / "cost_stress" / f"{level}_{tag}_SLIP{slip}"
            if not _is_complete(out_dir):
                continue
            rows.append(_metrics_row(out_dir, label=level, slippage_bps=slip, variant=tag))
    df = pd.DataFrame(rows)
    if not df.empty:
        for tag in ("R0", "R3"):
            base = df[(df["variant"] == tag) & (df["label"] == "K0")]
            if base.empty:
                continue
            base_cagr = float(base.iloc[0]["cagr"])
            mask = df["variant"] == tag
            df.loc[mask, "cagr_delta_vs_k0"] = df.loc[mask, "cagr"].astype(float) - base_cagr
        r0 = df[df["variant"] == "R0"].set_index("label")["cagr"].astype(float)
        r3 = df[df["variant"] == "R3"].set_index("label")["cagr"].astype(float)
        common = r0.index.intersection(r3.index)
        excess = r3.reindex(common) - r0.reindex(common)
        for level in common:
            df.loc[(df["label"] == level) & (df["variant"] == "R3"), "cagr_excess_vs_r0"] = float(excess[level])
    path = research_root / "risk_off_cost_stress_summary.csv"
    df.to_csv(path, index=False)
    return path


def write_quantile_summary(research_root: Path) -> Path:
    rows: List[Dict[str, Any]] = []
    candidates = [
        ("R3_q070", R3_BASE, 0.70),
        ("R3_q060", research_root / "quantile_tune" / "R3_q060", 0.60),
        ("R3_q080", research_root / "quantile_tune" / "R3_q080", 0.80),
    ]
    for key, out_dir, q in candidates:
        if not _is_complete(out_dir):
            continue
        row = _metrics_row(out_dir, label=key, slippage_bps=2.0, variant="R3")
        row["rescue_quantile"] = q
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty and "R3_q070" in set(df["label"]):
        base = float(df.loc[df["label"] == "R3_q070", "cagr"].iloc[0])
        df["cagr_delta_vs_q070"] = df["cagr"].astype(float) - base
    path = research_root / "risk_off_quantile_tuning_summary.csv"
    df.to_csv(path, index=False)
    return path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Risk-Off follow-up: cost stress + quantile tuning.")
    p.add_argument("--research-root", default=str(RESEARCH_ROOT))
    p.add_argument("--shared-cache-dir", default=str(SHARED_CACHE))
    p.add_argument("--parallel-jobs", type=int, default=2)
    p.add_argument("--cpu-cores", type=int, default=DEFAULT_CPU_CORES)
    p.add_argument("--only", choices=["cost", "quantile", "reports", "all"], default="all")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    research_root = Path(args.research_root)
    shared_cache = Path(args.shared_cache_dir)
    parallel_jobs = max(1, min(int(args.parallel_jobs), 4))
    cpu_cores = max(1, int(args.cpu_cores))

    if args.only in {"cost", "all"}:
        cost_exps = build_cost_stress_experiments()
        if args.dry_run:
            for e in cost_exps:
                print("[cost]", e["key"], "slip=", e["slippage_bps"])
        else:
            print(f"[PHASE] cost stress ({len(cost_exps)} runs)", flush=True)
            rc = run_batch(
                cost_exps,
                research_root=research_root,
                shared_cache=shared_cache,
                parallel_jobs=parallel_jobs,
                cpu_cores=cpu_cores,
                grace_seconds=90,
            )
            if rc != 0:
                return rc

    if args.only in {"quantile", "all"}:
        q_exps = build_quantile_experiments()
        if args.dry_run:
            for e in q_exps:
                print("[quantile]", e["key"], "q=", e["risk_off_momentum_rescue_quantile"])
        else:
            print(f"[PHASE] quantile tuning ({len(q_exps)} runs)", flush=True)
            for exp in q_exps:
                rc = run_batch(
                    [exp],
                    research_root=research_root,
                    shared_cache=shared_cache,
                    parallel_jobs=1,
                    cpu_cores=cpu_cores,
                    grace_seconds=90,
                )
                if rc != 0:
                    return rc

    if args.dry_run:
        return 0

    if args.only in {"reports", "all", "cost", "quantile"}:
        main_variant_dirs = {
            "R0_LEGACY_ENSEMBLE": research_root / "R0_LEGACY_ENSEMBLE",
            "R1_GATE_BASE_ONLY": research_root / "R1_GATE_BASE_ONLY",
            "R2_MOM_BLEND_REPLACE": research_root / "R2_MOM_BLEND_REPLACE",
            "R3_RISK_OFF_MOMENTUM_RESCUE": research_root / "R3_RISK_OFF_MOMENTUM_RESCUE",
            "R4_RISK_OFF_MOMENTUM_RESCUE_FORCE_EXIT": research_root / "R4_RISK_OFF_MOMENTUM_RESCUE_FORCE_EXIT",
            "M1_MOM_BLEND_MATCHED_CONTROLS": research_root / "M1_MOM_BLEND_MATCHED_CONTROLS",
            "NAIVE_MOM_BLEND_TOP12": research_root / "R0_LEGACY_ENSEMBLE",
            "NAIVE_MOM_63_TOP12": research_root / "R0_LEGACY_ENSEMBLE",
        }
        paths = write_risk_off_research_reports(research_root, main_variant_dirs)
        for p in paths:
            print(f"[OK] {p}", flush=True)
        cs = write_cost_stress_summary(research_root)
        print(f"[OK] {cs}", flush=True)
        qs = write_quantile_summary(research_root)
        print(f"[OK] {qs}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
