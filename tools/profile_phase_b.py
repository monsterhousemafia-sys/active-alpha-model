#!/usr/bin/env python3
"""Profile Phase B (walk-forward path simulation) section timings."""
from __future__ import annotations

import argparse
import pickle
import sys
from collections import defaultdict
from pathlib import Path
from time import monotonic
from typing import Any, DefaultDict, Dict, List, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_backtest import (  # noqa: E402
    _accumulate_vectorized_period_returns,
    _rebalance_period_bounds,
)
from aa_config import BacktestConfig  # noqa: E402
from aa_constants import deduplicate_dataframe_columns  # noqa: E402
from aa_execution import (  # noqa: E402
    apply_buy_hold_spread,
    apply_min_trade_value_filter,
    enforce_hard_position_count,
    estimate_backtest_rebalance_costs,
    fee_model_label,
    final_position_hygiene_metrics,
)
from aa_features import (  # noqa: E402
    _try_load_feature_cache,
    _try_load_prediction_cache,
    build_feature_by_date,
)
from aa_portfolio import (  # noqa: E402
    apply_tail_pruning,
    apply_trade_controls,
    classify_cash_reason,
    compute_risk_off_forced_exit_tickers,
    constraint_binding_metrics,
    portfolio_diagnostics,
    project_to_valid_by_blending,
    trim_to_beta_cap,
    trim_to_exposure_cap,
    trim_to_group_caps,
    validate_weights,
)


def _default_cfg(out_dir: Path) -> BacktestConfig:
    return BacktestConfig(
        out_dir=str(out_dir),
        shared_cache_dir=str(ROOT / "robustness_results_trading212" / "_shared_cache"),
        start="2012-01-01",
        benchmark="SPY",
        universe_mode="diy_pit_liquidity",
        universe_top_n=100,
        universe_adv_lookback=63,
        universe_min_adv=10_000_000,
        universe_min_price=5,
        universe_min_history_days=252,
        ticker_source="sp500_pit",
        membership_mode="strict",
        membership_file=str(ROOT / "ticker_membership.csv"),
        horizon=10,
        rebalance_every=5,
        train_years=7,
        top_k=15,
        reuse_feature_cache=True,
        reuse_prediction_cache=True,
    )


def _load_data(out_dir: Path, cfg: BacktestConfig) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[Any, Any], int]:
    n_tickers = int(getattr(cfg, "universe_top_n", 100) or 100)
    pack, reject = _try_load_feature_cache(out_dir, cfg, n_tickers)
    if pack is None:
        shared = Path(cfg.shared_cache_dir) / "features"
        fallback_dir = None
        if shared.is_dir():
            for meta_path in shared.glob("*/feature_cache_meta.json"):
                fallback_dir = meta_path.parent
                break
        if fallback_dir is None:
            raise RuntimeError(f"Feature cache load failed: {reject}")
        features = pd.read_parquet(fallback_dir / "feature_cache.parquet")
        returns = pd.read_parquet(fallback_dir / "returns_cache.parquet")
        if "date" in features.columns:
            features["date"] = pd.to_datetime(features["date"])
        if not isinstance(returns.index, pd.DatetimeIndex):
            returns.index = pd.to_datetime(returns.index)
    else:
        features, _bench, returns = pack
    n_tickers = int(features["ticker"].nunique())
    cached, pred_reject, _missing = _try_load_prediction_cache(out_dir, cfg, n_tickers, [])
    if cached is None:
        pkl = out_dir / "prediction_cache.pkl"
        if pkl.exists():
            with pkl.open("rb") as fh:
                cached = pickle.load(fh)
        else:
            raise RuntimeError(f"Prediction cache load failed: {pred_reject}")
    return features, returns, cached, n_tickers


def profile_phase_b(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    prediction_cache: Dict[Any, Any],
    cfg: BacktestConfig,
) -> Tuple[float, Dict[str, float], Dict[str, int]]:
    timings: DefaultDict[str, float] = defaultdict(float)
    counts: DefaultDict[str, int] = defaultdict(int)

    def tick(name: str, t0: float) -> None:
        timings[name] += monotonic() - t0
        counts[name] += 1

    dates = sorted(features["date"].dropna().unique())
    dates = [pd.Timestamp(d) for d in dates]
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]

    t0 = monotonic()
    feature_by_date = build_feature_by_date(features)
    tick("setup_feature_by_date", t0)

    ret_index = returns.index
    ret_np = returns.to_numpy(dtype=np.float32, copy=False)
    col_to_j = {str(c): j for j, c in enumerate(returns.columns)}
    period_bounds_list = _rebalance_period_bounds(rebalance_dates, ret_index)
    prediction_cache_norm = {pd.Timestamp(k): v for k, v in prediction_cache.items()}
    decision_head_n = max(50, int(cfg.top_k))
    bridge_keys = (
        "desired_exposure", "regime_target_exposure", "exposure_controller_score", "signal_breadth_positive",
        "avg_alpha_lcb", "n_positive_candidates_for_exposure", "exposure_before_constraints",
        "exposure_after_position_cap", "exposure_after_issuer_cap", "exposure_after_sector_cap",
        "exposure_after_cluster_cap", "exposure_after_beta_cap", "exposure_after_cash_filler",
        "effective_max_portfolio_beta", "beta_cap_mode_effective", "cash_filler_enabled",
        "cash_filler_added_weight", "cash_filler_n_names", "low_beta_filler_enabled",
        "low_beta_filler_added_weight", "low_beta_filler_n_names", "n_candidates", "n_eligible_candidates",
        "n_selected_candidates", "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol",
    )
    fee_keys = (
        "sec_fee_cost", "finra_taf_cost", "cat_fee_cost", "clearing_fee_cost", "exchange_fee_cost",
        "pass_through_fee_cost", "fx_fee_cost", "market_impact_cost", "sec_fee_dollars", "finra_taf_dollars",
        "cat_fee_dollars", "clearing_fee_dollars", "exchange_fee_dollars", "pass_through_fee_dollars",
        "fx_fee_dollars", "market_impact_dollars",
    )

    daily_dates: List[pd.Timestamp] = []
    daily_values: List[float] = []
    decision_rows: List[Dict[str, Any]] = []
    weight_rows: List[Dict[str, Any]] = []
    prev_weights = pd.Series(dtype=float)
    backtest_equity = float(cfg.backtest_capital) if float(getattr(cfg, "backtest_capital", 0.0)) > 0 else 100000.0

    loop_t0 = monotonic()
    n_rebalances = 0
    for n, rb in enumerate(rebalance_dates[:-1]):
        snapshot = feature_by_date.get(rb)
        res = prediction_cache_norm.get(pd.Timestamp(rb))
        if res is None or res.get("status") != "ok":
            continue
        n_rebalances += 1

        t = monotonic()
        rmse = float(res.get("rmse", np.nan))
        target_weights = res["target_weights"]
        ranked = res["ranked"]
        effective_beta_cap = float(res.get("effective_beta_cap", getattr(cfg, "max_portfolio_beta", 0.0) or 0.0))
        tick("cache_lookup", t)

        from dataclasses import replace

        t = monotonic()
        cfg_rb = replace(cfg, max_portfolio_beta=effective_beta_cap)
        target_exposure_before_controls = float(target_weights.sum()) if not target_weights.empty else 0.0
        risk_on_flag = bool(ranked["risk_on"].dropna().iloc[0]) if "risk_on" in ranked.columns and ranked["risk_on"].notna().any() else False
        forced_exit = compute_risk_off_forced_exit_tickers(ranked, prev_weights, cfg_rb, risk_on=risk_on_flag)
        target_weights = apply_buy_hold_spread(target_weights, prev_weights, ranked, cfg_rb, forced_exit_tickers=forced_exit)
        tick("buy_hold_spread", t)

        t = monotonic()
        weights = apply_trade_controls(target_weights, prev_weights, ranked, cfg_rb)
        weights, tail_diag = apply_tail_pruning(weights, prev_weights, ranked, cfg_rb)
        weights = apply_min_trade_value_filter(weights, prev_weights, backtest_equity, cfg_rb)
        weights = enforce_hard_position_count(weights, ranked, cfg_rb)
        tick("trade_controls_chain", t)

        t = monotonic()
        try:
            validate_weights(weights, ranked, cfg_rb, context="post_min_trade_value")
        except ValueError:
            weights = project_to_valid_by_blending(weights, target_weights, ranked, cfg_rb, context="post_min_trade_value_projection")
            weights = enforce_hard_position_count(weights, ranked, cfg_rb)
            weights = trim_to_exposure_cap(weights, cfg_rb)
            weights = trim_to_group_caps(weights, ranked, cfg_rb)
            weights = trim_to_beta_cap(weights, ranked, cfg_rb)
            validate_weights(weights, ranked, cfg_rb, context="post_min_trade_value_strict_final")
        tick("validate_or_project", t)

        t = monotonic()
        diag = portfolio_diagnostics(weights, ranked, cfg_rb)
        final_hygiene_diag = final_position_hygiene_metrics(weights, cfg_rb)
        tick("diagnostics", t)

        i0, i1 = period_bounds_list[n]
        if i1 <= i0:
            continue

        t = monotonic()
        idx = target_weights.index.union(prev_weights.index)
        tw_v = target_weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        pw_v = prev_weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        w_v = weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        raw_turnover = float(np.abs(tw_v - pw_v).sum())
        delta_v = w_v - pw_v
        turnover = float(np.abs(delta_v).sum())
        delta_weights = pd.Series(delta_v, index=idx)
        fee_diag = estimate_backtest_rebalance_costs(delta_weights, snapshot, backtest_equity, cfg_rb)
        tx_cost = float(fee_diag["tx_cost"])
        equity_before_rebalance = float(backtest_equity)
        period_dates, period_returns, growth = _accumulate_vectorized_period_returns(
            weights, returns, pd.Index([]), tx_cost,
            ret_np=ret_np, ret_index=ret_index, col_to_j=col_to_j, period_bounds=(i0, i1),
        )
        daily_dates.extend(period_dates)
        daily_values.extend(period_returns)
        backtest_equity *= growth
        tick("fees_and_pnl", t)

        t = monotonic()
        dec_extra: Dict[str, Any] = {
            "rebalance_date": rb,
            "rmse": rmse,
            "raw_turnover": float(raw_turnover),
            "turnover": float(turnover),
            "tx_cost": float(tx_cost),
            "fee_model_label": fee_model_label(cfg_rb),
            "risk_on": bool(ranked["risk_on"].dropna().iloc[0]) if "risk_on" in ranked.columns and ranked["risk_on"].notna().any() else False,
            "target_exposure_before_trade_controls": float(target_exposure_before_controls),
            "target_exposure_after_buy_hold": float(target_weights.sum()) if not target_weights.empty else 0.0,
            "exposure_after_trade_controls": float(weights.sum()) if not weights.empty else 0.0,
            "exposure_after_tail_prune": float(weights.sum()) if not weights.empty else 0.0,
            "exposure_after_min_trade": float(weights.sum()) if not weights.empty else 0.0,
            "exposure_gap_vs_risk_floor": float(max(0.0, float(getattr(cfg_rb, "risk_on_exposure_floor", 0.0)) - diag["portfolio_exposure"])),
            "n_orders": float(fee_diag["n_orders"]),
            "commission_cost": float(fee_diag["commission_cost"]),
            "slippage_cost": float(fee_diag["slippage_cost"]),
            "regulatory_fee_cost": float(fee_diag["regulatory_fee_cost"]),
            "tx_cost_dollars": float(fee_diag["tx_cost_dollars"]),
            "commission_dollars": float(fee_diag["commission_dollars"]),
            "slippage_dollars": float(fee_diag["slippage_dollars"]),
            "regulatory_fees_dollars": float(fee_diag["regulatory_fees_dollars"]),
            "fee_price_fallback_orders": float(fee_diag["fee_price_fallback_orders"]),
            "backtest_equity_before_rebalance": equity_before_rebalance,
            "backtest_equity_after_period": float(backtest_equity),
            "portfolio_exposure": diag["portfolio_exposure"],
            "portfolio_beta": diag["portfolio_beta"],
            "max_position_weight": diag["max_position_weight"],
            "max_issuer_weight": diag["max_issuer_weight"],
            "max_sector_weight": diag["max_sector_weight"],
            "max_correlation_cluster_weight": diag["max_correlation_cluster_weight"],
            "n_positions": diag["n_positions"],
            "constraint_violations": diag["constraint_violations"],
            "final_validated_exposure": diag["portfolio_exposure"],
        }
        for _bridge_key in bridge_keys:
            if _bridge_key in ranked.columns and ranked[_bridge_key].notna().any():
                dec_extra[_bridge_key] = ranked[_bridge_key].dropna().iloc[0]
        dec_extra.update({_tail_key: float(_tail_value) for _tail_key, _tail_value in tail_diag.items()})
        for _fee_key in fee_keys:
            dec_extra[_fee_key] = float(fee_diag.get(_fee_key, 0.0))
        dec_extra.update({_bind_key: float(_bind_value) for _bind_key, _bind_value in constraint_binding_metrics(weights, ranked, cfg_rb).items()})
        dec_extra.update(classify_cash_reason(dec_extra))
        dec_extra.update({_hygiene_key: float(_hygiene_value) for _hygiene_key, _hygiene_value in final_hygiene_diag.items()})
        tick("decision_meta", t)

        t = monotonic()
        head = ranked.iloc[: min(decision_head_n, len(ranked))]
        weight_map = weights.to_dict()
        for row_dict in head.to_dict(orient="records"):
            rec = dict(dec_extra)
            rec.update(row_dict)
            tk = rec.get("ticker")
            rec["target_weight"] = float(weight_map.get(tk, 0.0))
            decision_rows.append(rec)
        tick("decision_rows_expand", t)

        t = monotonic()
        if not weights.empty:
            rb_str = pd.Timestamp(rb)
            for tk, wt in weights.items():
                weight_rows.append({"ticker": str(tk), "weight": float(wt), "rebalance_date": rb_str})
        prev_weights = weights.copy(deep=False)
        tick("weights_and_prev", t)

    loop_sec = monotonic() - loop_t0

    t = monotonic()
    decisions_df = pd.DataFrame(decision_rows) if decision_rows else pd.DataFrame()
    decisions_df = deduplicate_dataframe_columns(decisions_df) if not decisions_df.empty else decisions_df
    weights_df = pd.DataFrame(weight_rows) if weight_rows else pd.DataFrame()
    _ = pd.Series(daily_values, index=pd.DatetimeIndex(daily_dates), name="strategy_return").sort_index()
    tick("finalize_dataframes", t)

    counts["rebalances_processed"] = n_rebalances
    counts["decision_rows"] = len(decision_rows)
    counts["weight_rows"] = len(weight_rows)
    total = sum(timings.values())
    return total, dict(timings), dict(counts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Profile Phase B walk-forward path simulation.")
    parser.add_argument("--out-dir", default=str(ROOT / "model_output_sp500_pit_t212"))
    args = parser.parse_args()
    out_dir = Path(args.out_dir)
    cfg = _default_cfg(out_dir)

    print(f"Loading caches from {out_dir} …")
    features, returns, prediction_cache, n_tickers = _load_data(out_dir, cfg)
    print(f"Features: {len(features):,} rows, {n_tickers} tickers | Returns: {returns.shape} | Cache rebalances: {len(prediction_cache)}")

    total, timings, counts = profile_phase_b(features, returns, prediction_cache, cfg)
    ranked = sorted(timings.items(), key=lambda kv: kv[1], reverse=True)
    n_rb = max(counts.get("rebalances_processed", 1), 1)

    print("\n=== Phase B Profil (Sekunden) ===")
    print(f"Rebalances verarbeitet: {n_rb}")
    print(f"Decision-Zeilen: {counts.get('decision_rows', 0):,} | Weight-Zeilen: {counts.get('weight_rows', 0):,}")
    print(f"Gemessene Summe: {total:.2f}s\n")
    for name, sec in ranked:
        pct = 100.0 * sec / total if total > 0 else 0.0
        per_rb = sec / n_rb
        print(f"  {name:28s} {sec:8.2f}s  ({pct:5.1f}%)  {per_rb * 1000:6.1f} ms/reb")

    other = total - sum(timings.values())
    if abs(other) > 0.01:
        print(f"  {'(loop overhead)':28s} {other:8.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
