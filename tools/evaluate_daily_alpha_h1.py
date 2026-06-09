#!/usr/bin/env python3
"""Evaluate DAILY_ALPHA_H1 vs mom_1_top12 net of daily turnover cost stress."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VARIANT = "DAILY_ALPHA_H1"
BENCHMARK_SUFFIX = "mom_1_top12"
EVIDENCE_REL = Path("evidence/daily_alpha_h1_evaluation_latest.json")
LEDGER_REL = Path("research_evidence/r0_tuning_trial_ledger.json")


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


def _load_returns(path: Path, column: Optional[str] = None):
    import pandas as pd

    if not path.is_file():
        return None
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    if column and column in frame.columns:
        col = column
    elif "strategy_return" in frame.columns:
        col = "strategy_return"
    else:
        cols = [c for c in frame.columns if "mom" in str(c).lower() or "return" in str(c).lower()]
        col = cols[0] if cols else frame.columns[0]
    return pd.to_numeric(frame[col], errors="coerce").dropna()


def _evaluation_message_de(
    root: Path,
    *,
    metrics_strategy: Dict[str, Any],
    metrics_benchmark: Dict[str, Any],
    metrics_strategy_stress: Dict[str, Any],
    metrics_benchmark_stress: Dict[str, Any],
    pass_full: bool,
    extra_bps: float,
) -> str:
    if metrics_benchmark:
        return (
            f"DAILY_ALPHA_H1 {'SEAL PASS' if pass_full else 'FAIL'} vs {BENCHMARK_SUFFIX} "
            f"(Sharpe {metrics_strategy.get('sharpe_0rf', 0):.3f} vs {metrics_benchmark.get('sharpe_0rf', 0):.3f}; "
            f"+{extra_bps:.0f}bps Turnover-Stress: "
            f"{metrics_strategy_stress.get('sharpe_0rf', 0):.3f} vs {metrics_benchmark_stress.get('sharpe_0rf', 0):.3f})."
        )
    try:
        from analytics.h1_seal_policy import is_h1_benchmark_required

        if not is_h1_benchmark_required(root) and metrics_strategy:
            sharpe = float(metrics_strategy.get("sharpe_0rf") or 0)
            return (
                f"H1 COMPLETE — mom_1-Benchmark optional (control/h1_seal_policy.json). "
                f"Strategie Sharpe {sharpe:.3f} — pass_full_seal informativ."
            )
    except Exception:
        pass
    return "Benchmark returns fehlen — Backtest noch nicht vollständig."


def evaluate_run(root: Path, run_dir: Path) -> Dict[str, Any]:
    from aa_reporting import calculate_metrics
    from analytics.live_profile_governance import (
        DAILY_COST_STRESS_EXTRA_BPS,
        apply_cost_stress_to_returns,
        daily_trading_fee_context,
        load_run_turnover,
    )

    root = Path(root)
    run_dir = Path(run_dir)
    from aa_backtest import _naive_artifact_slug

    strat_path = run_dir / "strategy_daily_returns.csv"
    bench_slug = _naive_artifact_slug(BENCHMARK_SUFFIX)
    bench_candidates = [
        run_dir / f"{bench_slug}_daily_returns.csv",
        run_dir / f"naive_momentum_{BENCHMARK_SUFFIX}_daily_returns.csv",
        run_dir / "naive_momentum_daily_returns.csv",
    ]
    bench_path = next((p for p in bench_candidates if p.is_file()), None)

    strat = _load_returns(strat_path)
    bench = _load_returns(bench_path) if bench_path else None
    if strat is None or strat.empty:
        return {"ok": False, "reason": "strategy_returns_missing", "run_dir": str(run_dir)}

    turnover = load_run_turnover(root, run_dir)
    fee_ctx = daily_trading_fee_context(root)
    extra_bps = float(fee_ctx.get("cost_stress_incremental_bps") or DAILY_COST_STRESS_EXTRA_BPS)

    metrics_strategy = calculate_metrics(strat)
    metrics_benchmark = calculate_metrics(bench) if bench is not None and not bench.empty else {}

    stressed_strat = strat
    stressed_bench = bench
    if turnover is not None and not turnover.empty:
        stressed_strat, _ = apply_cost_stress_to_returns(strat, turnover, extra_bps=extra_bps)
        if bench is not None and not bench.empty:
            stressed_bench, _ = apply_cost_stress_to_returns(bench, turnover, extra_bps=extra_bps)

    metrics_strategy_stress = calculate_metrics(stressed_strat)
    metrics_benchmark_stress = (
        calculate_metrics(stressed_bench) if stressed_bench is not None and not stressed_bench.empty else {}
    )

    beats_sharpe = False
    beats_sharpe_stress = False
    mdd_ok = True
    mdd_stress_ok = True
    if metrics_benchmark:
        beats_sharpe = float(metrics_strategy.get("sharpe_0rf", 0)) > float(metrics_benchmark.get("sharpe_0rf", 0))
        mdd_ok = float(metrics_strategy.get("max_drawdown", -1)) >= float(metrics_benchmark.get("max_drawdown", -1))
    if metrics_benchmark_stress:
        beats_sharpe_stress = float(metrics_strategy_stress.get("sharpe_0rf", 0)) > float(
            metrics_benchmark_stress.get("sharpe_0rf", 0)
        )
        mdd_stress_ok = float(metrics_strategy_stress.get("max_drawdown", -1)) >= float(
            metrics_benchmark_stress.get("max_drawdown", -1)
        )

    pass_objective = bool(metrics_benchmark) and beats_sharpe and mdd_ok
    pass_daily_cost_stress = bool(metrics_benchmark_stress) and beats_sharpe_stress and mdd_stress_ok
    pass_full = pass_objective and pass_daily_cost_stress

    return {
        "ok": True,
        "run_dir": str(run_dir.relative_to(root)).replace("\\", "/"),
        "objective_ref": "control/r0_migration/alpha_objective.json",
        "benchmark_variant": BENCHMARK_SUFFIX,
        "benchmark_returns_path": str(bench_path.relative_to(root)).replace("\\", "/") if bench_path else None,
        "pass_alpha_objective": pass_objective,
        "pass_daily_cost_stress": pass_daily_cost_stress,
        "pass_full_seal": pass_full,
        "beats_benchmark_sharpe": beats_sharpe,
        "beats_benchmark_sharpe_after_cost_stress": beats_sharpe_stress,
        "max_drawdown_not_worse": mdd_ok,
        "max_drawdown_not_worse_after_cost_stress": mdd_stress_ok,
        "cost_stress_extra_bps_on_turnover": extra_bps,
        "daily_trading_fee_context": fee_ctx,
        "metrics_strategy": metrics_strategy,
        "metrics_benchmark": metrics_benchmark,
        "metrics_strategy_cost_stress": metrics_strategy_stress,
        "metrics_benchmark_cost_stress": metrics_benchmark_stress,
        "message_de": _evaluation_message_de(
            root,
            metrics_strategy=metrics_strategy,
            metrics_benchmark=metrics_benchmark,
            metrics_strategy_stress=metrics_strategy_stress,
            metrics_benchmark_stress=metrics_benchmark_stress,
            pass_full=pass_full,
            extra_bps=extra_bps,
        ),
    }


def _update_trial_ledger(root: Path, evaluation: Dict[str, Any]) -> None:
    if not evaluation.get("pass_full_seal"):
        return
    path = Path(root) / LEDGER_REL
    if not path.is_file():
        return
    doc = json.loads(path.read_text(encoding="utf-8"))
    for trial in doc.get("trials") or []:
        if str(trial.get("variant_key") or "") == VARIANT:
            trial["status"] = "SEALED"
            trial["sealed_at_utc"] = evaluation.get("evaluated_at_utc")
            trial["evaluation_ref"] = str(EVIDENCE_REL).replace("\\", "/")
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> int:
    import argparse
    from datetime import datetime, timezone

    from aa_safe_io import atomic_write_json

    parser = argparse.ArgumentParser(description="Evaluate DAILY_ALPHA_H1 vs mom_1")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--run-dir", type=Path, default=None)
    parser.add_argument("--seal-on-pass", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    root = Path(args.root)
    run = Path(args.run_dir) if args.run_dir else _latest_run(root)
    if run is None or not run.is_dir():
        out = {"ok": False, "reason": "no_completed_run"}
        print(json.dumps(out, indent=2))
        return 2
    evaluation = evaluate_run(root, run)
    evaluation["evaluated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    atomic_write_json(root / EVIDENCE_REL, evaluation)
    if args.seal_on_pass and evaluation.get("pass_full_seal"):
        _update_trial_ledger(root, evaluation)
    if args.json:
        print(json.dumps(evaluation, indent=2, ensure_ascii=False, default=str))
    else:
        print(evaluation.get("message_de", ""))
    return 0 if evaluation.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
