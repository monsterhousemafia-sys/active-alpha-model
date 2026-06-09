from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Dict, List, Optional, Tuple

import hashlib
import json
import math
import pickle
import numpy as np
import pandas as pd

from aa_backtest_ml import precompute_backtest_predictions, resolve_forwarded_ml_prediction
from aa_config import BacktestConfig
from aa_constants import FEATURE_COLUMNS, deduplicate_dataframe_columns
from aa_dashboard import RunDashboard
from aa_execution import (
    PhaseTimings,
    apply_buy_hold_spread,
    apply_min_trade_value_filter,
    estimate_backtest_rebalance_costs,
    fee_model_label,
    final_position_hygiene_metrics,
    enforce_hard_position_count,
)
from aa_features import build_feature_by_date
from aa_integrity import IntegrityResult, validate_backtest_calendar_integrity
from aa_models import fit_predict
from aa_parallel import (
    ProcessPoolSession,
    _CTX,
    _estimate_dataframe_gb,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
from aa_portfolio import (
    _momentum_score,
    _momentum_variant_label,
    _neutralized_momentum_candidates,
    allocate_with_caps,
    apply_cash_filler,
    apply_tail_pruning,
    apply_trade_controls,
    classify_cash_reason,
    compute_risk_off_eligibility,
    compute_risk_off_forced_exit_tickers,
    compute_target_exposure,
    constraint_binding_metrics,
    determine_risk_on,
    effective_beta_cap_from_snapshot,
    parse_naive_momentum_variants,
    portfolio_diagnostics,
    project_to_valid_by_blending,
    select_portfolio,
    trim_to_beta_cap,
    trim_to_exposure_cap,
    trim_to_group_caps,
    validate_weights,
    write_constraint_binding_history,
)
from aa_benchmark_returns import load_verified_benchmark_returns
from aa_reporting import calculate_metrics, compute_benchmark_comparison, compute_custom_benchmark_returns


@dataclass
class BaselineRunResult:
    variant: str
    daily_returns: pd.Series
    decisions: pd.DataFrame
    weights: pd.DataFrame
    constraint_history: pd.DataFrame
    execution_costs: pd.DataFrame
    position_contributions: pd.DataFrame


def _naive_artifact_slug(variant: str) -> str:
    v = str(variant).lower().strip()
    if v == "mom_blend_matched_controls":
        return "mom_blend_matched_controls"
    if v.endswith("_top12"):
        v = v[: -len("_top12")]
    return f"naive_{v}"


def parse_naive_detailed_variants(cfg: BacktestConfig) -> List[str]:
    raw = str(getattr(cfg, "naive_detailed_variants", "") or "")
    variants = [x.strip().lower() for x in raw.split(",") if x.strip()]
    out: List[str] = []
    for v in variants:
        if v not in out:
            out.append(v)
    return out


def _build_naive_matched_controls_portfolio(
    snap: pd.DataFrame,
    cfg: BacktestConfig,
    momentum_variant: str,
) -> Tuple[pd.Series, pd.DataFrame]:
    """Momentum selection with ensemble-matched exposure, beta cap, and cash filler."""
    snap = snap.copy()
    mom = _momentum_score(snap, momentum_variant)
    snap["mu_hat"] = mom
    snap["alpha_lcb"] = mom
    mtrend = float(snap["market_trend_200"].dropna().iloc[0]) if "market_trend_200" in snap and snap["market_trend_200"].notna().any() else 0.0
    mret63 = float(snap["market_ret_63"].dropna().iloc[0]) if "market_ret_63" in snap and snap["market_ret_63"].notna().any() else -1.0
    risk_on = determine_risk_on(mtrend, mret63, cfg)
    snap["eligible"] = compute_risk_off_eligibility(snap, cfg, risk_on)
    exposure, exposure_diag = compute_target_exposure(snap, risk_on, cfg)
    effective_beta_cap = effective_beta_cap_from_snapshot(snap, risk_on, cfg, exposure_diag)
    cfg_eff = replace(cfg, max_portfolio_beta=effective_beta_cap)
    cross = snap.loc[snap["eligible"].fillna(False).astype(bool)].copy()
    if cross.empty or exposure <= 0:
        snap["risk_on"] = risk_on
        snap["target_exposure"] = exposure
        return pd.Series(dtype=float), snap
    cross["selection_score"] = _momentum_score(cross, momentum_variant)
    cross.sort_values("selection_score", ascending=False, inplace=True)
    min_names_needed = int(math.ceil(exposure / max(cfg.max_position, 1e-9)))
    n_select = max(cfg.top_k, min_names_needed)
    pool = cross.head(max(n_select * 2, cfg.top_k + 10)).copy()
    candidates = pool.head(n_select).copy()
    shifted = candidates["selection_score"] - candidates["selection_score"].min() + 1e-4
    vol_adj = np.sqrt(candidates.set_index("ticker")["vol_20"].clip(lower=0.05)) if "vol_20" in candidates.columns else pd.Series(1.0, index=candidates["ticker"])
    raw = pd.Series(shifted.values, index=candidates["ticker"]) / vol_adj
    weights = allocate_with_caps(candidates, raw, cfg_eff, exposure)
    weights, _cash_diag = apply_cash_filler(weights, cross, cfg_eff, exposure, risk_on=risk_on)
    try:
        validate_weights(weights, cross, cfg_eff, context="naive_matched_controls")
    except ValueError:
        weights = trim_to_exposure_cap(weights, cfg_eff)
        weights = trim_to_group_caps(weights, cross, cfg_eff)
        weights = trim_to_beta_cap(weights, cross, cfg_eff)
    snap["risk_on"] = risk_on
    snap["target_exposure"] = exposure
    for _k, _v in exposure_diag.items():
        snap[_k] = _v
    snap["selection_score"] = snap["ticker"].map(cross.set_index("ticker")["selection_score"]).fillna(0.0)
    snap["target_weight"] = snap["ticker"].map(weights).fillna(0.0)
    return weights, snap.sort_values("selection_score", ascending=False)


def _prep_naive_rebalance_weights(
    snap: Optional[pd.DataFrame],
    cfg: BacktestConfig,
    *,
    variant: str,
    momentum_variant: str,
    matched_controls: bool,
    returns_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """Per-rebalance weight selection (parallelizable — no prev_weights dependency)."""
    if snap is None or snap.empty:
        return None
    snap = snap.copy()
    mtrend = float(snap["market_trend_200"].dropna().iloc[0]) if "market_trend_200" in snap and snap["market_trend_200"].notna().any() else 0.0
    mret63 = float(snap["market_ret_63"].dropna().iloc[0]) if "market_ret_63" in snap and snap["market_ret_63"].notna().any() else -1.0
    risk_on = determine_risk_on(mtrend, mret63, cfg)

    if matched_controls:
        target_weights, ranked = _build_naive_matched_controls_portfolio(snap, cfg, momentum_variant)
        cfg_rb = cfg
        if "effective_max_portfolio_beta" in ranked.columns and ranked["effective_max_portfolio_beta"].notna().any():
            cfg_rb = replace(cfg, max_portfolio_beta=float(pd.to_numeric(ranked["effective_max_portfolio_beta"], errors="coerce").dropna().iloc[0]))
    else:
        exposure = cfg.good_regime_exposure if risk_on else cfg.bad_regime_exposure
        if risk_on:
            exposure = max(exposure, cfg.risk_on_exposure_floor)
        exposure = min(max(exposure, 0.0), float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0))
        if "in_universe" not in snap.columns:
            snap["in_universe"] = True
        eligible = (
            snap["in_universe"].fillna(False).astype(bool)
            & (pd.to_numeric(snap.get("adv_20", 0.0), errors="coerce").fillna(0.0) >= cfg.min_adv)
            & (pd.to_numeric(snap.get("vol_20", 99.0), errors="coerce").fillna(99.0) <= cfg.max_ann_vol)
        )
        mv = str(momentum_variant).lower().strip()
        if returns_only and (mv == "mom_1" or mv.startswith("mom_1_")):
            snap["momentum_baseline_score"] = pd.to_numeric(snap.get("mom_1", 0.0), errors="coerce").fillna(0.0)
        else:
            snap["momentum_baseline_score"] = _momentum_score(snap, momentum_variant)
        eligible &= pd.to_numeric(snap["momentum_baseline_score"], errors="coerce").notna()
        ranked = snap.loc[eligible].sort_values(["momentum_baseline_score", "mom_252_21"], ascending=[False, False])
        ranked["risk_on"] = risk_on
        ranked["selection_score"] = ranked["momentum_baseline_score"]
        if ranked.empty:
            ranked = snap.copy()
            ranked["risk_on"] = risk_on
            ranked["selection_score"] = pd.to_numeric(snap.get("momentum_baseline_score", 0.0), errors="coerce").fillna(0.0)
        if ranked.empty or exposure <= 0:
            target_weights = pd.Series(dtype=float)
        else:
            if "neutral" in str(momentum_variant).lower():
                candidate_names = _neutralized_momentum_candidates(ranked, cfg, momentum_variant)
            else:
                candidate_names = ranked.head(max(int(cfg.top_k) * 3, int(cfg.top_k) + 5))["ticker"].tolist()
            raw = ranked.set_index("ticker")["momentum_baseline_score"].astype(float).reindex(candidate_names).dropna()
            raw = (raw - raw.min()).clip(lower=0.0) + 1e-6
            target_weights = allocate_with_caps(ranked, raw, cfg, exposure)
        cfg_rb = cfg

    target_exposure_before = float(target_weights.sum()) if not target_weights.empty else 0.0
    return {
        "snap": snap,
        "risk_on": risk_on,
        "target_weights": target_weights,
        "ranked": ranked,
        "cfg_rb": cfg_rb,
        "target_exposure_before": target_exposure_before,
    }


_NAIVE_PREP_SHARED: Dict[str, Any] = {}


def _init_naive_prep_worker(
    feature_by_date: Dict[pd.Timestamp, pd.DataFrame],
    cfg: BacktestConfig,
    variant: str,
    momentum_variant: str,
    matched_controls: bool,
    rebalance_dates: List[pd.Timestamp],
) -> None:
    _parallel_worker_bootstrap()
    _NAIVE_PREP_SHARED.clear()
    _NAIVE_PREP_SHARED.update(
        {
            "feature_by_date": feature_by_date,
            "cfg": cfg,
            "variant": variant,
            "momentum_variant": momentum_variant,
            "matched_controls": matched_controls,
            "rebalance_dates": rebalance_dates,
        }
    )


def _naive_prep_worker_task(n: int) -> Tuple[int, Optional[Dict[str, Any]]]:
    ctx = _NAIVE_PREP_SHARED
    rb = ctx["rebalance_dates"][n]
    prep = _prep_naive_rebalance_weights(
        ctx["feature_by_date"].get(rb),
        ctx["cfg"],
        variant=ctx["variant"],
        momentum_variant=ctx["momentum_variant"],
        matched_controls=ctx["matched_controls"],
        returns_only=bool(getattr(ctx["cfg"], "naive_benchmark_returns_only", False)),
    )
    return n, prep


def _write_naive_benchmark_progress(
    progress_path: Optional[str],
    *,
    variant: str,
    phase: str,
    progress_pct: Optional[int] = None,
    rebalance_done: Optional[int] = None,
    rebalance_dates_total: Optional[int] = None,
    prep_done: Optional[int] = None,
    prep_total: Optional[int] = None,
    last_rebalance_date: Optional[str] = None,
    status: str = "running",
) -> None:
    if not progress_path:
        return
    try:
        from aa_safe_io import atomic_write_json

        doc: Dict[str, Any] = {
            "status": status,
            "variant": variant,
            "phase": phase,
            "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        if progress_pct is not None:
            doc["progress_pct"] = int(progress_pct)
        if rebalance_done is not None:
            doc["rebalance_done"] = int(rebalance_done)
        if rebalance_dates_total is not None:
            doc["rebalance_dates_total"] = int(rebalance_dates_total)
        if prep_done is not None:
            doc["prep_done"] = int(prep_done)
        if prep_total is not None:
            doc["prep_total"] = int(prep_total)
        if last_rebalance_date:
            doc["last_rebalance_date"] = last_rebalance_date
        atomic_write_json(Path(progress_path), doc)
    except Exception:
        pass


def _parallel_prep_naive_rebalances(
    rebalance_dates: List[pd.Timestamp],
    feature_by_date: Dict[pd.Timestamp, pd.DataFrame],
    cfg: BacktestConfig,
    *,
    variant: str,
    momentum_variant: str,
    matched_controls: bool,
    workers: int,
    backend: str = "process",
    feature_table_gb: float = 0.0,
    progress_path: Optional[str] = None,
) -> Dict[int, Optional[Dict[str, Any]]]:
    n_periods = max(len(rebalance_dates) - 1, 0)
    if workers <= 1 or n_periods < 2:
        return {}

    backend = str(backend or "process").lower().strip() or "process"
    tasks = list(range(n_periods))
    _write_naive_benchmark_progress(
        progress_path,
        variant=variant,
        phase="prep",
        progress_pct=0,
        prep_done=0,
        prep_total=n_periods,
        rebalance_dates_total=n_periods,
    )
    if backend == "thread":
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _thread_task(n: int) -> Tuple[int, Optional[Dict[str, Any]]]:
            rb = rebalance_dates[n]
            prep = _prep_naive_rebalance_weights(
                feature_by_date.get(rb),
                cfg,
                variant=variant,
                momentum_variant=momentum_variant,
                matched_controls=matched_controls,
                returns_only=bool(getattr(cfg, "naive_benchmark_returns_only", False)),
            )
            return n, prep

        out: Dict[int, Optional[Dict[str, Any]]] = {}
        pool_workers = min(workers, n_periods)
        prep_done = 0
        with ThreadPoolExecutor(max_workers=pool_workers) as ex:
            futures = [ex.submit(_thread_task, n) for n in tasks]
            for fut in as_completed(futures):
                n, prep = fut.result()
                out[n] = prep
                prep_done += 1
                if prep_done % 50 == 0 or prep_done >= n_periods:
                    pct = int(min(49, round(50 * prep_done / max(n_periods, 1))))
                    _write_naive_benchmark_progress(
                        progress_path,
                        variant=variant,
                        phase="prep",
                        progress_pct=pct,
                        prep_done=prep_done,
                        prep_total=n_periods,
                        rebalance_dates_total=n_periods,
                    )
        return out

    results = _parallel_map_unordered(
        cfg,
        _naive_prep_worker_task,
        tasks,
        initializer=_init_naive_prep_worker,
        initargs=(feature_by_date, cfg, variant, momentum_variant, matched_controls, rebalance_dates),
        feature_table_gb=feature_table_gb,
        backend="process",
    )
    return {n: prep for n, prep in results}


def run_naive_momentum_baseline_full(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    variant: str = "mom_blend_top12",
) -> BaselineRunResult:
    """Internal no-ML control benchmark with optional full diagnostic artifacts."""
    label = _momentum_variant_label(variant)
    empty = BaselineRunResult(
        variant=variant,
        daily_returns=pd.Series(dtype=float, name=label),
        decisions=pd.DataFrame(),
        weights=pd.DataFrame(),
        constraint_history=pd.DataFrame(),
        execution_costs=pd.DataFrame(),
        position_contributions=pd.DataFrame(),
    )
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    if len(dates) < 600:
        return empty
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]
    if len(rebalance_dates) < 20:
        return empty

    feature_by_date = {pd.Timestamp(k): v for k, v in features.groupby("date")}
    prev_weights = pd.Series(dtype=float)
    equity = float(cfg.backtest_capital) if float(getattr(cfg, "backtest_capital", 0.0)) > 0 else 100000.0
    daily_dates: List[pd.Timestamp] = []
    daily_values: List[float] = []
    decision_rows: List[Dict[str, Any]] = []
    weight_rows: List[Dict[str, Any]] = []
    constraint_rows: List[Dict[str, Any]] = []
    execution_rows: List[Dict[str, Any]] = []
    contribution_rows: List[Dict[str, Any]] = []
    matched_controls = str(variant).lower().strip() == "mom_blend_matched_controls"
    momentum_variant = "mom_blend_top12" if matched_controls else variant

    if dashboard is not None:
        dashboard.start_phase(f"Naive Momentum Baseline: {variant}", total=max(len(rebalance_dates) - 1, 1), step="interne Momentum-Kontrolle")

    ret_index = returns.index
    ret_np = returns.to_numpy(dtype=np.float32, copy=False)
    col_to_j = {str(c): j for j, c in enumerate(returns.columns)}
    period_bounds_list = _rebalance_period_bounds(rebalance_dates, ret_index)
    use_gpu_returns = bool(getattr(cfg, "naive_gpu_returns", False))
    ret_gpu = None
    if use_gpu_returns:
        try:
            from aa_gpu_returns import as_gpu_returns, gpu_returns_available

            if gpu_returns_available():
                ret_gpu = as_gpu_returns(ret_np)
        except Exception:
            ret_gpu = None
    returns_only = bool(getattr(cfg, "naive_benchmark_returns_only", False))
    prep_backend = str(getattr(cfg, "naive_prep_backend", "process") or "process").lower().strip() or "process"
    feature_gb = _estimate_dataframe_gb(features)
    prep_workers = resolve_parallel_workers(cfg, feature_table_gb=feature_gb, backend=prep_backend)
    prep_cap = getattr(cfg, "naive_prep_max_workers", None)
    if prep_cap is not None:
        try:
            prep_workers = min(prep_workers, max(1, int(prep_cap)))
        except (TypeError, ValueError):
            pass
    use_parallel_prep = bool(getattr(cfg, "naive_parallel_prep", True)) and prep_workers > 1
    progress_path = getattr(cfg, "naive_progress_path", None)
    total_steps = max(len(rebalance_dates) - 1, 1)
    prep_by_n = (
        _parallel_prep_naive_rebalances(
            rebalance_dates,
            feature_by_date,
            cfg,
            variant=variant,
            momentum_variant=momentum_variant,
            matched_controls=matched_controls,
            workers=prep_workers,
            backend=prep_backend,
            feature_table_gb=feature_gb,
            progress_path=str(progress_path) if progress_path else None,
        )
        if use_parallel_prep
        else {}
    )
    if use_parallel_prep and prep_by_n:
        _write_naive_benchmark_progress(
            str(progress_path) if progress_path else None,
            variant=variant,
            phase="returns",
            progress_pct=50,
            prep_done=len(prep_by_n),
            prep_total=max(len(rebalance_dates) - 1, 1),
            rebalance_dates_total=total_steps,
            rebalance_done=0,
        )
    if returns_only:
        try:
            from analytics.h1_federation_dispatch import load_distributed_naive_prep

            out_p = Path(str(getattr(cfg, "out_dir", "") or "."))
            project_root = out_p.parent.parent if out_p.parent.name == "validation_runs" else out_p.parent
            distributed = load_distributed_naive_prep(project_root)
            if distributed:
                merged: Dict[int, Optional[Dict[str, Any]]] = dict(prep_by_n)
                for n, raw in distributed.items():
                    ni = int(n)
                    if ni < 0 or ni >= len(rebalance_dates) - 1:
                        continue
                    tw = pd.Series(raw.get("target_weights") or {}, dtype=float)
                    ranked = pd.DataFrame(raw.get("ranked_records") or [])
                    merged[ni] = {
                        "snap": feature_by_date.get(rebalance_dates[ni]),
                        "risk_on": bool(raw.get("risk_on")),
                        "target_weights": tw,
                        "ranked": ranked,
                        "cfg_rb": cfg,
                        "target_exposure_before": float(raw.get("target_exposure_before") or 0.0),
                    }
                prep_by_n = merged
                use_parallel_prep = len(prep_by_n) > 0
        except Exception:
            pass
    for n, rb in enumerate(rebalance_dates[:-1]):
        prep = prep_by_n.get(n) if use_parallel_prep else None
        if prep is not None:
            snap = prep["snap"]
            risk_on = prep["risk_on"]
            target_weights = prep["target_weights"]
            ranked = prep["ranked"]
            cfg_rb = prep["cfg_rb"]
            target_exposure_before = prep["target_exposure_before"]
        else:
            snap = feature_by_date.get(rb)
            inline = _prep_naive_rebalance_weights(
                snap,
                cfg,
                variant=variant,
                momentum_variant=momentum_variant,
                matched_controls=matched_controls,
                returns_only=returns_only,
            )
            if inline is None:
                continue
            snap = inline["snap"]
            risk_on = inline["risk_on"]
            target_weights = inline["target_weights"]
            ranked = inline["ranked"]
            cfg_rb = inline["cfg_rb"]
            target_exposure_before = inline["target_exposure_before"]

        forced_exit = compute_risk_off_forced_exit_tickers(snap, prev_weights, cfg_rb, risk_on=risk_on)
        target_weights = apply_buy_hold_spread(target_weights, prev_weights, ranked, cfg_rb, forced_exit_tickers=forced_exit)
        weights = apply_trade_controls(target_weights, prev_weights, ranked, cfg_rb)
        weights, _tail_diag = apply_tail_pruning(weights, prev_weights, ranked, cfg_rb)
        weights = apply_min_trade_value_filter(weights, prev_weights, equity, cfg_rb)
        if not returns_only:
            try:
                validate_weights(weights, ranked, cfg_rb, context=f"naive_momentum_baseline_{variant}")
            except ValueError:
                weights = project_to_valid_by_blending(weights, pd.Series(dtype=float), ranked, cfg_rb, context=f"naive_momentum_projection_{variant}")

        i0, i1 = period_bounds_list[n]
        if i1 <= i0:
            continue
        idx = target_weights.index.union(prev_weights.index)
        delta_v = weights.reindex(idx).fillna(0.0) - prev_weights.reindex(idx).fillna(0.0)
        fee_diag = estimate_backtest_rebalance_costs(pd.Series(delta_v, index=idx), snap, equity, cfg_rb)
        tx_cost = float(fee_diag["tx_cost"])
        equity_before = float(equity)
        if ret_gpu is not None:
            from aa_gpu_returns import accumulate_period_returns_gpu

            period_dates, period_returns, growth = accumulate_period_returns_gpu(
                weights,
                ret_gpu=ret_gpu,
                ret_index=ret_index,
                col_to_j=col_to_j,
                period_bounds=(i0, i1),
                tx_cost=tx_cost,
            )
            period_dates = [pd.Timestamp(d) for d in period_dates]
        else:
            period_dates, period_returns, growth = _accumulate_vectorized_period_returns(
                weights, returns, pd.Index([]), tx_cost, ret_np=ret_np, ret_index=ret_index, col_to_j=col_to_j, period_bounds=(i0, i1),
            )
        if (
            not returns_only
            and bool(getattr(cfg, "naive_position_contributions", False))
            and weights is not None
            and not weights.empty
            and i1 > i0
        ):
            active = [(str(t), float(weights.get(t, 0.0))) for t in weights.index if float(weights.get(t, 0.0)) != 0.0 and str(t) in col_to_j]
            if active:
                j_idx = [col_to_j[t] for t, _ in active]
                w_vec = np.asarray([w for _, w in active], dtype=np.float32)
                R = ret_np[i0:i1, j_idx]
                contrib = R * w_vec.reshape(1, -1)
                for day_i, dt in enumerate(period_dates):
                    row_ret = float(period_returns[day_i]) if day_i < len(period_returns) else 0.0
                    for (tk, wt), c in zip(active, contrib[day_i]):
                        contribution_rows.append({
                            "variant": variant,
                            "date": pd.Timestamp(dt),
                            "rebalance_date": pd.Timestamp(rb),
                            "ticker": tk,
                            "weight": wt,
                            "daily_return": row_ret,
                            "position_return_contribution": float(c),
                        })
        daily_dates.extend(period_dates)
        daily_values.extend(period_returns)
        equity *= growth

        if not returns_only:
            diag = portfolio_diagnostics(weights, ranked, cfg_rb)
            bind = constraint_binding_metrics(weights, ranked, cfg_rb)
            constraint_row = {"variant": variant, "rebalance_date": pd.Timestamp(rb), "risk_on": bool(risk_on), **diag, **bind}
            constraint_rows.append(constraint_row)
            execution_rows.append(
                {
                    "variant": variant,
                    "rebalance_date": pd.Timestamp(rb),
                    "equity_before": equity_before,
                    "equity_after_period": float(equity),
                    **fee_diag,
                }
            )
            head = ranked.head(max(50, int(cfg.top_k))) if ranked is not None and not ranked.empty else pd.DataFrame()
            weight_map = weights.to_dict() if not weights.empty else {}
            dec_base = {
                "variant": variant,
                "rebalance_date": pd.Timestamp(rb),
                "risk_on": bool(risk_on),
                "target_exposure_before_controls": target_exposure_before,
            }
            dec_base.update(diag)
            for row_dict in head.to_dict(orient="records") if not head.empty else []:
                rec = dict(dec_base)
                rec.update(row_dict)
                rec["target_weight"] = float(weight_map.get(rec.get("ticker"), 0.0))
                decision_rows.append(rec)
            if not weights.empty:
                rb_ts = pd.Timestamp(rb)
                for tk, wt in weights.items():
                    weight_rows.append({"variant": variant, "ticker": str(tk), "weight": float(wt), "rebalance_date": rb_ts})
        prev_weights = weights.copy(deep=False)
        if dashboard is not None:
            dashboard.advance_phase(1, step=str(rb.date()), candidates=len(ranked) if ranked is not None else 0)
        elif progress_path and (n % 25 == 0 or n >= total_steps - 1):
            done = n + 1
            pct = int(min(99, 50 + round(50 * done / total_steps)))
            _write_naive_benchmark_progress(
                str(progress_path),
                variant=variant,
                phase="returns",
                progress_pct=pct,
                rebalance_done=done,
                rebalance_dates_total=total_steps,
                last_rebalance_date=str(rb.date()),
            )

    if dashboard is not None:
        dashboard.finish_phase()
    elif progress_path:
        try:
            from aa_safe_io import atomic_write_json

            atomic_write_json(
                Path(progress_path),
                {
                    "status": "complete",
                    "variant": variant,
                    "rebalance_done": total_steps,
                    "rebalance_dates_total": total_steps,
                    "progress_pct": 100,
                    "updated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                },
            )
        except Exception:
            pass
    daily = pd.Series(daily_values, index=pd.DatetimeIndex(daily_dates), name=label).sort_index()
    return BaselineRunResult(
        variant=variant,
        daily_returns=daily,
        decisions=pd.DataFrame(decision_rows) if decision_rows else pd.DataFrame(),
        weights=pd.DataFrame(weight_rows) if weight_rows else pd.DataFrame(),
        constraint_history=pd.DataFrame(constraint_rows) if constraint_rows else pd.DataFrame(),
        execution_costs=pd.DataFrame(execution_rows) if execution_rows else pd.DataFrame(),
        position_contributions=pd.DataFrame(contribution_rows) if contribution_rows else pd.DataFrame(),
    )


def run_naive_momentum_baseline_detailed(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    variant: str = "mom_blend_top12",
) -> BaselineRunResult:
    """Full naive baseline diagnostics (weights, decisions, costs, constraints)."""
    return run_naive_momentum_baseline_full(features, returns, cfg, dashboard, variant=variant)


def run_naive_momentum_baseline(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    variant: str = "mom_blend_top12",
) -> pd.Series:
    """Backward-compatible wrapper returning only the daily return series."""
    return run_naive_momentum_baseline_full(features, returns, cfg, dashboard, variant=variant).daily_returns


def write_naive_baseline_artifacts(out_dir: Path, result: BaselineRunResult) -> List[Path]:
    """Persist detailed naive baseline CSVs for research comparisons."""
    out_dir = Path(out_dir)
    slug = _naive_artifact_slug(result.variant)
    written: List[Path] = []
    if not result.daily_returns.empty:
        p = out_dir / f"{slug}_daily_returns.csv"
        result.daily_returns.to_csv(p, header=True)
        written.append(p)
    for attr, suffix in [
        ("weights", "weights"),
        ("decisions", "decisions"),
        ("constraint_history", "constraint_history"),
        ("execution_costs", "execution_costs"),
        ("position_contributions", "position_contributions"),
    ]:
        df = getattr(result, attr)
        if df is not None and not df.empty:
            p = out_dir / f"{slug}_{suffix}.csv"
            df.to_csv(p, index=False)
            written.append(p)
    return written


def _naive_detailed_export_task(variant: str) -> Tuple[str, int]:
    if _CTX.features is None or _CTX.returns is None or _CTX.cfg is None:
        raise RuntimeError("Naive detailed worker was not initialized.")
    result = run_naive_momentum_baseline_full(_CTX.features, _CTX.returns, _CTX.cfg, None, variant=variant)
    paths = write_naive_baseline_artifacts(Path(getattr(_CTX.cfg, "out_dir", "model_output")), result)
    return variant, len(paths)


def _apply_king_h1_naive_profile_for_daily(cfg: BacktestConfig, features: pd.DataFrame) -> None:
    """Thread-Prep + RAM-Caps for tägliche Naive-Exports (H1 mom_1_top12)."""
    if int(getattr(cfg, "rebalance_every", 5) or 5) != 1:
        return
    if getattr(cfg, "naive_prep_backend", None):
        return
    try:
        from analytics.h1_king_runtime import apply_king_h1_profile

        apply_king_h1_profile(cfg, feature_gb=_estimate_dataframe_gb(features))
    except Exception:
        pass


def _naive_detailed_export_wanted(cfg: BacktestConfig) -> bool:
    return bool(getattr(cfg, "naive_detailed_reporting", False)) and bool(parse_naive_detailed_variants(cfg))


def _naive_detailed_overlap_enabled(cfg: BacktestConfig) -> bool:
    return (
        _naive_detailed_export_wanted(cfg)
        and parallel_execution_enabled(cfg)
        and not bool(getattr(cfg, "no_naive_overlap", False))
    )


def expected_naive_detailed_paths(cfg: BacktestConfig, out_dir: Path) -> List[Path]:
    """Seal-taugliche Naive-Baseline-CSVs (z. B. naive_mom_1_daily_returns.csv)."""
    if not _naive_detailed_export_wanted(cfg):
        return []
    out_dir = Path(out_dir)
    paths: List[Path] = []
    for variant in parse_naive_detailed_variants(cfg):
        slug = _naive_artifact_slug(variant)
        paths.append(out_dir / f"{slug}_daily_returns.csv")
    return paths


def verify_naive_detailed_artifacts(cfg: BacktestConfig, out_dir: Path) -> List[Path]:
    """Fail-closed: naive_detailed_reporting muss die konfigurierten Seal-CSVs liefern."""
    expected = expected_naive_detailed_paths(cfg, out_dir)
    if not expected:
        return []
    missing = [p.name for p in expected if not p.is_file() or p.stat().st_size <= 0]
    if missing:
        raise RuntimeError(
            f"naive_detailed_reporting=True but seal artifacts missing in {Path(out_dir).resolve()}: "
            f"{', '.join(missing)}. "
            "benchmark_daily_returns.csv is SPY reporting only — not the mom_1_top12 seal benchmark."
        )
    return expected


def _wait_naive_background_future(
    naive_future: Any,
    naive_executor: Any,
    *,
    dashboard: Optional[RunDashboard] = None,
    wait_label: str = "Naive-Detail-Export",
) -> None:
    wait_started = monotonic()
    if dashboard is not None:
        dashboard.set_status(
            step=f"Warte auf parallelen {wait_label}",
            rebalance="",
            date="",
            train_rows="",
            candidates="",
        )
        dashboard.ok(f"{wait_label} läuft im Hintergrund; warte auf Abschluss")
    try:
        while not naive_future.done():
            if dashboard is not None:
                dashboard.set_status(step=f"Warte auf parallelen {wait_label} ({monotonic() - wait_started:.0f}s)")
            deadline = monotonic() + 5.0
            while monotonic() < deadline and not naive_future.done():
                from aa_ui_pump import pump_ui

                pump_ui(force=True)
                sleep(0.1)
        naive_future.result()
    finally:
        naive_executor.shutdown(wait=True)


def run_naive_detailed_reporting(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    out_dir: Path,
    dashboard: Optional[RunDashboard] = None,
) -> List[Path]:
    """Run and export full naive baseline diagnostics for configured variants."""
    if not bool(getattr(cfg, "naive_detailed_reporting", False)):
        return []
    variants = parse_naive_detailed_variants(cfg)
    if not variants:
        return []
    _apply_king_h1_naive_profile_for_daily(cfg, features)
    paths: List[Path] = []
    workers = resolve_parallel_workers(cfg, feature_table_gb=_estimate_dataframe_gb(features), backend="process")
    if dashboard is not None:
        dashboard.ok(f"Naive-Detail-Export: {len(variants)} Variante(n)" + (f", {workers} Worker" if workers > 1 and len(variants) > 1 else ""))
    if workers > 1 and len(variants) > 1 and parallel_execution_enabled(cfg):
        cfg_out = replace(cfg, out_dir=str(out_dir))
        for variant, n_paths in _parallel_map_unordered(
            cfg,
            _naive_detailed_export_task,
            variants,
            initializer=_naive_baseline_initializer,
            initargs=(features, returns, cfg_out),
            feature_table_gb=_estimate_dataframe_gb(features),
        ):
            if n_paths:
                slug = _naive_artifact_slug(variant)
                paths.extend(sorted(Path(out_dir).glob(f"{slug}_*.csv")))
    else:
        for variant in variants:
            result = run_naive_momentum_baseline_full(features, returns, cfg, dashboard, variant=variant)
            paths.extend(write_naive_baseline_artifacts(out_dir, result))
    return paths


def _naive_baseline_initializer(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig) -> None:
    _parallel_worker_bootstrap()
    _CTX.features = features
    _CTX.returns = returns
    _CTX.cfg = cfg


def _naive_baseline_variant_task(variant: str) -> Tuple[str, List[str], List[float]]:
    if _CTX.features is None or _CTX.returns is None or _CTX.cfg is None:
        raise RuntimeError("Naive-baseline worker was not initialized.")
    s = run_naive_momentum_baseline(_CTX.features, _CTX.returns, _CTX.cfg, None, variant=variant)
    if s.empty:
        return variant, [], []
    idx = [str(x) for x in s.index]
    vals = [float(x) for x in s.values]
    return variant, idx, vals


def run_naive_momentum_baselines(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig, dashboard: Optional[RunDashboard] = None) -> pd.DataFrame:
    variants = parse_naive_momentum_variants(cfg)
    if not variants:
        return pd.DataFrame()
    n_workers = resolve_parallel_workers(cfg, backend="process")
    series: List[pd.Series] = []
    if dashboard is not None:
        dashboard.start_phase(
            "Naive Momentum Baselines",
            total=len(variants),
            step=f"{len(variants)} Varianten ({n_workers} Worker)" if n_workers > 1 else f"{len(variants)} Varianten",
        )
    if parallel_execution_enabled(cfg) and variants:
        # Windows spawn workers start with an empty module-level _CTX.
        # The naive task reads features/returns/cfg from _CTX, so the pool must
        # be created with the naive initializer whenever this helper creates
        # its own worker pool, including the overlapping subprocess path.
        for variant, idx, vals in _parallel_map_unordered(
            cfg,
            _naive_baseline_variant_task,
            variants,
            initializer=_naive_baseline_initializer,
            initargs=(features, returns, cfg),
            feature_table_gb=_estimate_dataframe_gb(features),
        ):
            if idx:
                series.append(pd.Series(vals, index=pd.DatetimeIndex(idx), name=_momentum_variant_label(variant)))
            if dashboard is not None:
                dashboard.advance_phase(1, step=f"Naive: {variant}")
    else:
        for variant in variants:
            s = run_naive_momentum_baseline(features, returns, cfg, dashboard, variant=variant)
            if not s.empty:
                series.append(s)
            if dashboard is not None:
                dashboard.advance_phase(1, step=f"Naive: {variant}")
    if dashboard is not None:
        dashboard.finish_phase()
    if not series:
        return pd.DataFrame()
    return pd.concat(series, axis=1).sort_index()

def _rebalance_period_bounds(
    rebalance_dates: List[pd.Timestamp],
    ret_index: pd.Index,
) -> List[Tuple[int, int]]:
    bounds: List[Tuple[int, int]] = []
    for rb, next_rb in zip(rebalance_dates[:-1], rebalance_dates[1:]):
        i0 = int(ret_index.searchsorted(pd.Timestamp(rb), side="right"))
        i1 = int(ret_index.searchsorted(pd.Timestamp(next_rb), side="right"))
        bounds.append((i0, i1))
    return bounds


def _accumulate_vectorized_period_returns(
    weights: pd.Series,
    returns: pd.DataFrame,
    ret_dates: pd.Index,
    tx_cost: float,
    *,
    ret_np: Optional[np.ndarray] = None,
    ret_index: Optional[pd.Index] = None,
    col_to_j: Optional[Dict[str, int]] = None,
    period_bounds: Optional[Tuple[int, int]] = None,
) -> Tuple[List[pd.Timestamp], List[float], float]:
    """Vectorized daily PnL for one rebalance holding period (Zen2-friendly NumPy dot)."""
    if period_bounds is not None and ret_np is not None and ret_index is not None:
        i0, i1 = period_bounds
        if i1 <= i0:
            return [], [], 1.0
        dates_out = [pd.Timestamp(ret_index[i]) for i in range(i0, i1)]
        if weights is None or weights.empty:
            return dates_out, [0.0] * len(dates_out), 1.0
        if col_to_j is None:
            col_to_j = {str(c): j for j, c in enumerate(returns.columns)}
        active = [(str(t), float(weights.get(t, 0.0))) for t in weights.index if str(t) in col_to_j and float(weights.get(t, 0.0)) != 0.0]
        if not active:
            return dates_out, [0.0] * len(dates_out), 1.0
        j_idx = [col_to_j[t] for t, _ in active]
        w_vec = np.asarray([w for _, w in active], dtype=np.float32)
        R = ret_np[i0:i1, j_idx]
        pr = (R @ w_vec).astype(float)
        if len(pr):
            pr[0] -= float(tx_cost)
        growth = float(np.prod(np.maximum(1.0 + pr, 0.0)))
        return dates_out, pr.tolist(), growth

    if len(ret_dates) == 0:
        return [], [], 1.0
    dates_out = [pd.Timestamp(d) for d in ret_dates]
    if weights is None or weights.empty:
        return dates_out, [0.0] * len(dates_out), 1.0
    cols = weights.index.intersection(returns.columns)
    if len(cols) == 0:
        return dates_out, [0.0] * len(dates_out), 1.0
    w_vec = weights.reindex(cols).fillna(0.0).astype(float).values
    R = returns.reindex(index=ret_dates, columns=cols).fillna(0.0).astype(float).values
    pr = (R @ w_vec).astype(float)
    if len(pr):
        pr[0] -= float(tx_cost)
    growth = float(np.prod(np.maximum(1.0 + pr, 0.0)))
    return dates_out, pr.tolist(), growth


PATH_SIM_CHECKPOINT_SCHEMA = 1
PATH_SIM_CHECKPOINT_INTERVAL = 25


def _path_sim_checkpoint_paths(out_dir: Path) -> Tuple[Path, Path]:
    base = Path(out_dir)
    return base / "path_sim_checkpoint.pkl", base / "path_sim_checkpoint_meta.json"


def _path_sim_checkpoint_fingerprint(cfg: BacktestConfig) -> str:
    payload = "|".join([
        str(getattr(cfg, "horizon", "")),
        str(getattr(cfg, "rebalance_every", "")),
        str(getattr(cfg, "random_seed", "")),
        str(getattr(cfg, "start", "")),
        str(getattr(cfg, "slippage_bps", "")),
        str(getattr(cfg, "fee_model", "")),
        str(getattr(cfg, "backtest_capital", "")),
        str(getattr(cfg, "returns_fast_path", False)),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _save_path_sim_checkpoint(
    out_dir: Path,
    cfg: BacktestConfig,
    *,
    last_n: int,
    prev_weights: pd.Series,
    backtest_equity: float,
    daily_dates: List[pd.Timestamp],
    daily_values: List[float],
    simulated_rebalance_dates: List[pd.Timestamp],
) -> None:
    if not bool(getattr(cfg, "path_sim_checkpoint", False)):
        return
    pkl_path, meta_path = _path_sim_checkpoint_paths(out_dir)
    pkl_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "prev_weights": prev_weights.to_dict(),
        "backtest_equity": float(backtest_equity),
        "daily_dates": [pd.Timestamp(d) for d in daily_dates],
        "daily_values": list(daily_values),
        "simulated_rebalance_dates": [pd.Timestamp(d) for d in simulated_rebalance_dates],
    }
    with pkl_path.open("wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": PATH_SIM_CHECKPOINT_SCHEMA,
                "fingerprint": _path_sim_checkpoint_fingerprint(cfg),
                "last_n": int(last_n),
                "n_daily": len(daily_values),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _try_load_path_sim_checkpoint(
    out_dir: Path,
    cfg: BacktestConfig,
    rebalance_dates: List[pd.Timestamp],
) -> Optional[Tuple[int, pd.Series, float, List[pd.Timestamp], List[float], List[pd.Timestamp]]]:
    if not bool(getattr(cfg, "path_sim_checkpoint", False)):
        return None
    pkl_path, meta_path = _path_sim_checkpoint_paths(out_dir)
    if not (pkl_path.is_file() and meta_path.is_file()):
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("schema_version") != PATH_SIM_CHECKPOINT_SCHEMA:
            return None
        if str(meta.get("fingerprint", "")) != _path_sim_checkpoint_fingerprint(cfg):
            return None
        with pkl_path.open("rb") as f:
            raw = pickle.load(f)
        last_n = int(meta.get("last_n", -1))
        if last_n < 0 or last_n >= len(rebalance_dates) - 1:
            return None
        prev_weights = pd.Series(raw.get("prev_weights") or {}, dtype=float)
        return (
            last_n,
            prev_weights,
            float(raw.get("backtest_equity", cfg.backtest_capital)),
            [pd.Timestamp(d) for d in raw.get("daily_dates") or []],
            [float(x) for x in raw.get("daily_values") or []],
            [pd.Timestamp(d) for d in raw.get("simulated_rebalance_dates") or []],
        )
    except Exception:
        return None


def _simulate_walkforward_portfolio_path(
    prediction_cache: Dict[pd.Timestamp, Dict[str, Any]],
    features: pd.DataFrame,
    returns: pd.DataFrame,
    dates: List[pd.Timestamp],
    rebalance_dates: List[pd.Timestamp],
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
) -> Tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """Path-dependent portfolio simulation (serial state); ML inputs come from prediction_cache."""
    feature_by_date = build_feature_by_date(features)
    daily_dates: List[pd.Timestamp] = []
    daily_values: List[float] = []
    decision_rows: List[Dict[str, Any]] = []
    weight_rows: List[Dict[str, Any]] = []
    simulated_rebalance_dates: List[pd.Timestamp] = []
    prev_weights = pd.Series(dtype=float)
    backtest_equity = float(cfg.backtest_capital) if float(getattr(cfg, "backtest_capital", 0.0)) > 0 else 100000.0
    use_cache = bool(prediction_cache)
    prediction_cache_norm = {pd.Timestamp(k): v for k, v in prediction_cache.items()}
    workers = resolve_parallel_workers(cfg, feature_table_gb=_estimate_dataframe_gb(features), backend="process")
    ret_index = returns.index
    ret_np = returns.to_numpy(dtype=np.float32, copy=False)
    col_to_j = {str(c): j for j, c in enumerate(returns.columns)}
    period_bounds_list = _rebalance_period_bounds(rebalance_dates, ret_index)
    decision_head_n = max(50, int(cfg.top_k))
    fast_path = bool(getattr(cfg, "returns_fast_path", False))
    out_dir = Path(getattr(cfg, "out_dir", "model_output") or "model_output")
    resume_from = 0
    bridge_keys = (
        "desired_exposure", "regime_target_exposure", "exposure_controller_score", "signal_breadth_positive", "avg_alpha_lcb", "n_positive_candidates_for_exposure", "exposure_before_constraints", "exposure_after_position_cap",
        "exposure_after_issuer_cap", "exposure_after_sector_cap", "exposure_after_cluster_cap", "exposure_after_beta_cap", "exposure_after_cash_filler", "effective_max_portfolio_beta", "beta_cap_mode_effective",
        "cash_filler_enabled", "cash_filler_added_weight", "cash_filler_n_names", "low_beta_filler_enabled", "low_beta_filler_added_weight", "low_beta_filler_n_names",
        "n_candidates", "n_eligible_candidates", "n_selected_candidates", "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol",
    )
    fee_keys = (
        "sec_fee_cost", "finra_taf_cost", "cat_fee_cost", "clearing_fee_cost", "exchange_fee_cost",
        "pass_through_fee_cost", "fx_fee_cost", "market_impact_cost", "sec_fee_dollars", "finra_taf_dollars",
        "cat_fee_dollars", "clearing_fee_dollars", "exchange_fee_dollars", "pass_through_fee_dollars",
        "fx_fee_dollars", "market_impact_dollars",
    )

    backtest_steps = max(len(rebalance_dates) - 1, 1)
    loaded = _try_load_path_sim_checkpoint(out_dir, cfg, rebalance_dates)
    if loaded is not None:
        last_n, prev_weights, backtest_equity, daily_dates, daily_values, simulated_rebalance_dates = loaded
        resume_from = last_n + 1
        msg = f"Path-Sim-Checkpoint: Fortsetzen ab Rebalance {resume_from + 1}/{backtest_steps}"
        if dashboard is not None:
            dashboard.ok(msg)
        else:
            print(msg)
    if dashboard is not None:
        if use_cache:
            dashboard.start_phase(
                "Pfad-Simulation (Phase B)",
                total=backtest_steps,
                step=f"Pfad/Kosten (vektorisiert, {workers} Kerne ML-Cache)",
            )
        else:
            dashboard.start_phase("Walk-forward Backtest", total=backtest_steps, step="ML + Pfad seriell")
    else:
        if use_cache:
            print(
                f"Walk-forward path simulation with parallel ML cache ({workers} workers), "
                f"{len(rebalance_dates)} rebalance dates ..."
            )
        else:
            print(f"Walk-forward backtest with {len(rebalance_dates)} rebalance dates ...")
    for n, rb in enumerate(rebalance_dates[:-1]):
        if n < resume_from:
            continue
        if dashboard is not None:
            from aa_cancellation import check_cancelled

            check_cancelled(f"Rebalance {n + 1}/{backtest_steps}")
        next_rb = rebalance_dates[n + 1]
        snapshot = feature_by_date.get(rb)
        loop_train_rows = 0
        loop_snapshot_rows = 0 if snapshot is None else len(snapshot)
        if use_cache:
            res = prediction_cache_norm.get(pd.Timestamp(rb), {"status": "skip", "reason": "missing_parallel_result", "train_rows": 0, "snapshot_rows": 0})
            res = resolve_forwarded_ml_prediction(res, snapshot, cfg)
            loop_train_rows = int(res.get("train_rows", 0) or 0)
            loop_snapshot_rows = int(res.get("snapshot_rows", loop_snapshot_rows) or 0)
            if dashboard is not None:
                dashboard.set_status(
                    step="Pfadsimulation mit gecachten Vorhersagen",
                    rebalance=f"{n + 1}/{backtest_steps}",
                    date=str(pd.Timestamp(rb).date()),
                    train_rows=f"{loop_train_rows:,}",
                    candidates=loop_snapshot_rows,
                )
                from aa_ui_pump import pump_ui

                pump_ui(force=False)
            if res.get("status") != "ok":
                if dashboard is not None:
                    dashboard.advance_phase(1, step=f"übersprungen: {res.get('reason', 'unknown')}", rebalance=f"{n + 1}/{backtest_steps}", date=str(pd.Timestamp(rb).date()))
                continue
            rmse = float(res.get("rmse", np.nan))
            target_weights = res["target_weights"]
            ranked = res["ranked"]
            effective_beta_cap = float(res.get("effective_beta_cap", getattr(cfg, "max_portfolio_beta", 0.0) or 0.0))
        else:
            train_end_idx = max(0, dates.index(rb) - cfg.horizon - 1)
            train_end = dates[train_end_idx]
            train_start = rb - pd.DateOffset(years=cfg.train_years)

            train_mask = (features["date"] >= train_start) & (features["date"] <= train_end)
            if "in_universe" in features.columns:
                train_mask &= features["in_universe"].fillna(False).astype(bool)
            train = features.loc[train_mask].dropna(subset=["target"])
            loop_train_rows = len(train)
            loop_snapshot_rows = 0 if snapshot is None else len(snapshot)
            if dashboard is not None:
                dashboard.set_status(
                    step="Training und Vorhersage",
                    rebalance=f"{n + 1}/{backtest_steps}",
                    date=str(rb.date()),
                    train_rows=f"{loop_train_rows:,}",
                    candidates=loop_snapshot_rows,
                )
            if snapshot is None or len(train) < cfg.min_train_rows:
                if dashboard is not None:
                    dashboard.advance_phase(1, step="übersprungen: zu wenige Trainingsdaten", rebalance=f"{n + 1}/{backtest_steps}", date=str(rb.date()))
                continue
            pred, rmse = fit_predict(train, snapshot, FEATURE_COLUMNS, cfg)
            if dashboard is not None:
                from aa_ui_pump import pump_ui

                pump_ui(force=True)
            target_weights, ranked = select_portfolio(pred, rmse, cfg)
            ranked = deduplicate_dataframe_columns(ranked)
            effective_beta_cap = float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0)
            if "effective_max_portfolio_beta" in ranked.columns and ranked["effective_max_portfolio_beta"].notna().any():
                effective_beta_cap = float(pd.to_numeric(ranked["effective_max_portfolio_beta"], errors="coerce").dropna().iloc[0])
        cfg_rb = replace(cfg, max_portfolio_beta=effective_beta_cap)
        risk_on_flag = bool(ranked["risk_on"].dropna().iloc[0]) if "risk_on" in ranked.columns and ranked["risk_on"].notna().any() else False
        forced_exit = compute_risk_off_forced_exit_tickers(ranked, prev_weights, cfg_rb, risk_on=risk_on_flag)
        if not fast_path:
            selected_target_exposure_pre = float(target_weights.sum()) if not target_weights.empty else 0.0
            pre_diag = portfolio_diagnostics(target_weights, ranked, cfg_rb)
            selected_target_beta_pre = float(pre_diag.get("portfolio_beta", float("nan")))
            target_exposure_before_controls = selected_target_exposure_pre
            pre_buy_hold_weights = target_weights.copy(deep=False)
        target_weights = apply_buy_hold_spread(target_weights, prev_weights, ranked, cfg_rb, forced_exit_tickers=forced_exit)
        if not fast_path:
            target_exposure_after_buy_hold = float(target_weights.sum()) if not target_weights.empty else 0.0

        weights = apply_trade_controls(target_weights, prev_weights, ranked, cfg_rb)
        if not fast_path:
            exposure_after_trade_controls = float(weights.sum()) if not weights.empty else 0.0
        weights, tail_diag = apply_tail_pruning(weights, prev_weights, ranked, cfg_rb)
        if not fast_path:
            exposure_after_tail_prune = float(weights.sum()) if not weights.empty else 0.0
        weights = apply_min_trade_value_filter(weights, prev_weights, backtest_equity, cfg_rb)
        weights = enforce_hard_position_count(weights, ranked, cfg_rb)
        if not fast_path:
            exposure_after_min_trade = float(weights.sum()) if not weights.empty else 0.0
        try:
            validate_weights(weights, ranked, cfg_rb, context="post_min_trade_value")
        except ValueError:
            weights = project_to_valid_by_blending(weights, target_weights, ranked, cfg_rb, context="post_min_trade_value_projection")
            weights = enforce_hard_position_count(weights, ranked, cfg_rb)
            weights = trim_to_exposure_cap(weights, cfg_rb)
            weights = trim_to_group_caps(weights, ranked, cfg_rb)
            weights = trim_to_beta_cap(weights, ranked, cfg_rb)
            validate_weights(weights, ranked, cfg_rb, context="post_min_trade_value_strict_final")
        if not fast_path:
            diag = portfolio_diagnostics(weights, ranked, cfg_rb)
            final_hygiene_diag = final_position_hygiene_metrics(weights, cfg_rb)

        i0, i1 = period_bounds_list[n]
        if i1 <= i0:
            continue

        idx = target_weights.index.union(prev_weights.index)
        tw_v = target_weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        pw_v = prev_weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        w_v = weights.reindex(idx).fillna(0.0).to_numpy(dtype=float)
        delta_v = w_v - pw_v
        delta_weights = pd.Series(delta_v, index=idx)
        fee_diag = estimate_backtest_rebalance_costs(delta_weights, snapshot, backtest_equity, cfg_rb)
        tx_cost = float(fee_diag["tx_cost"])
        equity_before_rebalance = float(backtest_equity)

        period_dates, period_returns, growth = _accumulate_vectorized_period_returns(
            weights,
            returns,
            pd.Index([]),
            tx_cost,
            ret_np=ret_np,
            ret_index=ret_index,
            col_to_j=col_to_j,
            period_bounds=(i0, i1),
        )
        daily_dates.extend(period_dates)
        daily_values.extend(period_returns)
        backtest_equity *= growth

        if not fast_path:
            raw_turnover = float(np.abs(tw_v - pw_v).sum())
            turnover = float(np.abs(delta_v).sum())
            dec_extra: Dict[str, Any] = {
                "rebalance_date": rb,
                "rmse": rmse,
                "raw_turnover": float(raw_turnover),
                "turnover": float(turnover),
                "tx_cost": float(tx_cost),
                "fee_model_label": fee_model_label(cfg_rb),
                "risk_on": risk_on_flag,
                "selection_mode": str(getattr(cfg_rb, "risk_off_selection_mode", "legacy") or "legacy"),
                "gate_mode": str(getattr(cfg_rb, "risk_off_gate_mode", "legacy") or "legacy"),
                "effective_beta_cap": float(effective_beta_cap),
                "target_exposure_before_trade_controls": float(target_exposure_before_controls),
                "target_exposure_after_buy_hold": float(target_exposure_after_buy_hold),
                "exposure_after_trade_controls": float(exposure_after_trade_controls),
                "exposure_after_tail_prune": float(exposure_after_tail_prune),
                "exposure_after_min_trade": float(exposure_after_min_trade),
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
                "selected_target_exposure_pre_execution": float(selected_target_exposure_pre),
                "selected_target_beta_pre_execution": float(selected_target_beta_pre) if np.isfinite(selected_target_beta_pre) else np.nan,
                "final_portfolio_exposure": diag["portfolio_exposure"],
                "final_portfolio_beta": diag["portfolio_beta"],
                "final_cash_weight": max(0.0, 1.0 - float(diag.get("portfolio_exposure", 0.0) or 0.0)),
                "final_validated_exposure": diag["portfolio_exposure"],
                "final_constraint_violations": diag["constraint_violations"],
                "final_n_positions": diag["n_positions"],
                "portfolio_exposure": diag["portfolio_exposure"],
                "portfolio_beta": diag["portfolio_beta"],
                "max_position_weight": diag["max_position_weight"],
                "max_issuer_weight": diag["max_issuer_weight"],
                "max_sector_weight": diag["max_sector_weight"],
                "max_correlation_cluster_weight": diag["max_correlation_cluster_weight"],
                "n_positions": diag["n_positions"],
                "constraint_violations": diag["constraint_violations"],
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
            from aa_risk_off import compute_forced_exit_diagnostics

            dec_extra.update(
                compute_forced_exit_diagnostics(
                    forced_exit,
                    prev_weights,
                    pre_buy_hold_weights,
                    target_weights,
                    weights,
                    {**fee_diag, "turnover": turnover},
                )
            )

            head = ranked.iloc[: min(decision_head_n, len(ranked))]
            weight_map = weights.to_dict()
            for row_dict in head.to_dict(orient="records"):
                rec = dict(row_dict)
                rec.update(dec_extra)
                tk = rec.get("ticker")
                rec["target_weight"] = float(weight_map.get(tk, 0.0))
                rec["forced_exit_candidate"] = bool(str(tk) in forced_exit)
                rec["rescued_by_momentum"] = bool(rec.get("rescued_by_momentum", False))
                decision_rows.append(rec)

            if not weights.empty:
                rb_str = pd.Timestamp(rb)
                for tk, wt in weights.items():
                    weight_rows.append({
                        "ticker": str(tk),
                        "weight": float(wt),
                        "rebalance_date": rb_str,
                        "risk_on": bool(dec_extra.get("risk_on", False)),
                        "portfolio_exposure": float(diag.get("portfolio_exposure", 0.0)),
                        "portfolio_beta": float(diag.get("portfolio_beta", 0.0)),
                        "final_portfolio_exposure": float(diag.get("portfolio_exposure", 0.0)),
                        "final_portfolio_beta": float(diag.get("portfolio_beta", 0.0)),
                        "final_cash_weight": max(0.0, 1.0 - float(diag.get("portfolio_exposure", 0.0) or 0.0)),
                    })

        simulated_rebalance_dates.append(pd.Timestamp(rb))
        prev_weights = weights.copy(deep=False)
        if bool(getattr(cfg, "path_sim_checkpoint", False)) and ((n + 1) % PATH_SIM_CHECKPOINT_INTERVAL == 0 or n + 1 >= backtest_steps):
            _save_path_sim_checkpoint(
                out_dir,
                cfg,
                last_n=n,
                prev_weights=prev_weights,
                backtest_equity=backtest_equity,
                daily_dates=daily_dates,
                daily_values=daily_values,
                simulated_rebalance_dates=simulated_rebalance_dates,
            )

        if dashboard is not None:
            dashboard.advance_phase(
                1,
                step="Rebalance abgeschlossen",
                rebalance=f"{n + 1}/{backtest_steps}",
                date=str(rb.date()),
                train_rows=f"{loop_train_rows:,}",
                candidates=loop_snapshot_rows,
            )
        elif (n + 1) % 25 == 0:
            print(f"  processed {n + 1}/{len(rebalance_dates)} rebalances")

    if dashboard is not None:
        dashboard.finish_phase()

    decisions_df = pd.DataFrame(decision_rows) if decision_rows else pd.DataFrame()
    decisions_df = deduplicate_dataframe_columns(decisions_df) if not decisions_df.empty else decisions_df
    weights_df = pd.DataFrame(weight_rows) if weight_rows else pd.DataFrame()
    strategy_returns = pd.Series(daily_values, index=pd.DatetimeIndex(daily_dates), name="strategy_return").sort_index()
    if not decisions_df.empty:
        decisions_df.attrs["simulated_rebalance_dates"] = simulated_rebalance_dates
    return strategy_returns, decisions_df, weights_df


def _naive_baselines_subprocess(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    """Picklable entry for overlapping naive baselines with path simulation."""
    overlap_workers = max(1, int(getattr(cfg, "cpu_cores", 16) or 16) // 2)
    cfg_overlap = replace(cfg, n_jobs=str(overlap_workers))
    return run_naive_momentum_baselines(features, returns, cfg_overlap, None)


def run_walkforward_pipeline(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    *,
    include_naive_baselines: bool = True,
    phase_timings: Optional[PhaseTimings] = None,
) -> Tuple[pd.Series, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Unified walk-forward pipeline for Ryzen multi-core hosts.

    Phase A (parallel): ML fit_predict + select_portfolio per rebalance.
    Phase B (serial, vectorized PnL): path-dependent portfolio, costs, turnover.
    Phase C (parallel): naive momentum baselines (independent variants).
    """
    dates = sorted(features["date"].dropna().unique())
    dates = [pd.Timestamp(d) for d in dates]
    if len(dates) < 600:
        raise RuntimeError("Not enough dates for walk-forward backtest.")

    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]
    if len(rebalance_dates) < 20:
        raise RuntimeError("Too few rebalance dates. Use an earlier --start or shorter --train-years.")

    workers = resolve_parallel_workers(
        cfg,
        feature_table_gb=_estimate_dataframe_gb(features),
        backend=str(getattr(cfg, "parallel_backtest_backend", "process") or "process"),
    )
    prediction_cache: Dict[pd.Timestamp, Dict[str, Any]] = {}
    phase_a_sec = 0.0
    if dashboard is not None:
        if workers > 1:
            dashboard.ok(f"Walk-forward Phase A: paralleles ML auf {workers} physischen Kernen")
        elif bool(getattr(cfg, "reuse_prediction_cache", False)):
            dashboard.ok("Walk-forward Phase A: Prediction-Cache prüfen")
        else:
            dashboard.ok("Walk-forward Phase A: serieller ML-Cache")
    t0 = monotonic()
    prediction_cache = precompute_backtest_predictions(
        features,
        dates,
        rebalance_dates,
        cfg,
        dashboard,
        out_dir=Path(getattr(cfg, "out_dir", "model_output")),
        n_tickers=int(features["ticker"].nunique()),
    )
    phase_a_sec = monotonic() - t0
    if phase_timings is not None:
        phase_timings.set("walkforward_phase_a_ml", phase_a_sec)
        phase_timings.meta["walkforward_ml_parallel"] = bool(workers > 1 and prediction_cache)
    if dashboard is not None:
        dashboard.ok(f"Phase A ML: {phase_a_sec:.1f}s")

    naive_future = None
    naive_executor = None
    naive_submit_at: Optional[float] = None
    naive_overlap = (
        include_naive_baselines
        and bool(getattr(cfg, "naive_momentum_baseline", True))
        and parallel_execution_enabled(cfg)
        and not bool(getattr(cfg, "no_naive_overlap", False))
    )
    if naive_overlap:
        from concurrent.futures import ProcessPoolExecutor
        overlap_workers = max(1, int(getattr(cfg, "cpu_cores", 16) or 16) // 2)
        if dashboard is not None:
            dashboard.ok(f"Phase C Naive parallel zu Phase B ({overlap_workers} Worker)")
        naive_executor = ProcessPoolExecutor(max_workers=1)
        naive_submit_at = monotonic()
        naive_future = naive_executor.submit(_naive_baselines_subprocess, features, returns, cfg)

    t1 = monotonic()
    strategy_returns, decisions_df, weights_df = _simulate_walkforward_portfolio_path(
        prediction_cache,
        features,
        returns,
        dates,
        rebalance_dates,
        cfg,
        dashboard,
    )
    phase_b_sec = monotonic() - t1
    if phase_timings is not None:
        phase_timings.set("walkforward_phase_b_path", phase_b_sec)
    if dashboard is not None:
        dashboard.ok(f"Phase B Pfad/Kosten: {phase_b_sec:.1f}s")

    naive_returns = pd.DataFrame()
    phase_c_sec = 0.0
    if naive_future is not None and naive_executor is not None:
        wait_started = monotonic()
        if dashboard is not None:
            dashboard.set_status(
                step="Warte auf parallele Naive Momentum Baselines",
                rebalance="",
                date="",
                train_rows="",
                candidates="",
            )
            dashboard.ok("Phase C Naive läuft im Hintergrund; warte auf Abschluss")
        try:
            while not naive_future.done():
                if dashboard is not None:
                    dashboard.set_status(step=f"Warte auf parallele Naive Momentum Baselines ({monotonic() - wait_started:.0f}s)")
                deadline = monotonic() + 5.0
                while monotonic() < deadline and not naive_future.done():
                    from aa_ui_pump import pump_ui

                    pump_ui(force=True)
                    sleep(0.1)
            naive_returns = naive_future.result()
        finally:
            naive_executor.shutdown(wait=True)
        if naive_submit_at is not None:
            phase_c_sec = monotonic() - naive_submit_at
    elif include_naive_baselines and bool(getattr(cfg, "naive_momentum_baseline", True)):
        t_c = monotonic()
        naive_returns = run_naive_momentum_baselines(features, returns, cfg, dashboard)
        phase_c_sec = monotonic() - t_c

    if phase_timings is not None:
        phase_timings.set("walkforward_phase_c_naive", phase_c_sec)
        phase_timings.meta["naive_overlap"] = bool(naive_overlap)

    if dashboard is not None and (phase_a_sec or phase_b_sec or phase_c_sec):
        dashboard.ok(f"Walk-forward Phasen: A={phase_a_sec:.1f}s | B={phase_b_sec:.1f}s | C={phase_c_sec:.1f}s")

    return strategy_returns, decisions_df, weights_df, naive_returns


@dataclass
class ResearchPipelineResult:
    strategy_returns: pd.Series
    decisions: pd.DataFrame
    weight_history: pd.DataFrame
    naive_returns: pd.DataFrame
    benchmark_returns: pd.Series
    metrics: Dict[str, float]
    bench_metrics: Dict[str, float]
    integrity: Optional[IntegrityResult] = None
    rebalance_dates: Optional[List[pd.Timestamp]] = None


def run_path_only_research(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    prediction_cache: Dict[pd.Timestamp, Dict[str, Any]],
    dashboard: Optional[RunDashboard] = None,
    *,
    run_id: str = "",
    phase_timings: Optional[PhaseTimings] = None,
) -> ResearchPipelineResult:
    """Phase B only: reuse cached ML predictions (slippage/fee sweeps without Phase A).

    When ``naive_detailed_reporting`` is set (e.g. H1 mom_1_top12), exports seal CSVs
    via ``run_naive_detailed_reporting`` — parallel to Phase B when overlap is enabled.
    """
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]

    out_dir = Path(getattr(cfg, "out_dir", "model_output") or "model_output")
    naive_future = None
    naive_executor = None
    naive_submit_at: Optional[float] = None
    naive_overlap = _naive_detailed_overlap_enabled(cfg)
    if naive_overlap:
        from concurrent.futures import ThreadPoolExecutor

        cfg_export = replace(cfg, out_dir=str(out_dir))
        if dashboard is not None:
            dashboard.ok("Phase C Naive-Detail parallel zu Phase B (path-only, Thread)")
        naive_executor = ThreadPoolExecutor(max_workers=1)
        naive_submit_at = monotonic()
        naive_future = naive_executor.submit(
            run_naive_detailed_reporting,
            features,
            returns,
            cfg_export,
            out_dir,
            None,
        )

    t0 = monotonic()
    strategy_returns, decisions, weight_history = _simulate_walkforward_portfolio_path(
        prediction_cache,
        features,
        returns,
        dates,
        rebalance_dates,
        cfg,
        dashboard,
    )
    phase_b_sec = monotonic() - t0

    phase_c_sec = 0.0
    if naive_future is not None and naive_executor is not None:
        _wait_naive_background_future(
            naive_future,
            naive_executor,
            dashboard=dashboard,
            wait_label="Naive-Detail-Export",
        )
        if naive_submit_at is not None:
            phase_c_sec = monotonic() - naive_submit_at
    elif _naive_detailed_export_wanted(cfg):
        t_c = monotonic()
        run_naive_detailed_reporting(features, returns, cfg, out_dir, dashboard)
        phase_c_sec = monotonic() - t_c

    seal_paths = verify_naive_detailed_artifacts(cfg, out_dir)

    if phase_timings is not None:
        phase_timings.set("walkforward_phase_a_ml", 0.0)
        phase_timings.set("walkforward_phase_b_path", phase_b_sec)
        phase_timings.set("walkforward_phase_c_naive", phase_c_sec)
        phase_timings.meta["backtest_scope"] = "path-only"
        phase_timings.meta["naive_detailed_overlap"] = bool(naive_overlap)
        phase_timings.meta["naive_detailed_path_only"] = bool(_naive_detailed_export_wanted(cfg))
        if seal_paths:
            phase_timings.meta["h1_seal_benchmark_paths"] = [p.name for p in seal_paths]
            phase_timings.meta["reporting_benchmark_note"] = (
                "benchmark_daily_returns.csv = SPY reporting; seal uses naive_mom_1_daily_returns.csv"
            )
    if dashboard is not None:
        dashboard.ok(f"Phase B (path-only): {phase_b_sec:.1f}s")
        if phase_c_sec:
            dashboard.ok(f"Phase C Naive-Detail: {phase_c_sec:.1f}s")

    naive_returns = pd.DataFrame()
    benchmark_returns, _bench_src, _bench_ok = load_verified_benchmark_returns(
        out_dir=out_dir,
        returns=returns,
        benchmark=cfg.benchmark,
        strategy_index=strategy_returns.index,
    )
    metrics = calculate_metrics(strategy_returns, benchmark_returns)
    bench_metrics = calculate_metrics(benchmark_returns)
    simulated = list(getattr(decisions, "attrs", {}).get("simulated_rebalance_dates", []))
    if not simulated and not decisions.empty and "rebalance_date" in decisions.columns:
        simulated = sorted({pd.Timestamp(d) for d in decisions["rebalance_date"].dropna().unique()})
    integrity = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        returns_calendar=returns.index,
        simulated_rebalance_dates=simulated,
        run_id=run_id,
    )
    return ResearchPipelineResult(
        strategy_returns=strategy_returns,
        decisions=decisions,
        weight_history=weight_history,
        naive_returns=naive_returns,
        benchmark_returns=benchmark_returns,
        metrics=metrics,
        bench_metrics=bench_metrics,
        integrity=integrity,
        rebalance_dates=rebalance_dates,
    )


def run_research_pipeline(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
    *,
    include_naive_baselines: bool = True,
    phase_timings: Optional[PhaseTimings] = None,
    run_id: str = "",
) -> ResearchPipelineResult:
    """Walk-forward phases A/B/C plus headline backtest metrics."""
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    first_possible = pd.Timestamp(cfg.start) + pd.DateOffset(years=cfg.train_years)
    rebalance_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % cfg.rebalance_every == 0]

    strategy_returns, decisions, weight_history, naive_returns = run_walkforward_pipeline(
        features,
        returns,
        cfg,
        dashboard,
        include_naive_baselines=include_naive_baselines,
        phase_timings=phase_timings,
    )
    out_dir = Path(getattr(cfg, "out_dir", "model_output") or "model_output")
    benchmark_returns, _bench_src, _bench_ok = load_verified_benchmark_returns(
        out_dir=out_dir,
        returns=returns,
        benchmark=cfg.benchmark,
        strategy_index=strategy_returns.index,
    )
    metrics = calculate_metrics(strategy_returns, benchmark_returns)
    bench_metrics = calculate_metrics(benchmark_returns)
    simulated = list(getattr(decisions, "attrs", {}).get("simulated_rebalance_dates", []))
    if not simulated and not decisions.empty and "rebalance_date" in decisions.columns:
        simulated = sorted({pd.Timestamp(d) for d in decisions["rebalance_date"].dropna().unique()})
    integrity = validate_backtest_calendar_integrity(
        rebalance_dates=rebalance_dates,
        strategy_returns=strategy_returns,
        benchmark_returns=benchmark_returns,
        returns_calendar=returns.index,
        simulated_rebalance_dates=simulated,
        run_id=run_id,
    )
    if bool(getattr(cfg, "naive_detailed_reporting", False)):
        run_naive_detailed_reporting(features, returns, cfg, out_dir, dashboard)
        verify_naive_detailed_artifacts(cfg, out_dir)
    return ResearchPipelineResult(
        strategy_returns=strategy_returns,
        decisions=decisions,
        weight_history=weight_history,
        naive_returns=naive_returns,
        benchmark_returns=benchmark_returns,
        metrics=metrics,
        bench_metrics=bench_metrics,
        integrity=integrity,
        rebalance_dates=rebalance_dates,
    )


def write_backtest_core_outputs(
    out_dir: Path,
    result: ResearchPipelineResult,
    *,
    output_files: Optional[List[Path]] = None,
) -> Tuple[Path, Path, Path, Path]:
    """Write mandatory backtest CSV outputs (strategy, decisions, weights, report path)."""
    files = output_files if output_files is not None else []
    out_dir = Path(out_dir)
    strategy_path = out_dir / "strategy_daily_returns.csv"
    decisions_path = out_dir / "backtest_decisions.csv"
    weights_path = out_dir / "backtest_weights.csv"
    report_path = out_dir / "backtest_report.txt"

    result.strategy_returns.to_csv(strategy_path, header=True)
    files.append(strategy_path)
    if not result.benchmark_returns.empty:
        bench_path = out_dir / "benchmark_daily_returns.csv"
        result.benchmark_returns.to_csv(bench_path, header=["benchmark_return"])
        files.append(bench_path)
    if not result.decisions.empty:
        result.decisions.to_csv(decisions_path, index=False)
        files.append(decisions_path)
        cb_path = write_constraint_binding_history(out_dir, result.decisions)
        if cb_path is not None:
            files.append(cb_path)
    if not result.weight_history.empty:
        result.weight_history.to_csv(weights_path, index=False)
        files.append(weights_path)
    return strategy_path, decisions_path, weights_path, report_path


def run_backtest(
    features: pd.DataFrame,
    returns: pd.DataFrame,
    cfg: BacktestConfig,
    dashboard: Optional[RunDashboard] = None,
) -> Tuple[pd.Series, pd.DataFrame, pd.DataFrame]:
    """Backward-compatible wrapper (Phasen A+B ohne Naive-Baselines)."""
    strategy_returns, decisions_df, weights_df, _ = run_walkforward_pipeline(
        features, returns, cfg, dashboard, include_naive_baselines=False
    )
    return strategy_returns, decisions_df, weights_df


def run_latest_signal(features: pd.DataFrame, cfg: BacktestConfig, dashboard: Optional[RunDashboard] = None) -> pd.DataFrame:
    if dashboard is not None:
        dashboard.start_phase("Aktuelles Signal", total=1, step="aktuelles Zielportfolio berechnen")
    latest_date = pd.Timestamp(features["date"].max())
    train_end = latest_date - pd.Timedelta(days=cfg.horizon * 2)
    train_start = latest_date - pd.DateOffset(years=cfg.train_years)
    train_mask = (features["date"] >= train_start) & (features["date"] <= train_end)
    if "in_universe" in features.columns:
        train_mask &= features["in_universe"].fillna(False).astype(bool)
    train = features.loc[train_mask].dropna(subset=["target"])
    snapshot = features[features["date"] == latest_date].copy()
    if len(train) < cfg.min_train_rows:
        raise RuntimeError("Not enough training data for latest signal. Lower --min-train-rows or expand history.")
    if dashboard is not None:
        dashboard.set_status(
            step="Training und aktuelles Signal",
            date=str(latest_date.date()),
            train_rows=f"{len(train):,}",
            candidates=len(snapshot),
        )
    pred, rmse = fit_predict(train, snapshot, FEATURE_COLUMNS, cfg)
    _, ranked = select_portfolio(pred, rmse, cfg)
    if dashboard is not None:
        dashboard.advance_phase(
            1,
            step="aktuelles Zielportfolio berechnet",
            date=str(latest_date.date()),
            train_rows=f"{len(train):,}",
            candidates=len(snapshot),
        )
        dashboard.finish_phase()
    ranked["signal_date"] = latest_date
    return ranked.sort_values("target_weight", ascending=False)


def _first_column_as_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a single Series for col even when a DataFrame has duplicate column labels.

    Pandas returns a DataFrame for df[col] / df.loc[:, col] when the column name
    is duplicated. That broke reporting diagnostics via pd.to_numeric(...).  The
    backtest decision table can legitimately contain duplicate diagnostic labels
    after layered concat/merge operations, so diagnostics must be defensive.
    """
    if df is None or col not in df.columns:
        return pd.Series(dtype="float64")
    data = df.loc[:, col]
    if isinstance(data, pd.DataFrame):
        if data.shape[1] == 0:
            return pd.Series(index=df.index, dtype="float64")
        # Coalesce duplicate columns row-wise. If all duplicates are identical,
        # this is equivalent to taking the first column; if one duplicate has
        # missing values, the next duplicate can still supply the diagnostic.
        try:
            return data.bfill(axis=1).iloc[:, 0]
        except Exception:
            return data.iloc[:, 0]
    return data


def _numeric_series(df: pd.DataFrame, col: str) -> pd.Series:
    return pd.to_numeric(_first_column_as_series(df, col), errors="coerce")


def _bool_series(df: pd.DataFrame, col: str) -> pd.Series:
    s = _first_column_as_series(df, col)
    if s.empty:
        return pd.Series(False, index=df.index)
    if s.dtype == bool:
        return s.fillna(False).astype(bool)
    text = s.astype(str).str.strip().str.lower()
    return text.isin({"true", "1", "yes", "y", "j", "ja"})


