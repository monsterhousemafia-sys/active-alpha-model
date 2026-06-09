from __future__ import annotations

import argparse
import os
import sys
import multiprocessing as mp
from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from aa_backtest import (
    run_latest_signal,
    run_path_only_research,
    run_research_pipeline,
    verify_naive_detailed_artifacts,
    write_backtest_core_outputs,
)
from aa_config import (
    BacktestConfig,
    apply_capital_curve_policy_to_config,
    enforce_reproducibility_inputs,
    parse_args,
    write_run_config_snapshot,
)
from aa_dashboard_qt import create_dashboard, should_use_gui
from aa_ui_pump import pump_ui
from aa_data_quality_gate import run_data_quality_gate, write_data_quality_gate
from aa_integrity import write_integrity_reports
from aa_execution import PhaseTimings, write_run_manifest
from aa_run_provenance import make_run_id, publish_validated_run, run_directory, write_run_manifest as write_provenance_manifest
from aa_model_status import write_model_status
from aa_variant_id import resolve_canonical_variant_id
from aa_features import (
    _feature_build_fingerprint,
    _try_load_prediction_cache,
    build_or_load_features,
    collect_cache_status_lines,
    resolve_feature_cache_dir,
    resolve_price_cache_dir,
    resolve_shared_cache_root,
    using_shared_cache_dir,
)
from aa_parallel import ProcessPoolSession, _configure_blas_threading, resolve_parallel_workers
from aa_portfolio import (
    apply_dynamic_cluster_overlay,
    data_quality_report,
    target_portfolio_explained,
    write_unknown_mapping_reports,
)
from aa_reporting import run_backtest_reporting
from aa_universe import load_tickers


@dataclass
class RunResult:
    metrics: Dict[str, float] = field(default_factory=dict)
    bench_metrics: Dict[str, float] = field(default_factory=dict)
    signal_date: str = "n/a"
    output_files: List[Path] = field(default_factory=list)
    out_dir: Path = Path("model_output")
    success: bool = True
    error: str = ""


def execute_run(
    args: argparse.Namespace,
    cfg: BacktestConfig,
    dashboard,
    *,
    out_dir: Path,
    run_started: float,
) -> RunResult:
    metrics: Dict[str, float] = {}
    bench_metrics: Dict[str, float] = {}
    signal_date = "n/a"
    output_files: List[Path] = []
    phase_timings = PhaseTimings()
    phase_timings.meta["mode"] = args.mode
    result = RunResult(out_dir=out_dir)

    try:
        phase_timings.start("tickers_load")
        tickers = load_tickers(args, dashboard)
        phase_timings.stop("tickers_load")
        cfg.ticker_source_detail = getattr(args, "_ticker_source_detail", cfg.ticker_source_detail)
        cfg.membership_source_detail = getattr(args, "_membership_source_detail", cfg.membership_source_detail)

        with ProcessPoolSession(cfg) as pool_session:
            features, bench_close, returns, features_from_cache = build_or_load_features(
                cfg,
                tickers,
                out_dir,
                pool_session=pool_session,
                dashboard=dashboard,
                phase_timings=phase_timings,
            )
            phase_timings.meta["features_from_cache"] = bool(features_from_cache)

            phase_timings.start("cluster_overlay")
            cluster_mode = str(getattr(cfg, "cluster_mode", "static") or "static").lower().strip()
            constraint_mode = str(getattr(cfg, "cluster_constraint_mode", "static_only") or "static_only").lower().strip()
            if cluster_mode == "static" or (cluster_mode == "dynamic_diagnostic" and constraint_mode == "static_only"):
                dynamic_cluster_diagnostics = pd.DataFrame()
                if dashboard is not None:
                    dashboard.ok("Cluster-Overlay übersprungen (kein aktiver Constraint-Modus)")
            else:
                features, dynamic_cluster_diagnostics = apply_dynamic_cluster_overlay(features, returns, cfg, dashboard)
            phase_timings.stop("cluster_overlay")

            persist_features = args.mode in {"backtest", "both"}
            skip_feature_parquet = bool(getattr(cfg, "skip_feature_parquet_write", False)) and features_from_cache
            if persist_features and not skip_feature_parquet:
                phase_timings.start("feature_file_write")
                dashboard.start_phase("Feature-Datei schreiben", total=1, step="features.parquet speichern")
                feature_path = out_dir / "features.parquet"
                features.to_parquet(feature_path, index=False)
                output_files.append(feature_path)
                data_quality_path = out_dir / "data_quality_report.csv"
                data_quality_report(features).to_csv(data_quality_path, index=False)
                output_files.append(data_quality_path)
                if dynamic_cluster_diagnostics is not None and not dynamic_cluster_diagnostics.empty:
                    dyn_cluster_path = out_dir / "dynamic_cluster_diagnostics.csv"
                    dynamic_cluster_diagnostics.to_csv(dyn_cluster_path, index=False)
                    output_files.append(dyn_cluster_path)
                dashboard.advance_phase(1, step="features.parquet gespeichert", last_file=str(feature_path))
                dashboard.ok(f"Feature table written: {feature_path} ({len(features):,} rows)")
                dashboard.finish_phase()
                phase_timings.stop("feature_file_write")
            elif persist_features and skip_feature_parquet:
                if dashboard is not None:
                    dashboard.ok(
                        f"Feature-Parquet übersprungen (Cache-Hit, {len(features):,} Zeilen unverändert im Shared-Cache)"
                    )
            elif dashboard is not None:
                dashboard.ok(f"Signal-Modus: Feature-Parquet übersprungen ({len(features):,} Zeilen im Speicher)")

            if args.mode in ["backtest", "both"]:
                project_root = Path(__file__).resolve().parent
                run_id = make_run_id(cfg, project_root)
                run_dir = run_directory(project_root, run_id)
                run_dir.mkdir(parents=True, exist_ok=True)

                backtest_scope = str(getattr(args, "backtest_scope", "full") or "full").strip().lower()
                if backtest_scope == "path-only":
                    n_tk = int(features["ticker"].nunique())
                    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
                    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
                    rebalance_dates = [
                        d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0
                    ]
                    pred_root = Path(str(getattr(args, "prediction_cache_dir", "") or "").strip() or out_dir)
                    cached, reject, missing = _try_load_prediction_cache(pred_root, cfg, n_tk, rebalance_dates)
                    if cached is None or missing:
                        raise RuntimeError(
                            f"path-only backtest requires complete prediction cache in {pred_root.resolve()}: "
                            f"{reject!r} missing={len(missing)}"
                        )
                    if dashboard is not None:
                        dashboard.ok(f"Path-only: {len(cached):,} cached predictions from {pred_root.name}")
                    research = run_path_only_research(
                        features,
                        returns,
                        cfg,
                        cached,
                        dashboard,
                        phase_timings=phase_timings,
                        run_id=run_id,
                    )
                else:
                    research = run_research_pipeline(
                        features,
                        returns,
                        cfg,
                        dashboard,
                        include_naive_baselines=bool(getattr(cfg, "naive_momentum_baseline", True)),
                        phase_timings=phase_timings,
                        run_id=run_id,
                    )
                metrics = research.metrics
                bench_metrics = research.bench_metrics
                integrity = research.integrity

                seal_paths = verify_naive_detailed_artifacts(cfg, out_dir)
                if seal_paths:
                    phase_timings.meta["h1_seal_benchmark_paths"] = [p.name for p in seal_paths]
                    phase_timings.meta["reporting_benchmark_note"] = (
                        "benchmark_daily_returns.csv = SPY reporting; seal uses naive_mom_1_daily_returns.csv"
                    )
                    if dashboard is not None:
                        dashboard.ok(
                            "H1-Seal-Benchmark: "
                            + ", ".join(p.name for p in seal_paths)
                            + " (nicht benchmark_daily_returns.csv/SPY)"
                        )

                if not bool(getattr(cfg, "minimal_backtest_reporting", False)):
                    dq_result = run_data_quality_gate(features)
                    write_data_quality_gate(run_dir, dq_result, features)

                if integrity is not None:
                    write_integrity_reports(run_dir, integrity)

                config_snapshot_path = run_dir / "run_config_snapshot.txt"
                write_run_config_snapshot(config_snapshot_path, cfg)
                output_files.append(config_snapshot_path)

                phase_timings.start("reporting")
                dashboard.start_phase("Backtest-Dateien schreiben", total=1, step="Reports und CSV-Dateien speichern")
                _, _, _, report_path = write_backtest_core_outputs(run_dir, research, output_files=output_files)

                if integrity is not None and integrity.passed:
                    run_backtest_reporting(
                        run_dir,
                        cfg,
                        args=args,
                        dashboard=dashboard,
                        output_files=output_files,
                        features=features,
                        returns=returns,
                        strategy_returns=research.strategy_returns,
                        benchmark_returns=research.benchmark_returns,
                        decisions=research.decisions,
                        weight_history=research.weight_history,
                        naive_returns=research.naive_returns,
                        metrics=research.metrics,
                        bench_metrics=research.bench_metrics,
                        no_plot=bool(args.no_plot),
                    )
                    publish_validated_run(
                        out_dir,
                        run_dir,
                        run_id,
                        integrity=integrity,
                        variant_id=resolve_canonical_variant_id(cfg),
                    )
                    dashboard.advance_phase(1, step="Backtest-Dateien gespeichert", last_file=str(report_path))
                    dashboard.ok(f"Backtest files written: {run_dir.resolve()} (published to {out_dir.resolve()})")
                else:
                    err_msg = "; ".join(integrity.errors if integrity else ["integrity check missing"])
                    if dashboard is not None:
                        dashboard.error(f"Backtest integrity INVALID — kein gültiger Report: {err_msg}")
                    if integrity is not None:
                        publish_validated_run(
                            out_dir,
                            run_dir,
                            run_id,
                            integrity=integrity,
                            variant_id=resolve_canonical_variant_id(cfg),
                        )
                    result.success = False
                    result.error = err_msg
                    raise RuntimeError(f"Backtest integrity check failed: {err_msg}")

                manifest_path = write_provenance_manifest(
                    run_dir,
                    run_id=run_id,
                    cfg=cfg,
                    output_files=output_files,
                    integrity=integrity,
                    root=project_root,
                )
                output_files.append(manifest_path)
                dashboard.finish_phase()
                phase_timings.stop("reporting")

            if args.mode in ["signal", "both"]:
                phase_timings.start("signal")
                latest = run_latest_signal(features, cfg, dashboard)
                latest_cols = [
                    "signal_date", "ticker", "target_weight", "mu_hat", "alpha_lcb", "rank_score", "selection_score",
                    "sector", "issuer", "correlation_cluster", "mom_252_21", "mom_126_21", "mom_63_21", "rev_5", "trend_50", "trend_200",
                    "vol_20", "idio_vol_63", "beta_252", "rel_strength_63", "sector_rel_strength_63", "adv_20", "universe_adv", "in_universe", "universe_rank", "universe_reason", "membership_allowed", "membership_valid_from", "membership_source", "membership_reason", "eligible", "risk_on", "target_exposure",
                    "desired_exposure", "regime_target_exposure", "exposure_controller_score", "signal_breadth_positive", "avg_alpha_lcb", "n_positive_candidates_for_exposure", "exposure_before_constraints", "exposure_after_position_cap", "exposure_after_issuer_cap", "exposure_after_sector_cap", "exposure_after_cluster_cap", "exposure_after_beta_cap", "exposure_after_cash_filler", "effective_max_portfolio_beta", "beta_cap_mode_effective", "cash_filler_enabled", "cash_filler_added_weight", "cash_filler_n_names", "low_beta_filler_enabled", "low_beta_filler_added_weight", "low_beta_filler_n_names", "correlation_cluster_static", "correlation_cluster_dynamic", "correlation_cluster_source", "dynamic_cluster_stable",
                    "n_candidates", "n_eligible_candidates", "n_selected_candidates", "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol",
                    "portfolio_exposure", "portfolio_beta", "max_position_weight", "max_issuer_weight", "max_sector_weight", "max_correlation_cluster_weight", "n_positions", "constraint_violations", "gross_exposure_binding", "max_position_binding", "max_issuer_binding", "max_sector_binding", "max_cluster_binding", "max_beta_binding", "unknown_sector_weight", "unknown_cluster_weight", "unknown_issuer_weight", "n_unknown_sector_positions", "n_unknown_cluster_positions", "n_unknown_issuer_positions",
                ]
                latest_out = latest[[c for c in latest_cols if c in latest.columns]].copy()
                signal_date = str(latest_out["signal_date"].iloc[0]) if not latest_out.empty and "signal_date" in latest_out else "n/a"
                trade_list = latest_out[latest_out["target_weight"] > 0].copy() if "target_weight" in latest_out else pd.DataFrame()

                dashboard.start_phase("Signal-Dateien schreiben", total=1, step="aktuelle Signale speichern")
                signals_path = out_dir / "latest_signals.csv"
                portfolio_path = out_dir / "latest_target_portfolio.csv"
                latest_out.to_csv(signals_path, index=False)
                trade_list.to_csv(portfolio_path, index=False)
                explained_path = out_dir / "target_portfolio_explained.csv"
                target_portfolio_explained(latest_out).to_csv(explained_path, index=False)
                unknown_paths = write_unknown_mapping_reports(out_dir, latest_out, weight_col="target_weight")
                output_files.extend([signals_path, portfolio_path, explained_path] + unknown_paths)
                dashboard.advance_phase(1, step="Signal-Dateien gespeichert", last_file=str(portfolio_path))
                dashboard.ok(f"Signal files written: {out_dir.resolve()}")
                dashboard.finish_phase()
                phase_timings.stop("signal")

        if cfg.run_manifest:
            manifest_path = out_dir / "run_manifest.json"
            write_run_manifest(manifest_path, cfg, output_files, args)
            output_files.append(manifest_path)
        if dashboard is not None:
            dashboard.ok("Modelllauf abgeschlossen")
    except Exception as exc:
        result.success = False
        if dashboard is not None:
            dashboard.error(str(exc))
        raise
    finally:
        phase_timings.set("total_run", monotonic() - run_started)
        if dashboard is not None:
            try:
                timings_path = out_dir / "phase_timings.json"
                phase_timings.write(timings_path)
                if timings_path not in output_files:
                    output_files.append(timings_path)
                sections = phase_timings.as_dict().get("sections_seconds", {})
                dashboard.ok(
                    "Laufzeiten: "
                    f"Download {sections.get('download', 0.0):.1f}s | "
                    f"Features {sections.get('feature_build', 0.0):.1f}s | "
                    f"Cluster {sections.get('cluster_overlay', 0.0):.1f}s | "
                    f"ML {sections.get('walkforward_phase_a_ml', 0.0):.1f}s | "
                    f"Pfad {sections.get('walkforward_phase_b_path', 0.0):.1f}s | "
                    f"Naive {sections.get('walkforward_phase_c_naive', 0.0):.1f}s | "
                    f"Reporting {sections.get('reporting', 0.0):.1f}s"
                )
            except Exception:
                pass
            dashboard.stop()

    result.metrics = metrics
    result.bench_metrics = bench_metrics
    result.signal_date = signal_date
    result.output_files = output_files
    return result


def print_run_summary(result: RunResult) -> None:
    print("\nActive Alpha Model - Zusammenfassung")
    print("-" * 38)
    print(f"Output: {result.out_dir.resolve()}")
    if result.metrics:
        print("Backtest metrics:")
        for key in ["cagr", "sharpe_0rf", "max_drawdown", "information_ratio", "tracking_error", "total_return"]:
            if key in result.metrics:
                val = result.metrics[key]
                print(f"  {key}: {val:.4f}" if isinstance(val, (float, np.floating)) else f"  {key}: {val}")
    if result.signal_date != "n/a":
        print(f"Latest signal date: {result.signal_date}")
    if result.output_files:
        print("Geschriebene Dateien:")
        for file_path in result.output_files:
            print(f"  {file_path}")


def run_self_tests() -> None:
    """Run the pytest suite without downloading market data."""
    tests_dir = Path(__file__).resolve().parent / "tests"
    if tests_dir.is_dir():
        try:
            import pytest
        except ImportError as exc:
            raise SystemExit("pytest is required for --self-test. Run: pip install pytest") from exc
        code = pytest.main(["-q", str(tests_dir)])
        if code != 0:
            raise SystemExit(code)
        print(
            "Self-tests passed: allocator constraints, gross exposure cap, membership gating, "
            "Trading-212 fee model, capital policy, buy/hold spread and exposure recovery controls are valid."
        )
        return

    raise SystemExit("tests/ directory not found; cannot run self-tests.")


def print_dry_run_preview(cfg: BacktestConfig, args: argparse.Namespace, *, n_tickers: int) -> None:
    """Print resolved run plan without downloading market data or running the backtest."""
    out_dir = Path(cfg.out_dir)
    cache_root = resolve_shared_cache_root(cfg)
    feat_dir = resolve_feature_cache_dir(cfg, n_tickers)
    price_dir = resolve_price_cache_dir(cfg)
    feat_fp = _feature_build_fingerprint(cfg, n_tickers)
    workers = resolve_parallel_workers(cfg, backend="process")
    phases: List[str] = ["tickers", "features (download/build or cache)", "cluster overlay", "feature write"]
    if args.mode in {"backtest", "both"}:
        phases.extend(["walk-forward backtest", "reporting outputs"])
    if args.mode in {"signal", "both"}:
        phases.append("latest signal export")
    lines = [
        "Active Alpha Model — Dry Run",
        "==============================",
        f"mode: {args.mode}",
        f"out_dir: {out_dir.resolve()}",
        f"shared_cache: {cache_root.resolve() if using_shared_cache_dir(cfg) else '(off — caches in out_dir)'}",
        f"feature_cache_dir: {feat_dir.resolve()}",
        f"feature_fingerprint: {feat_fp}",
        f"price_cache_dir: {price_dir.resolve()}",
        f"tickers: {n_tickers} ({cfg.ticker_source}, membership={cfg.membership_mode})",
        f"start: {cfg.start} | benchmark: {cfg.benchmark} | universe: {cfg.universe_mode} top_n={cfg.universe_top_n}",
        f"parallel_workers: {workers} (profile={cfg.parallel_profile}, backend={cfg.parallel_backtest_backend})",
        "cache flags:",
        f"  reuse_feature_cache={cfg.reuse_feature_cache} force_rebuild_features={cfg.force_rebuild_features}",
        f"  reuse_prediction_cache={cfg.reuse_prediction_cache} skip_download_if_cached={cfg.skip_download_if_cached}",
        f"execution: policy={cfg.trading212_policy} fee_model={cfg.fee_model} "
        f"slippage_bps={cfg.slippage_bps} fx_bps={cfg.trading212_fx_bps}",
        f"capital: backtest={cfg.backtest_capital} research={cfg.research_backtest_capital}",
        "planned phases:",
    ]
    for step in phases:
        lines.append(f"  - {step}")
    lines.append("")
    lines.append("No download, ML training, or file writes will occur in dry-run mode.")
    print("\n".join(lines))


def main() -> None:
    args = parse_args()
    cfg = BacktestConfig.from_args(args)
    cfg = apply_capital_curve_policy_to_config(cfg)
    enforce_reproducibility_inputs(cfg)

    if args.mode == "signal" and int(getattr(cfg, "signal_lookback_years", 0)) > 0:
        # Paper-trading signal mode does not need the full backtest history. The
        # model trains on cfg.train_years and needs additional warm-up for 252-day
        # features, beta, liquidity and universe filters. 9 years is the chosen
        # chosen operating standard for this package.
        signal_start = pd.Timestamp.today().normalize() - pd.DateOffset(years=int(cfg.signal_lookback_years))
        cfg.start = signal_start.strftime("%Y-%m-%d")

    if args.self_test:
        run_self_tests()
        return

    if args.dry_run:
        tickers = load_tickers(args, None)
        print_dry_run_preview(cfg, args, n_tickers=len(tickers))
        return

    if args.cache_status:
        try:
            tickers = load_tickers(args, None)
            n_tickers = len(tickers)
        except Exception:
            n_tickers = 0
        print("\n".join(collect_cache_status_lines(cfg, cfg.out_dir, n_tickers=n_tickers)))
        return

    out_dir = Path(cfg.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_run_config_snapshot(out_dir / "run_config_snapshot.txt", cfg, workers=resolve_parallel_workers(cfg))

    # Fixed phase budget for a quiet console dashboard.
    # Core: ticker universe, download, feature engineering, ranking, universe filter.
    persist_features = args.mode in {"backtest", "both"}
    total_phases = 5 + (1 if persist_features else 0)
    if args.mode in ["backtest", "both"]:
        total_phases += 2  # backtest, output write
    if args.mode in ["signal", "both"]:
        total_phases += 2  # signal calculation, output write

    use_gui = should_use_gui(args)
    dashboard = create_dashboard(
        enabled=not args.plain_progress,
        title="Marktanalyse" if os.environ.get("AA_LAUNCHER_READY", "").strip() == "1" else None,
        prefer_gui=use_gui,
        plain=args.plain_progress,
    )
    run_started = monotonic()
    dashboard.start(total_phases=total_phases, out_dir=out_dir)
    dashboard.ok("Marktanalyse gestartet — initialisiere Pipeline …")
    pump_ui(force=True)
    try:
        result = execute_run(args, cfg, dashboard, out_dir=out_dir, run_started=run_started)
    except KeyboardInterrupt:
        dashboard.error("Lauf abgebrochen")
        if hasattr(dashboard, "finalize_app"):
            dashboard.finalize_app(success=False, result=RunResult(out_dir=out_dir, success=False))
        raise SystemExit(130)
    except Exception:
        if hasattr(dashboard, "finalize_app"):
            dashboard.finalize_app(success=False, result=RunResult(out_dir=out_dir, success=False))
        raise
    else:
        if hasattr(dashboard, "finalize_app"):
            dashboard.finalize_app(success=result.success, result=result)
        print_run_summary(result)


if __name__ == "__main__":
    mp.freeze_support()
    _configure_blas_threading(1)
    try:
        main()
    except KeyboardInterrupt:
        print("Interrupted.")
        sys.exit(130)
