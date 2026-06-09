#!/usr/bin/env python3
"""Backfill latest_validated_run.json for an existing output directory (read-only audit)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from aa_config import BacktestConfig
from aa_integrity import validate_backtest_calendar_integrity, write_integrity_reports, IntegrityResult
from aa_run_provenance import make_run_id, publish_validated_run, run_directory, write_run_manifest
from aa_variant_id import resolve_canonical_variant_id


def _load_rebalance_dates(features_path: Path, cfg: BacktestConfig) -> list[pd.Timestamp]:
    if not features_path.is_file():
        return []
    features = pd.read_parquet(features_path, columns=["date"])
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    return [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]


def _cfg_from_snapshot(out_dir: Path) -> BacktestConfig:
    snap = out_dir / "run_config_snapshot.txt"
    cfg = BacktestConfig(out_dir=str(out_dir))
    if not snap.is_file():
        return cfg
    data: dict[str, str] = {}
    for line in snap.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        data[key.strip()] = val.strip()
    cfg.risk_off_selection_mode = str(data.get("risk_off_selection_mode", cfg.risk_off_selection_mode))
    cfg.risk_off_gate_mode = str(data.get("risk_off_gate_mode", cfg.risk_off_gate_mode))
    cfg.risk_off_momentum_weight = float(data.get("risk_off_momentum_weight", cfg.risk_off_momentum_weight))
    cfg.risk_off_momentum_rescue_quantile = float(
        data.get("risk_off_momentum_rescue_quantile", cfg.risk_off_momentum_rescue_quantile)
    )
    cfg.risk_off_force_exit_enabled = str(data.get("risk_off_force_exit_enabled", "False")).lower() in {
        "1",
        "true",
        "yes",
    }
    cfg.naive_detailed_reporting = str(data.get("naive_detailed_reporting", "False")).lower() in {"1", "true", "yes"}
    cfg.naive_detailed_variants = str(data.get("naive_detailed_variants", cfg.naive_detailed_variants))
    return cfg


def backfill(out_dir: Path, *, dry_run: bool = False) -> int:
    out_dir = Path(out_dir).resolve()
    if not (out_dir / "strategy_daily_returns.csv").is_file():
        print(f"[ERROR] Missing strategy_daily_returns.csv in {out_dir}")
        return 1

    cfg = _cfg_from_snapshot(out_dir)
    strat = pd.read_csv(out_dir / "strategy_daily_returns.csv", index_col=0)
    col = "strategy_return" if "strategy_return" in strat.columns else strat.columns[0]
    strategy_returns = pd.to_numeric(strat[col], errors="coerce").dropna()
    strategy_returns.index = pd.to_datetime(strategy_returns.index)

    bench_path = out_dir / "benchmark_daily_returns.csv"
    benchmark_returns = None
    if bench_path.is_file():
        bench = pd.read_csv(bench_path, index_col=0)
        bcol = bench.columns[0]
        benchmark_returns = pd.to_numeric(bench[bcol], errors="coerce")
        benchmark_returns.index = pd.to_datetime(benchmark_returns.index)

    rebalance_dates = _load_rebalance_dates(out_dir / "features.parquet", cfg)
    simulated: list[pd.Timestamp] = []
    dec_path = out_dir / "backtest_decisions.csv"
    if dec_path.is_file():
        dec = pd.read_csv(dec_path, usecols=lambda c: c in {"rebalance_date"})
        if "rebalance_date" in dec.columns:
            simulated = sorted({pd.Timestamp(d) for d in dec["rebalance_date"].dropna().unique()})

    run_id = make_run_id(cfg, ROOT)
    integrity = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates or simulated,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        simulated_rebalance_dates=simulated or None,
        run_id=run_id,
    )
    print(f"Integrity: {integrity.status} ({len(integrity.errors)} errors, {len(integrity.warnings)} warnings)")
    for err in integrity.errors:
        print(f"  - {err}")

    if dry_run:
        return 0 if integrity.passed else 2

    run_dir = run_directory(ROOT, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    for name in (
        "strategy_daily_returns.csv",
        "backtest_decisions.csv",
        "backtest_weights.csv",
        "constraint_binding_history.csv",
        "benchmark_daily_returns.csv",
        "backtest_report.txt",
        "run_config_snapshot.txt",
        "latest_target_portfolio.csv",
    ):
        src = out_dir / name
        if src.is_file():
            shutil.copy2(src, run_dir / name)

    write_integrity_reports(run_dir, integrity)
    write_run_manifest(run_dir, run_id=run_id, cfg=cfg, output_files=list(run_dir.glob("*")), integrity=integrity, root=ROOT)
    published = publish_validated_run(
        out_dir,
        run_dir,
        run_id,
        integrity=integrity,
        variant_id=resolve_canonical_variant_id(cfg),
    )
    print(f"Published: {published} -> {out_dir / 'latest_validated_run.json'}")
    return 0 if integrity.passed and published else 2


def main() -> int:
    p = argparse.ArgumentParser(description="Backfill validated-run pointer for existing model output")
    p.add_argument("--out-dir", type=Path, default=ROOT / "model_output_sp500_pit_t212")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return backfill(args.out_dir, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
