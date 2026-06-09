from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import numpy as np

from aa_constants import (
    CORRELATION_CLUSTER_MAP,
    DEFAULT_TICKERS,
    FEATURE_COLUMNS,
    ISSUER_MAP,
    SECTOR_MAP,
    VALIDATION_TOL,
    deduplicate_dataframe_columns,
    ticker_to_correlation_cluster,
    ticker_to_issuer,
    ticker_to_sector,
)
from aa_dashboard import RunDashboard


@dataclass
class BacktestConfig:
    start: str = "2012-01-01"
    signal_lookback_years: int = 9  # Used only in --mode signal; backtests keep --start.
    benchmark: str = "SPY"
    horizon: int = 10
    rebalance_every: int = 5
    top_k: int = 15
    max_position: float = 0.12
    good_regime_exposure: float = 1.00
    bad_regime_exposure: float = 0.60
    risk_on_exposure_floor: float = 0.95
    min_edge: float = 0.0010
    lcb_z: float = 0.10
    lcb_scale: float = 0.10
    align_target_cost_with_execution: bool = True
    cost_bps: float = 10.0  # Fallback when align_target_cost_with_execution=False.
    fee_model: str = "trading212_us"  # Only supported broker cost model in this package.
    backtest_capital: float = 100_000.0
    slippage_bps: float = 0.0
    market_impact_bps: float = 0.0
    trading212_policy: str = "balanced"  # conservative, balanced, active, threshold.
    buy_hold_spread: bool = True
    buy_rank_multiple: float = 1.0
    hold_rank_multiple: float = 2.5
    sell_rank_multiple: float = 3.0
    tail_prune_enabled: bool = False
    residual_weight_floor: float = 0.005
    residual_sell_min_value: float = 0.01
    order_value_rounding: float = 1.0
    broker_min_remaining_position_value: float = 1.0
    max_n_positions_soft: int = 35
    max_n_positions_hard: int = 45
    tail_prune_reallocate: bool = True
    max_tail_reallocation_per_name: float = 0.01
    tail_reallocation_step: float = 0.0025
    tail_reallocation_rounds: int = 10
    tail_prune_min_exposure_buffer: float = 0.02
    trading212_sec_fee_rate: float = 0.0000278  # Trading 212 US sell-side SEC Transaction Fee: 0.00278% of sale value.
    trading212_finra_taf_per_share: float = 0.000195  # Trading 212 US sell-side FINRA fee per share sold.
    trading212_fx_bps: float = 15.0  # Trading 212 Invest/ISA FX fee: 0.15% when instrument currency differs from account/base currency; set 0 for no conversion.
    min_adv: float = 10_000_000.0
    max_ann_vol: float = 1.25
    max_sector: float = 0.55
    max_issuer: float = 0.15
    max_correlation_cluster: float = 0.40
    max_portfolio_beta: float = 1.25  # Base cap; dynamic mode can lift/reduce it per rebalance.
    beta_cap_mode: str = "dynamic"  # fixed or dynamic
    dynamic_beta_risk_off: float = 1.10
    dynamic_beta_normal: float = 1.25
    dynamic_beta_risk_on: float = 1.40
    dynamic_beta_strong: float = 1.50
    static_cluster_cap: float = 0.40
    dynamic_cluster_cap: float = 0.50
    cluster_constraint_mode: str = "static_only"  # static_only, dynamic_only, both_restrictive
    max_gross_exposure: float = 1.00  # Hard long gross exposure cap. 1.0 = unlevered long-only.
    universe_mode: str = "diy_pit_liquidity"  # static or diy_pit_liquidity.
    universe_top_n: int = 100          # Dynamic top-N universe by trailing dollar volume.
    universe_adv_lookback: int = 63    # Lookback for DIY point-in-time liquidity ranking.
    universe_min_adv: float = 10_000_000.0
    universe_min_price: float = 5.0
    universe_min_history_days: int = 252
    ticker_source: str = "sp500_pit"       # sp500_pit for historical S&P 500 PIT backtests; live signals use sp500_auto/wikipedia/slickcharts/cache.
    ticker_cache_dir: str = "universe_snapshots"
    ticker_snapshot_date: str = ""    # YYYY-MM-DD for cached_sp500; empty = latest snapshot.
    save_universe_snapshot: bool = True
    ticker_cache_max_age_days: int = 7
    allow_ticker_fallback: bool = True
    ticker_source_detail: str = ""
    membership_file: str = "ticker_membership.csv"
    membership_mode: str = "auto"  # off, auto or strict. Applies mainly to backtests.
    membership_filter_signal: bool = False
    update_membership_from_snapshots: bool = True
    asset_master_file: str = "asset_master.csv"
    update_asset_master: bool = True
    membership_source_detail: str = ""
    runtime_mode: str = ""
    no_trade_band: float = 0.01      # keep previous weight if absolute target change is below this weight threshold.
    weight_smoothing: float = 0.50   # 1.0 = immediate target; 0.5 = move halfway to target.
    max_turnover: Optional[float] = 0.35  # 0 disables; otherwise max turnover per rebalance.
    execution_policy_mode: str = "manual"  # manual or capital_curve.
    capital_profile: str = ""
    policy_rebalance_every: int = 0
    policy_top_k: int = 0
    policy_max_position: float = 0.0
    policy_max_issuer: float = 0.0
    policy_risk_on_exposure_floor: float = 0.0
    policy_max_turnover: float = 0.0
    policy_no_trade_band: float = 0.0
    policy_min_trade_value: float = 0.0
    policy_cost_budget: float = 0.0
    policy_continuous_rebalance_every: float = 0.0
    policy_continuous_top_k: float = 0.0
    policy_continuous_max_position: float = 0.0
    policy_reason: str = ""
    train_years: int = 7
    ml_retrain_every: int = 1  # Retrain ML every N rebalances; intermediate dates reuse prior model output.
    min_train_rows: int = 2500
    # Research validation / diagnostics
    alpha_model_mode: str = "ensemble"  # ensemble, ml_only, rank_only, elastic_only, gbm_only
    extra_benchmarks: str = "QQQ,RSP,MTUM,QUAL,VUG,VLUE,USMV,SMH"
    naive_momentum_baseline: bool = True
    naive_momentum_variants: str = "mom_63_top12,mom_126_top12,mom_252_21_top12,mom_blend_top12,sector_neutral_momentum,cluster_neutral_momentum"
    custom_benchmarks: bool = True
    statistical_diagnostics: bool = True
    minimal_backtest_reporting: bool = False  # Skip factor/benchmark comparison/stats; integrity-safe CSVs only.
    returns_fast_path: bool = False  # Phase B: skip decision/weight diagnostic rows; returns identical (post-M1 validated).
    path_sim_checkpoint: bool = False  # Phase B: resume path simulation from path_sim_checkpoint.pkl after hang.
    bootstrap_iterations: int = 250
    random_seed: int = 42
    n_jobs: str = "auto"  # 1 = serial, auto/all = min(physical cores, RAM budget).
    parallel_backtest_backend: str = "process"  # thread or process. process uses multiprocessing across CPU cores.
    cpu_cores: int = 16  # Physical cores for auto sizing (Ryzen 9 3950X: 16C/32T → use 16, not 32 threads).
    system_ram_gb: int = 64  # Host RAM budget for worker sizing (Windows x64, 64 GB default).
    parallel_profile: str = "high"  # auto, normal, high — high enables float32 tables and larger pool chunks.
    reuse_feature_cache: bool = False  # Skip download/feature build when a valid cache exists in out_dir.
    force_rebuild_features: bool = False  # Ignore reusable feature cache even when --reuse-feature-cache is set.
    write_feature_cache: bool = True  # Persist feature/return tables for fast reruns (robustness lab).
    skip_feature_parquet_write: bool = False  # Skip features.parquet when features were loaded from cache.
    no_naive_overlap: bool = False  # Run naive baselines after Phase B instead of overlapping with path simulation.
    reuse_prediction_cache: bool = False  # Load cached walk-forward ML predictions when fingerprint matches.
    force_rebuild_predictions: bool = False  # Ignore prediction cache even when --reuse-prediction-cache is set.
    write_prediction_cache: bool = True  # Persist Phase-A prediction cache for fast policy/slippage reruns.
    skip_download_if_cached: bool = False  # Reuse price panel cache in out-dir when fingerprint/TTL match.
    write_price_cache: bool = True  # Persist downloaded OHLCV panel under out-dir/price_cache.
    price_cache_ttl_hours: int = 24  # Max age of price cache before refresh (0 = no TTL expiry).
    risk_off_selection_mode: str = "legacy"  # legacy, mom_blend_replace, mom_blend_blend
    risk_off_momentum_variant: str = "mom_blend_top12"
    risk_off_momentum_weight: float = 0.70
    risk_off_gate_mode: str = "legacy"  # legacy, base_only, momentum_rescue
    risk_off_momentum_rescue_quantile: float = 0.70
    risk_off_force_exit_enabled: bool = False
    naive_detailed_reporting: bool = False
    naive_detailed_variants: str = "mom_blend_top12,mom_63_top12"
    naive_position_contributions: bool = False
    risk_regime_mode: str = "normal"  # strict, normal, loose
    # Stage 3 default model controls: gradual exposure, guarded cash filler, and
    # dynamic cluster guardrails that fall back to the static audit map when unstable.
    exposure_controller: str = "gradual_alpha"  # binary, gradual or gradual_alpha
    cash_filler_mode: str = "benchmark_completion"  # off, conservative, balanced, balanced_plus_low_beta, benchmark_completion
    cash_filler_max_position: float = 0.03
    cash_filler_min_score: float = 0.0
    benchmark_completion_ticker: str = "SPY"
    benchmark_completion_max_weight: float = 0.25
    low_beta_filler_max_position: float = 0.015
    low_beta_filler_beta_max: float = 0.90
    low_beta_filler_min_score: float = -0.05
    low_beta_filler_max_vol_63: float = 0.75
    exposure_recovery_policy: str = "cause_aware"
    cluster_mode: str = "static"  # static, dynamic_diagnostic, dynamic_guardrail, dynamic_enforced
    dynamic_cluster_window_short: int = 126
    dynamic_cluster_window_long: int = 252
    dynamic_cluster_corr_threshold: float = 0.65
    dynamic_cluster_min_overlap: float = 0.50
    reproducibility_mode: str = "normal"  # normal or strict
    research_backtest_capital: float = 100_000.0  # Used for capital-curve policy selection in research/backtests.
    run_manifest: bool = True
    out_dir: str = "model_output"
    shared_cache_dir: str = ""  # Optional shared root for feature/price caches (robustness lab).

    def __post_init__(self) -> None:
        if str(self.fee_model).strip().lower() != "trading212_us":
            raise ValueError("Only trading212_us fee model is supported in this package.")
        if float(self.backtest_capital) <= 0 or float(self.research_backtest_capital) <= 0:
            raise ValueError("backtest_capital and research_backtest_capital must be positive.")
        if int(self.max_n_positions_soft) > int(self.max_n_positions_hard):
            raise ValueError("max_n_positions_soft cannot exceed max_n_positions_hard.")
        if (
            str(getattr(self, "universe_mode", "static")).lower() == "diy_pit_liquidity"
            and int(self.top_k) > int(self.universe_top_n)
        ):
            raise ValueError(f"top_k ({self.top_k}) cannot exceed universe_top_n ({self.universe_top_n}).")
        from aa_risk_off import validate_risk_off_config

        validate_risk_off_config(self)

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "BacktestConfig":
        return cls(
            start=args.start,
            signal_lookback_years=args.signal_lookback_years,
            benchmark=args.benchmark.upper(),
            horizon=args.horizon,
            rebalance_every=args.rebalance_every,
            top_k=args.top_k,
            max_position=args.max_position,
            good_regime_exposure=args.good_regime_exposure,
            bad_regime_exposure=args.bad_regime_exposure,
            risk_on_exposure_floor=args.risk_on_exposure_floor,
            min_edge=args.min_edge,
            lcb_z=args.lcb_z,
            lcb_scale=args.lcb_scale,
            cost_bps=args.cost_bps,
            fee_model="trading212_us",
            backtest_capital=args.backtest_capital,
            slippage_bps=args.slippage_bps,
            market_impact_bps=args.market_impact_bps,
            trading212_policy=args.trading212_policy,
            buy_hold_spread=not args.no_buy_hold_spread,
            buy_rank_multiple=args.buy_rank_multiple,
            hold_rank_multiple=args.hold_rank_multiple,
            sell_rank_multiple=args.sell_rank_multiple,
            tail_prune_enabled=args.tail_prune_enabled,
            residual_weight_floor=args.residual_weight_floor,
            residual_sell_min_value=args.residual_sell_min_value,
            order_value_rounding=args.order_value_rounding,
            broker_min_remaining_position_value=args.broker_min_remaining_position_value,
            max_n_positions_soft=args.max_n_positions_soft,
            max_n_positions_hard=args.max_n_positions_hard,
            tail_prune_reallocate=not args.no_tail_prune_reallocate,
            max_tail_reallocation_per_name=args.max_tail_reallocation_per_name,
            tail_reallocation_step=args.tail_reallocation_step,
            tail_reallocation_rounds=args.tail_reallocation_rounds,
            tail_prune_min_exposure_buffer=args.tail_prune_min_exposure_buffer,
            trading212_sec_fee_rate=args.trading212_sec_fee_rate,
            trading212_finra_taf_per_share=args.trading212_finra_taf_per_share,
            trading212_fx_bps=args.trading212_fx_bps,
            min_adv=args.min_adv,
            max_ann_vol=args.max_ann_vol,
            max_sector=args.max_sector,
            max_issuer=args.max_issuer,
            max_correlation_cluster=args.max_correlation_cluster,
            max_portfolio_beta=args.max_portfolio_beta,
            beta_cap_mode=args.beta_cap_mode,
            dynamic_beta_risk_off=args.dynamic_beta_risk_off,
            dynamic_beta_normal=args.dynamic_beta_normal,
            dynamic_beta_risk_on=args.dynamic_beta_risk_on,
            dynamic_beta_strong=args.dynamic_beta_strong,
            static_cluster_cap=args.static_cluster_cap,
            dynamic_cluster_cap=args.dynamic_cluster_cap,
            cluster_constraint_mode=args.cluster_constraint_mode,
            max_gross_exposure=args.max_gross_exposure,
            universe_mode=args.universe_mode,
            universe_top_n=args.universe_top_n,
            universe_adv_lookback=args.universe_adv_lookback,
            universe_min_adv=args.universe_min_adv,
            universe_min_price=args.universe_min_price,
            universe_min_history_days=args.universe_min_history_days,
            ticker_source=args.ticker_source,
            ticker_cache_dir=args.ticker_cache_dir,
            ticker_cache_max_age_days=args.ticker_cache_max_age_days,
            ticker_snapshot_date=args.ticker_snapshot_date,
            save_universe_snapshot=not args.no_save_universe_snapshot,
            allow_ticker_fallback=not args.no_ticker_fallback,
            ticker_source_detail=getattr(args, "_ticker_source_detail", ""),
            membership_file=args.membership_file,
            membership_mode=args.membership_mode,
            membership_filter_signal=args.membership_filter_signal,
            update_membership_from_snapshots=not args.no_update_membership,
            asset_master_file=args.asset_master_file,
            update_asset_master=not args.no_update_asset_master,
            membership_source_detail=getattr(args, "_membership_source_detail", ""),
            runtime_mode=args.mode,
            no_trade_band=args.no_trade_band,
            weight_smoothing=args.weight_smoothing,
            max_turnover=args.max_turnover,
            execution_policy_mode=args.execution_policy_mode,
            capital_profile=args.capital_profile,
            policy_rebalance_every=args.policy_rebalance_every,
            policy_top_k=args.policy_top_k,
            policy_max_position=args.policy_max_position,
            policy_max_issuer=args.policy_max_issuer,
            policy_risk_on_exposure_floor=args.policy_risk_on_exposure_floor,
            policy_max_turnover=args.policy_max_turnover,
            policy_no_trade_band=args.policy_no_trade_band,
            policy_min_trade_value=args.policy_min_trade_value,
            policy_cost_budget=args.policy_cost_budget,
            policy_continuous_rebalance_every=args.policy_continuous_rebalance_every,
            policy_continuous_top_k=args.policy_continuous_top_k,
            policy_continuous_max_position=args.policy_continuous_max_position,
            policy_reason=args.policy_reason,
            train_years=args.train_years,
            ml_retrain_every=max(1, int(getattr(args, "ml_retrain_every", 1) or 1)),
            min_train_rows=args.min_train_rows,
            alpha_model_mode=args.alpha_model_mode,
            extra_benchmarks=args.extra_benchmarks,
            naive_momentum_baseline=not args.no_naive_momentum_baseline,
            naive_momentum_variants=args.naive_momentum_variants,
            custom_benchmarks=not args.no_custom_benchmarks,
            statistical_diagnostics=not args.no_statistical_diagnostics,
            minimal_backtest_reporting=bool(getattr(args, "minimal_backtest_reporting", False)),
            returns_fast_path=bool(getattr(args, "returns_fast_path", False)),
            path_sim_checkpoint=bool(getattr(args, "path_sim_checkpoint", False)),
            bootstrap_iterations=args.bootstrap_iterations,
            random_seed=args.random_seed,
            n_jobs=args.n_jobs,
            parallel_backtest_backend=args.parallel_backtest_backend,
            cpu_cores=args.cpu_cores,
            system_ram_gb=args.system_ram_gb,
            parallel_profile=args.parallel_profile,
            reuse_feature_cache=bool(getattr(args, "reuse_feature_cache", False)),
            force_rebuild_features=bool(getattr(args, "force_rebuild_features", False)),
            write_feature_cache=not bool(getattr(args, "no_feature_cache", False)),
            skip_feature_parquet_write=bool(getattr(args, "skip_feature_parquet_write", False)),
            no_naive_overlap=bool(getattr(args, "no_naive_overlap", False)),
            reuse_prediction_cache=bool(getattr(args, "reuse_prediction_cache", False)),
            force_rebuild_predictions=bool(getattr(args, "force_rebuild_predictions", False)),
            write_prediction_cache=not bool(getattr(args, "no_prediction_cache", False)),
            skip_download_if_cached=bool(getattr(args, "skip_download_if_cached", False)),
            write_price_cache=True,
            price_cache_ttl_hours=int(getattr(args, "price_cache_ttl_hours", 24) or 24),
            risk_off_selection_mode=str(getattr(args, "risk_off_selection_mode", "legacy") or "legacy"),
            risk_off_momentum_variant=str(getattr(args, "risk_off_momentum_variant", "mom_blend_top12") or "mom_blend_top12"),
            risk_off_momentum_weight=float(getattr(args, "risk_off_momentum_weight", 0.70) or 0.70),
            risk_off_gate_mode=str(getattr(args, "risk_off_gate_mode", "legacy") or "legacy"),
            risk_off_momentum_rescue_quantile=float(getattr(args, "risk_off_momentum_rescue_quantile", 0.70) or 0.70),
            risk_off_force_exit_enabled=bool(getattr(args, "risk_off_force_exit_enabled", False)),
            naive_detailed_reporting=bool(getattr(args, "naive_detailed_reporting", False)) and not bool(getattr(args, "no_naive_detailed_reporting", False)),
            naive_detailed_variants=str(getattr(args, "naive_detailed_variants", "mom_blend_top12,mom_63_top12") or "mom_blend_top12,mom_63_top12"),
            naive_position_contributions=bool(getattr(args, "naive_position_contributions", False)),
            risk_regime_mode=args.risk_regime_mode,
            exposure_controller=args.exposure_controller,
            cash_filler_mode=args.cash_filler_mode,
            cash_filler_max_position=args.cash_filler_max_position,
            cash_filler_min_score=args.cash_filler_min_score,
            benchmark_completion_ticker=args.benchmark_completion_ticker,
            benchmark_completion_max_weight=args.benchmark_completion_max_weight,
            low_beta_filler_max_position=args.low_beta_filler_max_position,
            low_beta_filler_beta_max=args.low_beta_filler_beta_max,
            low_beta_filler_min_score=args.low_beta_filler_min_score,
            low_beta_filler_max_vol_63=args.low_beta_filler_max_vol_63,
            exposure_recovery_policy=args.exposure_recovery_policy,
            cluster_mode=args.cluster_mode,
            dynamic_cluster_window_short=args.dynamic_cluster_window_short,
            dynamic_cluster_window_long=args.dynamic_cluster_window_long,
            dynamic_cluster_corr_threshold=args.dynamic_cluster_corr_threshold,
            dynamic_cluster_min_overlap=args.dynamic_cluster_min_overlap,
            reproducibility_mode=args.reproducibility_mode,
            research_backtest_capital=args.research_backtest_capital,
            run_manifest=not args.no_run_manifest,
            out_dir=args.out_dir,
            shared_cache_dir=args.shared_cache_dir,
        )


@dataclass
class CapitalCurvePolicy:
    """Continuous capital-aware execution policy.

    The function is deliberately continuous in log-capital so that a 4,999 USD
    account is not treated structurally differently from a 5,001 USD account.
    Final rebalance cadence and top_k are rounded to practical trading values,
    but the unrounded curve values are written to reports for auditability.
    """
    capital: float
    profile: str
    rebalance_every: int
    top_k: int
    max_position: float
    max_issuer: float
    risk_on_exposure_floor: float
    max_turnover: float
    no_trade_band: float
    min_trade_value: float
    max_annual_cost_budget: float
    fractional_shares_recommended: bool
    continuous_rebalance_every: float
    continuous_top_k: float
    continuous_max_position: float
    continuous_max_issuer: float
    policy_name: str
    reason: str


def _clip_float(x: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, x)))


def _interp_log_capital(capital: float, anchors: list[tuple[float, float]]) -> float:
    """Piecewise-linear interpolation over log10(capital)."""
    cap = float(capital)
    if not np.isfinite(cap) or cap <= 0:
        raise ValueError("capital must be positive")
    pts = sorted((math.log10(float(c)), float(v)) for c, v in anchors)
    x = math.log10(cap)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            t = (x - x0) / max(x1 - x0, 1e-12)
            return float(y0 + t * (y1 - y0))
    return pts[-1][1]


def _snap_to_allowed(value: float, allowed: list[int]) -> int:
    allowed = sorted(int(v) for v in allowed)
    return min(allowed, key=lambda v: abs(float(v) - float(value)))

def round_half_up_to_increment(value: float, increment: float) -> float:
    """Round a positive dollar value to the nearest increment using half-up semantics."""
    inc = float(increment)
    val = float(value)
    if not np.isfinite(val) or val <= 0 or not np.isfinite(inc) or inc <= 0:
        return max(0.0, val if np.isfinite(val) else 0.0)
    return float(math.floor(val / inc + 0.5) * inc)

def _smooth_micro_min_trade_value(
    capital: float,
    max_position: float,
    min_trade_value_anchors: list[tuple[float, float]],
) -> float:
    cap = float(capital)

    if cap <= 0:
        raise ValueError("capital must be positive")
    if max_position <= 0:
        raise ValueError("max_position must be positive")
    if max_position > 1:
        raise ValueError("max_position must be <= 1")
    if not min_trade_value_anchors:
        raise ValueError("min_trade_value_anchors must not be empty")

    micro_value = 1.0
    transition_lo = 100.0
    transition_hi = 1_000.0

    if cap <= transition_lo:
        return micro_value

    min_anchor_capital = min(float(c) for c, _ in min_trade_value_anchors)
    policy_capital = max(cap, min_anchor_capital)

    baseline_value = min(
        float(_interp_log_capital(policy_capital, min_trade_value_anchors)),
        cap * max_position * 0.50,
        cap * 0.05,
    )
    baseline_value = max(1.0, float(baseline_value))

    if cap >= transition_hi:
        return baseline_value

    x = (
        math.log10(cap) - math.log10(transition_lo)
    ) / (
        math.log10(transition_hi) - math.log10(transition_lo)
    )
    x = max(0.0, min(1.0, x))

    # Smoothstep: glättet Anfang und Ende des Übergangs
    x = x * x * (3.0 - 2.0 * x)

    return max(1.0, (1.0 - x) * micro_value + x * baseline_value)


def choose_capital_curve_policy(capital: float, *, fee_model: str = "trading212_us", policy: str = "balanced") -> CapitalCurvePolicy:
    """Trading-212-only continuous execution policy.

    The policy is intentionally different from the prior broker-minimum-oriented curve:
    Trading 212 has no broker minimum commission, so the main risks are signal
    staleness, insufficient market exposure, spread/slippage and FX. Therefore
    small accounts may trade more frequently and use lower minimum order values.

    policy:
      conservative = slower, lower turnover, lower exposure floor
      balanced     = default research / paper-trading profile
      active       = 5-trading-day signal cycle with higher turnover budget
      threshold    = 5-trading-day signal cycle with buy/hold spread emphasized
    """
    cap = float(capital)
    if not np.isfinite(cap) or cap <= 0:
        raise ValueError("capital must be positive")
    if str(fee_model).lower() != "trading212_us":
        raise ValueError("This package supports only fee_model='trading212_us'.")

    policy_name = str(policy or "balanced").lower().strip()
    if policy_name not in {"conservative", "balanced", "active", "threshold"}:
        raise ValueError("trading212 policy must be conservative, balanced, active or threshold")

    # Base anchors implement a continuous log-capital curve.  The 1k anchors are
    # deliberately more active than the previous capital_curve because the latest
    # Trading-212 backtest failed mainly through under-exposure and under-trading,
    # not through costs.
    if policy_name == "conservative":
        rebalance_every_anchors = [(1_000, 20), (5_000, 10), (25_000, 5), (100_000, 5)]
        topk_anchors = [(1_000, 10), (5_000, 12), (25_000, 20), (100_000, 20)]
        maxpos_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.075)]
        issuer_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.100)]
        turnover_cap_anchors = [(1_000, 0.25), (5_000, 0.30), (25_000, 0.35), (100_000, 0.35)]
        no_trade_band_anchors = [(1_000, 0.0200), (5_000, 0.0150), (25_000, 0.0100), (100_000, 0.0100)]
        min_trade_value_anchors = [(1_000, 15), (5_000, 25), (25_000, 50), (100_000, 100)]
        risk_floor = 0.85
        cost_budget = 0.015
    elif policy_name == "active":
        rebalance_every_anchors = [(1_000, 5), (5_000, 5), (25_000, 5), (100_000, 5)]
        topk_anchors = [(1_000, 12), (5_000, 15), (25_000, 20), (100_000, 20)]
        maxpos_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.075)]
        issuer_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.100)]
        turnover_cap_anchors = [(1_000, 0.50), (5_000, 0.45), (25_000, 0.40), (100_000, 0.35)]
        no_trade_band_anchors = [(1_000, 0.0100), (5_000, 0.0100), (25_000, 0.0100), (100_000, 0.0100)]
        min_trade_value_anchors = [(1_000, 10), (5_000, 25), (25_000, 50), (100_000, 100)]
        risk_floor = 0.95
        cost_budget = 0.025
    elif policy_name == "threshold":
        rebalance_every_anchors = [
            (1_000, 5),
            (5_000, 5),
            (25_000, 5),
            (100_000, 5),
        ]

        topk_anchors = [
            (1_000, 12),
            (5_000, 15),
            (25_000, 15),
            (100_000, 15),
        ]

        maxpos_anchors = [
            (1_000, 0.150),
            (5_000, 0.125),
            (25_000, 0.120),
            (100_000, 0.120),
        ]

        issuer_anchors = [
            (1_000, 0.150),
            (5_000, 0.150),
            (25_000, 0.150),
            (100_000, 0.150),
        ]

        turnover_cap_anchors = [
            (1_000, 0.35),
            (5_000, 0.35),
            (25_000, 0.30),
            (100_000, 0.30),
        ]

        no_trade_band_anchors = [
            (1_000, 0.0100),
            (5_000, 0.0075),
            (25_000, 0.0050),
            (100_000, 0.0050),
        ]

        min_trade_value_anchors = [
            (1_000, 10),
            (5_000, 25),
            (25_000, 50),
            (100_000, 100),
        ]
        risk_floor = 0.95
        cost_budget = 0.020
    else:  # balanced
        rebalance_every_anchors = [(1_000, 10), (5_000, 10), (25_000, 5), (100_000, 5)]
        topk_anchors = [(1_000, 10), (5_000, 12), (25_000, 20), (100_000, 20)]
        maxpos_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.075)]
        issuer_anchors = [(1_000, 0.150), (5_000, 0.125), (25_000, 0.100), (100_000, 0.100)]
        turnover_cap_anchors = [(1_000, 0.35), (5_000, 0.35), (25_000, 0.35), (100_000, 0.35)]
        no_trade_band_anchors = [(1_000, 0.0150), (5_000, 0.0125), (25_000, 0.0100), (100_000, 0.0100)]
        min_trade_value_anchors = [(1_000, 15), (5_000, 25), (25_000, 50), (100_000, 100)]
        risk_floor = 0.95
        cost_budget = 0.020

    rb_cont = _interp_log_capital(cap, rebalance_every_anchors)
    topk_cont = _interp_log_capital(cap, topk_anchors)
    maxpos_cont = _interp_log_capital(cap, maxpos_anchors)
    maxissuer_cont = _interp_log_capital(cap, issuer_anchors)
    max_turnover = _interp_log_capital(cap, turnover_cap_anchors)
    no_trade_band = _interp_log_capital(cap, no_trade_band_anchors)

    rebalance_every = _snap_to_allowed(rb_cont, [5, 10, 20])
    top_k = int(round(_clip_float(topk_cont, 8, 25)))
    max_position = _clip_float(maxpos_cont, 0.075, 0.20)
    max_issuer = _clip_float(maxissuer_cont, 0.075, 0.20)
    max_turnover = _clip_float(max_turnover, 0.20, 0.55)
    no_trade_band = _clip_float(no_trade_band, 0.005, 0.03)
    min_trade_value = _smooth_micro_min_trade_value(
        cap,
        max_position,
        min_trade_value_anchors,
    )

    return CapitalCurvePolicy(
        capital=cap,
        profile="trading212_" + policy_name,
        rebalance_every=int(rebalance_every),
        top_k=int(top_k),
        max_position=float(max_position),
        max_issuer=float(max_issuer),
        risk_on_exposure_floor=float(risk_floor),
        max_turnover=float(max_turnover),
        no_trade_band=float(no_trade_band),
        min_trade_value=float(min_trade_value),
        max_annual_cost_budget=float(cost_budget),
        fractional_shares_recommended=True,
        continuous_rebalance_every=float(rb_cont),
        continuous_top_k=float(topk_cont),
        continuous_max_position=float(maxpos_cont),
        continuous_max_issuer=float(maxissuer_cont),
        policy_name=policy_name,
        reason=(
            f"Trading-212 {policy_name} policy: frequent signal updates, broker-commission-free execution, "
            "lower minimum order values, capital-aware issuer/position caps, no-trade band, turnover budget, "
            "and explicit risk-on exposure recovery."
        ),
    )


def apply_capital_curve_policy_to_config(cfg: BacktestConfig) -> BacktestConfig:
    """Mutate cfg in-place when execution_policy_mode=capital_curve."""
    if str(getattr(cfg, "execution_policy_mode", "manual")).lower() != "capital_curve":
        return cfg
    policy_capital = float(cfg.backtest_capital)
    if str(getattr(cfg, "runtime_mode", "")).lower() in {"backtest", "both"}:
        research_capital = float(getattr(cfg, "research_backtest_capital", 0.0) or 0.0)
        if research_capital > 0:
            policy_capital = research_capital
    policy = choose_capital_curve_policy(policy_capital, fee_model="trading212_us", policy=str(getattr(cfg, "trading212_policy", "balanced")))
    cfg.rebalance_every = int(policy.rebalance_every)
    cfg.top_k = int(policy.top_k)
    cfg.max_position = float(policy.max_position)
    cfg.max_issuer = float(policy.max_issuer)
    cfg.risk_on_exposure_floor = max(float(getattr(cfg, "risk_on_exposure_floor", 0.0)), float(policy.risk_on_exposure_floor))
    cfg.max_turnover = float(policy.max_turnover)
    cfg.no_trade_band = float(policy.no_trade_band)
    cfg.capital_profile = policy.profile
    cfg.policy_rebalance_every = int(policy.rebalance_every)
    cfg.policy_top_k = int(policy.top_k)
    cfg.policy_max_position = float(policy.max_position)
    cfg.policy_max_issuer = float(policy.max_issuer)
    cfg.policy_risk_on_exposure_floor = float(policy.risk_on_exposure_floor)
    cfg.policy_max_turnover = float(policy.max_turnover)
    cfg.policy_no_trade_band = float(policy.no_trade_band)
    cfg.policy_min_trade_value = float(policy.min_trade_value)
    cfg.policy_cost_budget = float(policy.max_annual_cost_budget)
    cfg.policy_continuous_rebalance_every = float(policy.continuous_rebalance_every)
    cfg.policy_continuous_top_k = float(policy.continuous_top_k)
    cfg.policy_continuous_max_position = float(policy.continuous_max_position)
    cfg.policy_reason = policy.reason
    return cfg


def format_run_config_snapshot_lines(cfg: BacktestConfig, *, workers: int = 0) -> List[str]:
    """Human-readable resolved config for reproducibility (also written at run start)."""
    return [
        f"generated_at={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"mode={getattr(cfg, 'runtime_mode', 'both')}",
        f"out_dir={cfg.out_dir}",
        f"shared_cache_dir={getattr(cfg, 'shared_cache_dir', '')}",
        f"start={cfg.start}",
        f"benchmark={cfg.benchmark}",
        f"universe_mode={cfg.universe_mode}",
        f"universe_top_n={cfg.universe_top_n}",
        f"top_k={cfg.top_k}",
        f"rebalance_every={cfg.rebalance_every}",
        f"horizon={cfg.horizon}",
        f"train_years={cfg.train_years}",
        f"alpha_model_mode={cfg.alpha_model_mode}",
        f"random_seed={cfg.random_seed}",
        f"parallel_workers={workers}",
        f"parallel_profile={cfg.parallel_profile}",
        f"parallel_backtest_backend={cfg.parallel_backtest_backend}",
        f"n_jobs={cfg.n_jobs}",
        f"cpu_cores={cfg.cpu_cores}",
        f"system_ram_gb={cfg.system_ram_gb}",
        f"reuse_feature_cache={cfg.reuse_feature_cache}",
        f"force_rebuild_features={cfg.force_rebuild_features}",
        f"write_feature_cache={cfg.write_feature_cache}",
        f"skip_feature_parquet_write={cfg.skip_feature_parquet_write}",
        f"reuse_prediction_cache={cfg.reuse_prediction_cache}",
        f"force_rebuild_predictions={cfg.force_rebuild_predictions}",
        f"write_prediction_cache={cfg.write_prediction_cache}",
        f"skip_download_if_cached={cfg.skip_download_if_cached}",
        f"price_cache_ttl_hours={cfg.price_cache_ttl_hours}",
        f"risk_off_selection_mode={cfg.risk_off_selection_mode}",
        f"risk_off_momentum_variant={cfg.risk_off_momentum_variant}",
        f"risk_off_momentum_weight={cfg.risk_off_momentum_weight}",
        f"risk_off_gate_mode={cfg.risk_off_gate_mode}",
        f"risk_off_momentum_rescue_quantile={cfg.risk_off_momentum_rescue_quantile}",
        f"risk_off_force_exit_enabled={cfg.risk_off_force_exit_enabled}",
        f"naive_detailed_reporting={cfg.naive_detailed_reporting}",
        f"naive_detailed_variants={cfg.naive_detailed_variants}",
        f"no_naive_overlap={cfg.no_naive_overlap}",
        f"backtest_capital={cfg.backtest_capital}",
        f"research_backtest_capital={cfg.research_backtest_capital}",
        f"fee_model={cfg.fee_model}",
        f"trading212_policy={cfg.trading212_policy}",
        f"slippage_bps={cfg.slippage_bps}",
        f"cluster_mode={cfg.cluster_mode}",
        f"membership_mode={cfg.membership_mode}",
        f"membership_file={cfg.membership_file}",
        f"reproducibility_mode={cfg.reproducibility_mode}",
    ]


def write_run_config_snapshot(path: Path, cfg: BacktestConfig, *, workers: int = 0) -> None:
    path.write_text("\n".join(format_run_config_snapshot_lines(cfg, workers=workers)) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Active Alpha Model: backtest and signal generator")
    p.add_argument("--mode", choices=["backtest", "signal", "both"], default="both")
    p.add_argument("--tickers", default="", help="Comma-separated tickers. Overrides --tickers-file.")
    p.add_argument("--tickers-file", default="", help="Deprecated legacy option; not used by the normal no-legacy workflow.")
    p.add_argument("--ticker-source", choices=["sp500_pit", "sp500_auto", "wikipedia_sp500", "slickcharts_sp500", "cached_sp500"], default="sp500_pit", help="Ticker source: sp500_pit = historical S&P 500 point-in-time membership from ticker_membership.csv; sp500_auto = fresh cache, then Wikipedia, then Slickcharts, then stale cache fallback; wikipedia_sp500 and slickcharts_sp500 fetch directly; cached_sp500 uses saved snapshots.")
    p.add_argument("--ticker-cache-dir", default="universe_snapshots", help="Folder for S&P 500 universe snapshots used by sp500_auto and cached_sp500.")
    p.add_argument("--ticker-cache-max-age-days", type=int, default=7, help="For sp500_auto: use sp500_latest.csv without online refresh if it is not older than this many days.")
    p.add_argument("--ticker-snapshot-date", default="", help="For cached_sp500: snapshot date YYYY-MM-DD. Empty uses the latest available snapshot.")
    p.add_argument("--no-save-universe-snapshot", action="store_true", help="Do not save a universe snapshot when loading an online S&P 500 source.")
    p.add_argument("--no-ticker-fallback", action="store_true", help="Fail instead of falling back to stale cached/file sources if the requested S&P 500 source cannot be loaded.")
    p.add_argument("--membership-file", default="ticker_membership.csv", help="Optional point-in-time membership file with columns ticker,valid_from,valid_to,source,reason. Used to prevent newly added tickers from entering historical backtests retroactively.")
    p.add_argument("--membership-mode", choices=["off", "auto", "strict"], default="auto", help="Membership filter mode. off = ignore membership file; auto = use it when it exists; strict = require it and fail if missing.")
    p.add_argument("--membership-filter-signal", action="store_true", help="Also apply membership valid_from/valid_to filtering in --mode signal. Default is off so current paper snapshots are usable even when the latest market date is before the snapshot date.")
    p.add_argument("--no-update-membership", action="store_true", help="Do not append new non-file ticker-source symbols to ticker_membership.csv with a forward-only valid_from date.")
    p.add_argument("--asset-master-file", default="asset_master.csv", help="Asset master file updated from snapshots with first_seen/last_seen metadata.")
    p.add_argument("--no-update-asset-master", action="store_true", help="Do not update asset_master.csv from non-file ticker-source snapshots.")
    p.add_argument("--benchmark", default="SPY", help="Benchmark ticker, e.g. SPY, ^GSPC, ACWI.")
    p.add_argument("--start", default="2012-01-01")
    p.add_argument("--signal-lookback-years", type=int, default=9, help="For --mode signal only: load this many years of history instead of the full --start date. Backtests are unaffected.")
    p.add_argument("--horizon", type=int, default=10, help="Forward forecast horizon in trading days.")
    p.add_argument("--rebalance-every", type=int, default=5, help="Rebalance interval in trading days.")
    p.add_argument("--top-k", type=int, default=15)
    p.add_argument("--max-position", type=float, default=0.12)
    p.add_argument("--good-regime-exposure", type=float, default=1.0)
    p.add_argument("--bad-regime-exposure", type=float, default=0.60)
    p.add_argument("--risk-on-exposure-floor", type=float, default=0.95, help="Minimum invested exposure in risk-on regime, if enough candidates exist.")
    p.add_argument("--min-edge", type=float, default=0.0010, help="Soft minimum alpha. In risk-on it influences ranking, not hard cash gating.")
    p.add_argument("--lcb-z", type=float, default=0.10, help="Conservatism multiplier: alpha_lcb = alpha - z*lcb_scale*RMSE.")
    p.add_argument("--lcb-scale", type=float, default=0.10, help="Small RMSE scaling; prevents excessive cash drift.")
    p.add_argument("--cost-bps", type=float, default=10.0, help="Basis-point haircut used inside the alpha target; not a selectable fee model.")
    p.add_argument("--fee-model", choices=["trading212_us"], default="trading212_us", help="Broker cost model. Only trading212_us is supported in this package.")
    p.add_argument("--backtest-capital", type=float, default=100000.0, help="Assumed portfolio capital for broker-cost backtests.")
    p.add_argument("--trading212-policy", choices=["conservative", "balanced", "active", "threshold"], default="balanced", help="Trading-212 execution policy used by --execution-policy-mode capital_curve.")
    p.add_argument("--no-buy-hold-spread", action="store_true", help="Disable buy/hold spread; default keeps acceptable existing positions to reduce unnecessary churn.")
    p.add_argument("--buy-rank-multiple", type=float, default=1.0, help="Buy threshold multiple of top_k; informational for future policies.")
    p.add_argument("--hold-rank-multiple", type=float, default=2.5, help="Existing positions can be held up to top_k times this rank multiple.")
    p.add_argument("--sell-rank-multiple", type=float, default=3.0, help="Reserved sell threshold multiple for threshold policy diagnostics.")
    p.add_argument("--tail-prune-enabled", action="store_true", help="Enable residual-position sweep and soft position-cap pruning after trade controls.")
    p.add_argument("--residual-weight-floor", type=float, default=0.005, help="Portfolio-weight floor for residual tail positions, e.g. 0.005 = 0.5%%.")
    p.add_argument("--residual-sell-min-value", type=float, default=0.01, help="Minimum USD value for sell-to-zero residual exceptions in backtest order filtering.")
    p.add_argument("--order-value-rounding", type=float, default=1.0, help="Round non-liquidating backtest/paper order values to this USD increment. Default 1.0 = full-dollar order values; 0 disables.")
    p.add_argument("--broker-min-remaining-position-value", type=float, default=1.0, help="If a SELL would leave a positive residual below this USD value, force sell-to-zero.")
    p.add_argument("--max-n-positions-soft", type=int, default=35, help="Soft target number of positions after tail pruning.")
    p.add_argument("--max-n-positions-hard", type=int, default=45, help="Hard diagnostic ceiling for positions; pruning relaxes only when constraints/exposure require it.")
    p.add_argument("--no-tail-prune-reallocate", action="store_true", help="Do not reallocate freed residual weight across surviving positions.")
    p.add_argument("--max-tail-reallocation-per-name", type=float, default=0.01, help="Maximum extra weight a single survivor may receive from tail-prune reallocation, e.g. 0.01 = +1 percentage point.")
    p.add_argument("--tail-reallocation-step", type=float, default=0.0025, help="Waterfall allocation step size for tail-prune reallocation, e.g. 0.0025 = 25 bps per pass.")
    p.add_argument("--tail-reallocation-rounds", type=int, default=10, help="Maximum number of waterfall passes during tail-prune reallocation.")
    p.add_argument("--tail-prune-min-exposure-buffer", type=float, default=0.02, help="Allowed exposure shortfall below the risk-on exposure floor before tail-prune relaxes or falls back.")
    p.add_argument("--slippage-bps", type=float, default=0.0, help="Additional slippage/spread buffer in basis points.")
    p.add_argument("--market-impact-bps", type=float, default=0.0, help="Optional market-impact cost in bps on trade value. Usually 0 for small S&P 500 retail orders.")
    p.add_argument("--trading212-sec-fee-rate", type=float, default=0.0000278, help="Trading 212 US sell-side SEC Transaction Fee rate. Official Trading 212 help currently states $0.0000278 of sell order value / 0.00278%%.")
    p.add_argument("--trading212-finra-taf-per-share", type=float, default=0.000195, help="Trading 212 US sell-side FINRA fee per covered stock/ETF share sold.")
    p.add_argument("--trading212-fx-bps", type=float, default=15.0, help="Trading 212 FX fee in bps. Default 15 bps models the official 0.15%% FX fee when instrument currency differs from account/base currency. Use 0 only when there is no FX conversion.")
    p.add_argument("--min-adv", type=float, default=10_000_000.0, help="Minimum 20d average dollar volume.")
    p.add_argument("--max-ann-vol", type=float, default=1.25, help="Exclude only extremely volatile stocks above this annualized 20d vol.")
    p.add_argument("--max-sector", type=float, default=0.55, help="Maximum portfolio weight in one coarse sector.")
    p.add_argument("--max-issuer", type=float, default=0.15, help="Maximum portfolio weight in one issuer, e.g. GOOG+GOOGL.")
    p.add_argument("--max-correlation-cluster", type=float, default=0.40, help="Legacy/default correlation cluster cap. 0 disables this constraint unless static/dynamic caps are set.")
    p.add_argument("--max-portfolio-beta", type=float, default=1.25, help="Base cap for weighted portfolio beta. 0 disables this constraint.")
    p.add_argument("--beta-cap-mode", choices=["fixed", "dynamic"], default="dynamic", help="Dynamic mode tightens beta in risk-off and permits higher beta only in strong, broad risk-on regimes.")
    p.add_argument("--dynamic-beta-risk-off", type=float, default=1.10)
    p.add_argument("--dynamic-beta-normal", type=float, default=1.25)
    p.add_argument("--dynamic-beta-risk-on", type=float, default=1.40)
    p.add_argument("--dynamic-beta-strong", type=float, default=1.50)
    p.add_argument("--static-cluster-cap", type=float, default=0.40, help="Cap for static/auditable thematic clusters.")
    p.add_argument("--dynamic-cluster-cap", type=float, default=0.50, help="Cap for stable dynamic correlation clusters.")
    p.add_argument("--cluster-constraint-mode", choices=["static_only", "dynamic_only", "both_restrictive"], default="static_only", help="Cluster cap enforcement mode.")
    p.add_argument("--max-gross-exposure", type=float, default=1.0, help="Hard cap for total long exposure. 1.0 means unlevered long-only; values above 1.0 explicitly allow leverage.")
    p.add_argument("--universe-mode", choices=["static", "diy_pit_liquidity"], default="diy_pit_liquidity", help="static uses all tickers in the file; diy_pit_liquidity forms a date-specific top-N universe from historical liquidity only.")
    p.add_argument("--universe-top-n", type=int, default=100, help="Number of names kept in the DIY point-in-time liquidity universe on each date.")
    p.add_argument("--universe-adv-lookback", type=int, default=63, help="Rolling trading days used for DIY universe dollar-volume ranking.")
    p.add_argument("--universe-min-adv", type=float, default=10_000_000.0, help="Minimum trailing average dollar volume for DIY universe eligibility.")
    p.add_argument("--universe-min-price", type=float, default=5.0, help="Minimum close price for DIY universe eligibility.")
    p.add_argument("--universe-min-history-days", type=int, default=252, help="Minimum observed price history before a ticker can enter the DIY universe.")
    p.add_argument("--no-trade-band", type=float, default=0.01, help="Do not change an existing position if abs(target-prev) is below this weight threshold.")
    p.add_argument("--weight-smoothing", type=float, default=0.50, help="Move this fraction from previous to new target weights. 1.0 disables smoothing.")
    p.add_argument("--max-turnover", type=float, default=0.35, help="Maximum one-way portfolio turnover per rebalance.")
    p.add_argument("--execution-policy-mode", choices=["manual", "capital_curve"], default="manual", help="Execution policy. capital_curve applies the Trading-212 policy to cadence, top_k, issuer/position caps, turnover, no-trade-band, exposure floor and minimum trade value.")
    p.add_argument("--capital-profile", default="", help="Capital-aware policy profile label written to reports, e.g. micro/small/medium/large.")
    p.add_argument("--policy-rebalance-every", type=int, default=0, help="Recommended rebalance cadence from capital-aware policy, written to reports.")
    p.add_argument("--policy-top-k", type=int, default=0, help="Recommended top_k from capital-aware policy, written to reports.")
    p.add_argument("--policy-max-position", type=float, default=0.0, help="Recommended max_position from capital-aware policy, written to reports.")
    p.add_argument("--policy-max-issuer", type=float, default=0.0, help="Recommended max_issuer from Trading-212 policy, written to reports.")
    p.add_argument("--policy-risk-on-exposure-floor", type=float, default=0.0, help="Recommended risk-on exposure floor from Trading-212 policy, written to reports.")
    p.add_argument("--policy-max-turnover", type=float, default=0.0, help="Recommended max_turnover from capital-aware policy, written to reports.")
    p.add_argument("--policy-no-trade-band", type=float, default=0.0, help="Recommended no_trade_band from capital-aware policy, written to reports.")
    p.add_argument("--policy-min-trade-value", type=float, default=0.0, help="Recommended minimum order value from capital-aware policy, written to reports.")
    p.add_argument("--policy-cost-budget", type=float, default=0.0, help="Annual cost-budget from the continuous capital policy, written to reports.")
    p.add_argument("--policy-continuous-rebalance-every", type=float, default=0.0, help="Unrounded rebalance cadence from the continuous capital curve, written to reports.")
    p.add_argument("--policy-continuous-top-k", type=float, default=0.0, help="Unrounded top_k from the continuous capital curve, written to reports.")
    p.add_argument("--policy-continuous-max-position", type=float, default=0.0, help="Unrounded max_position from the continuous capital curve, written to reports.")
    p.add_argument("--policy-reason", default="", help="Capital-aware execution-policy rationale written to reports.")
    p.add_argument("--alpha-model-mode", choices=["ensemble", "ml_only", "rank_only", "elastic_only", "gbm_only"], default="ensemble", help="Alpha model ablation switch for robustness tests. ensemble = ElasticNet+GBM+rank fallback; ml_only excludes rank_score; rank_only excludes ML forecasts.")
    p.add_argument("--extra-benchmarks", default="QQQ,RSP,MTUM,QUAL,VUG,VLUE,USMV,SMH", help="Comma-separated ETF/proxy benchmarks downloaded for comparison and factor-proxy regression; they are excluded from the tradable universe.")
    p.add_argument("--no-naive-momentum-baseline", action="store_true", help="Disable the internal naive top-k rank/momentum baseline.")
    p.add_argument("--naive-momentum-variants", default="mom_63_top12,mom_126_top12,mom_252_21_top12,mom_blend_top12,sector_neutral_momentum,cluster_neutral_momentum", help="Comma-separated internal momentum baseline variants for model validation.")
    p.add_argument("--no-custom-benchmarks", action="store_true", help="Disable internally generated custom control benchmarks such as universe-equal-weight and neutralized momentum baselines.")
    p.add_argument("--no-statistical-diagnostics", action="store_true", help="Disable Newey-West, bootstrap and deflated-Sharpe diagnostic files.")
    p.add_argument(
        "--minimal-backtest-reporting",
        action="store_true",
        help="Write only core backtest CSVs and a short report (skip factor regression, benchmark comparison, bootstrap).",
    )
    p.add_argument(
        "--returns-fast-path",
        action="store_true",
        help="Phase B only: skip per-rebalance decision/weight diagnostic rows (strategy_daily_returns unchanged). Enable after M1 reference validation.",
    )
    p.add_argument(
        "--path-sim-checkpoint",
        action="store_true",
        help="Phase B: save/resume path_sim_checkpoint.pkl every 25 rebalances (survives hang/kill).",
    )
    p.add_argument(
        "--backtest-scope",
        choices=("full", "path-only"),
        default="full",
        help="full = Phase A+B walk-forward; path-only = Phase B using cached predictions (cost/slippage sweeps).",
    )
    p.add_argument(
        "--prediction-cache-dir",
        default="",
        help="Directory with prediction_cache.pkl (defaults to --out-dir). Used with --backtest-scope path-only.",
    )
    p.add_argument("--bootstrap-iterations", type=int, default=250, help="Block-bootstrap iterations for statistical diagnostics. 0 disables bootstrap intervals.")
    p.add_argument("--random-seed", type=int, default=42, help="Random seed for bootstrap diagnostics.")
    p.add_argument("--n-jobs", default="auto", help="Parallel workers. auto/all = min(--cpu-cores, RAM budget). Use 1 for serial or an explicit integer.")
    p.add_argument("--parallel-backtest-backend", choices=["thread", "process"], default="process", help="Parallel backend for walk-forward prediction/training. process uses multiprocessing.Pool across cores; thread shares memory but is limited by the GIL.")
    p.add_argument("--cpu-cores", type=int, default=16, help="Physical CPU cores for auto worker sizing. Ryzen 9 3950X: 16 (not 32 SMT threads).")
    p.add_argument("--system-ram-gb", type=int, default=64, help="Installed system RAM in GB; used with --n-jobs auto to avoid process oversubscription on Windows x64.")
    p.add_argument("--parallel-profile", choices=["auto", "normal", "high"], default="high", help="Parallel tuning profile. high compacts feature tables (float32) and uses larger pool chunks (recommended for 64 GB x64).")
    p.add_argument("--reuse-feature-cache", action="store_true", help="Load cached features/returns from out-dir when fingerprint matches (skips download and feature engineering).")
    p.add_argument("--force-rebuild-features", action="store_true", help="Ignore the reusable feature cache and rebuild features (still writes cache unless --no-feature-cache).")
    p.add_argument("--no-feature-cache", action="store_true", help="Do not write the reusable feature cache after building features.")
    p.add_argument("--skip-feature-parquet-write", action="store_true", help="Skip writing out-dir/features.parquet when features were loaded from cache (backtest/both modes).")
    p.add_argument("--no-naive-overlap", action="store_true", help="Run naive momentum baselines after Phase B instead of overlapping with path simulation (reduces CPU contention).")
    p.add_argument("--reuse-prediction-cache", action="store_true", help="Load cached walk-forward ML predictions from out-dir when fingerprint matches (skips Phase A).")
    p.add_argument("--force-rebuild-predictions", action="store_true", help="Ignore the prediction cache and recompute Phase-A ML (still writes cache unless --no-prediction-cache).")
    p.add_argument("--no-prediction-cache", action="store_true", help="Do not write the reusable prediction cache after Phase A.")
    p.add_argument("--skip-download-if-cached", action="store_true", help="Reuse cached OHLCV downloads from out-dir/price_cache when fingerprint and TTL match.")
    p.add_argument("--price-cache-ttl-hours", type=int, default=24, help="Max age of the price download cache in hours (0 disables TTL expiry).")
    p.add_argument("--risk-off-selection-mode", choices=["legacy", "mom_blend_replace", "mom_blend_blend"], default="legacy", help="Risk-off stock selection: legacy ensemble score, full momentum replace, or rank blend with ensemble.")
    p.add_argument("--risk-off-momentum-variant", default="mom_blend_top12", help="Naive momentum variant used for risk-off selection blending/rescue.")
    p.add_argument("--risk-off-momentum-weight", type=float, default=0.70, help="Momentum rank weight in mom_blend_blend mode (ensemble gets 1-weight).")
    p.add_argument("--risk-off-gate-mode", choices=["legacy", "base_only", "momentum_rescue"], default="legacy", help="Risk-off eligibility gates; momentum_rescue adds top-quantile momentum rescue.")
    p.add_argument("--risk-off-momentum-rescue-quantile", type=float, default=0.70, help="Minimum momentum rank percentile for rescue eligibility in risk-off.")
    p.add_argument("--risk-off-force-exit-enabled", action="store_true", help="Force-exit held positions in risk-off that fail both legacy and momentum-rescue gates.")
    p.add_argument("--naive-detailed-reporting", action="store_true", help="Export full naive baseline CSV diagnostics after backtest (slow; research only).")
    p.add_argument("--no-naive-detailed-reporting", action="store_true", help="Skip detailed naive baseline CSV exports (weights, decisions, costs).")
    p.add_argument("--naive-position-contributions", action="store_true", help="Include per-position return contributions in naive detailed exports (slower).")
    p.add_argument("--naive-detailed-variants", default="mom_blend_top12,mom_63_top12,mom_blend_matched_controls", help="Comma-separated naive variants to export with full diagnostic CSVs.")
    p.add_argument("--risk-regime-mode", choices=["strict", "normal", "loose"], default="normal", help="Risk-on/risk-off rule sensitivity for robustness tests.")
    p.add_argument("--exposure-controller", choices=["binary", "gradual", "gradual_alpha"], default="gradual_alpha", help="Portfolio exposure controller. gradual is the Stage-3 default; binary reproduces the old risk-on/risk-off target.")
    p.add_argument("--cash-filler-mode", choices=["off", "conservative", "balanced", "balanced_plus_low_beta", "benchmark_completion"], default="benchmark_completion", help="Controlled filler sleeve for residual cash in risk-on regimes; balanced_plus_low_beta adds beta-efficient diversifiers when caps block high-beta winners.")
    p.add_argument("--cash-filler-max-position", type=float, default=0.03, help="Maximum single-name filler weight added by the alpha filler sleeve.")
    p.add_argument("--cash-filler-min-score", type=float, default=0.0, help="Minimum selection_score for alpha-filler candidates.")
    p.add_argument("--benchmark-completion-ticker", default="SPY", help="Benchmark ETF used to complete residual exposure when cash_filler_mode=benchmark_completion.")
    p.add_argument("--benchmark-completion-max-weight", type=float, default=0.25, help="Maximum portfolio weight allocated to the benchmark-completion sleeve.")
    p.add_argument("--low-beta-filler-max-position", type=float, default=0.015, help="Maximum single-name weight for the low-beta diversification filler.")
    p.add_argument("--low-beta-filler-beta-max", type=float, default=0.90, help="Maximum beta_252 for low-beta filler candidates.")
    p.add_argument("--low-beta-filler-min-score", type=float, default=-0.05, help="Minimum selection_score for low-beta filler candidates.")
    p.add_argument("--low-beta-filler-max-vol-63", type=float, default=0.75, help="Maximum 63d annualized vol for low-beta filler candidates.")
    p.add_argument("--exposure-recovery-policy", choices=["off", "cause_aware"], default="cause_aware", help="Cause-aware recovery keeps cash only when it is intentional and attempts beta-efficient filling otherwise.")
    p.add_argument("--cluster-mode", choices=["static", "dynamic_diagnostic", "dynamic_guardrail", "dynamic_enforced"], default="dynamic_diagnostic", help="Cluster handling. dynamic_guardrail uses statistically stable rolling-correlation clusters and otherwise falls back to the static audit map.")
    p.add_argument("--dynamic-cluster-window-short", type=int, default=126, help="Short rolling-return window for dynamic cluster diagnostics.")
    p.add_argument("--dynamic-cluster-window-long", type=int, default=252, help="Long rolling-return window used to confirm cluster stability.")
    p.add_argument("--dynamic-cluster-corr-threshold", type=float, default=0.65, help="Minimum return correlation for dynamic cluster graph edges.")
    p.add_argument("--dynamic-cluster-min-overlap", type=float, default=0.50, help="Minimum short/long component overlap for dynamic cluster enforcement.")
    p.add_argument("--reproducibility-mode", choices=["normal", "strict"], default="normal", help="strict requires deterministic input files before running.")
    p.add_argument("--research-backtest-capital", type=float, default=100000.0, help="Capital used to choose capital-curve research parameters in backtests/both. Execution-cost dollars still use --backtest-capital.")
    p.add_argument("--no-run-manifest", action="store_true", help="Do not write run_manifest.json.")
    p.add_argument("--self-test", action="store_true", help="Run allocator and constraint unit tests, then exit without downloading market data.")
    p.add_argument("--train-years", type=int, default=7)
    p.add_argument("--ml-retrain-every", type=int, default=1, help="Retrain walk-forward ML every N rebalances (2 = every second rebalance).")
    p.add_argument("--min-train-rows", type=int, default=2500)
    p.add_argument("--out-dir", default="model_output")
    p.add_argument("--shared-cache-dir", default="", help="Shared directory for feature/price caches. Variant outputs still go to --out-dir. Used by the robustness lab.")
    p.add_argument("--dry-run", action="store_true", help="Print resolved configuration and planned phases, then exit without downloading data.")
    p.add_argument("--cache-status", action="store_true", help="Print feature/price/prediction cache status for --out-dir, then exit.")
    p.add_argument("--no-plot", action="store_true")
    p.add_argument("--fail-on-reporting-error", action="store_true", help="Fail the run when an optional reporting/diagnostic step fails. Default is to log reporting_errors.txt and keep core backtest outputs.")
    p.add_argument("--plain-progress", action="store_true", help="Use simple text progress instead of the live dashboard.")
    p.add_argument("--gui", action="store_true", help="Use native Windows progress window (requires PySide6).")
    p.add_argument("--no-gui", action="store_true", help="Force console dashboard even if PySide6 is available.")
    return p.parse_args()

def normalize_yfinance_ticker(symbol: str) -> str:
    """Normalize external index symbols into yfinance-compatible tickers."""
    tk = str(symbol).strip().upper()
    if not tk or tk in {"NAN", "NONE"}:
        return ""
    tk = tk.replace(".", "-")
    tk = tk.replace(" ", "")
    return tk



def parse_extra_benchmark_tickers(cfg_or_value: object) -> List[str]:
    """Return normalized, unique extra benchmark tickers.

    These proxies are downloaded and reported, but explicitly excluded from the
    tradable universe. They are intended for diagnostic comparison against QQQ,
    RSP, Momentum/Quality/Value/Low-Vol ETFs and sector/theme proxies.
    """
    raw = getattr(cfg_or_value, "extra_benchmarks", cfg_or_value)
    if raw is None:
        return []
    out: List[str] = []
    for item in str(raw).replace(";", ",").split(","):
        tk = normalize_yfinance_ticker(item)
        if tk and tk not in out:
            out.append(tk)
    return out


def non_tradable_benchmark_tickers(cfg: BacktestConfig) -> set[str]:
    tickers = {normalize_yfinance_ticker(str(cfg.benchmark).upper())}
    tickers.update(parse_extra_benchmark_tickers(cfg))
    return {t for t in tickers if t}
def enforce_reproducibility_inputs(cfg: BacktestConfig) -> None:
    mode = str(getattr(cfg, "reproducibility_mode", "normal") or "normal").lower().strip()
    if mode != "strict":
        return
    missing = []
    for attr in ["membership_file", "asset_master_file"]:
        path = Path(str(getattr(cfg, attr, "") or ""))
        if not path.exists() or path.stat().st_size == 0:
            missing.append(f"{attr}={path}")
    if str(getattr(cfg, "ticker_source", "")).lower() not in {"sp500_pit", "cached_sp500"}:
        missing.append("ticker_source must be sp500_pit or cached_sp500 in strict mode")
    if missing:
        raise RuntimeError("Strict reproducibility mode failed: " + "; ".join(missing))
