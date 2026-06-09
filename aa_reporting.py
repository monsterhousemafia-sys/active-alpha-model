from __future__ import annotations

import argparse
import json
import math
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, TypeVar

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, normalize_yfinance_ticker, parse_extra_benchmark_tickers
from aa_dashboard import RunDashboard
from aa_execution import write_run_manifest
from aa_features import build_feature_by_date
from aa_parallel import (
    _CTX,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)
from aa_portfolio import _momentum_score, _momentum_variant_label, _neutralized_momentum_candidates

def calculate_metrics(daily_returns: pd.Series, benchmark_returns: Optional[pd.Series] = None) -> Dict[str, float]:
    r = daily_returns.dropna().astype(float)
    if r.empty:
        return {}
    equity = (1.0 + r).cumprod()
    years = len(r) / 252.0
    total = equity.iloc[-1] - 1.0
    cagr = equity.iloc[-1] ** (1.0 / years) - 1.0 if years > 0 else np.nan
    vol = r.std() * math.sqrt(252)
    sharpe = (r.mean() / r.std()) * math.sqrt(252) if r.std() > 0 else np.nan
    dd = equity / equity.cummax() - 1.0
    maxdd = dd.min()
    hit = (r > 0).mean()
    out = {
        "total_return": total,
        "cagr": cagr,
        "annual_vol": vol,
        "sharpe_0rf": sharpe,
        "max_drawdown": maxdd,
        "daily_hit_rate": hit,
        "n_days": len(r),
    }
    if benchmark_returns is not None:
        b = benchmark_returns.reindex(r.index).dropna()
        common = r.index.intersection(b.index)
        if len(common) > 10:
            excess = r.reindex(common) - b.reindex(common)
            te = excess.std() * math.sqrt(252)
            info = (excess.mean() / excess.std()) * math.sqrt(252) if excess.std() > 0 else np.nan
            out["information_ratio"] = info
            out["tracking_error"] = te
            out["excess_cagr_approx"] = (r.reindex(common).mean() - b.reindex(common).mean()) * 252
    return out




def _safe_metric_value(x: object, default: float = 0.0) -> float:
    try:
        v = float(x)
        return v if np.isfinite(v) else default
    except Exception:
        return default

def _benchmark_row(strategy_returns: pd.Series, benchmark_returns: pd.Series, name: str, source: str) -> Optional[Dict[str, object]]:
    common = strategy_returns.dropna().index.intersection(benchmark_returns.dropna().index)
    if len(common) < 30:
        return None
    s = strategy_returns.reindex(common).fillna(0.0)
    b = benchmark_returns.reindex(common).fillna(0.0)
    sm = calculate_metrics(s, b)
    bm = calculate_metrics(b)
    corr = float(s.corr(b)) if len(common) > 2 else np.nan
    beta = float(np.cov(s.values, b.values)[0, 1] / np.var(b.values)) if np.var(b.values) > 0 else np.nan
    return {
        "benchmark": name,
        "source": source,
        "n_days": int(len(common)),
        "strategy_cagr": sm.get("cagr", np.nan),
        "benchmark_cagr": bm.get("cagr", np.nan),
        "cagr_diff": sm.get("cagr", np.nan) - bm.get("cagr", np.nan),
        "strategy_sharpe_0rf": sm.get("sharpe_0rf", np.nan),
        "benchmark_sharpe_0rf": bm.get("sharpe_0rf", np.nan),
        "sharpe_diff": sm.get("sharpe_0rf", np.nan) - bm.get("sharpe_0rf", np.nan),
        "strategy_max_drawdown": sm.get("max_drawdown", np.nan),
        "benchmark_max_drawdown": bm.get("max_drawdown", np.nan),
        "information_ratio": sm.get("information_ratio", np.nan),
        "tracking_error": sm.get("tracking_error", np.nan),
        "correlation": corr,
        "beta_to_benchmark": beta,
    }


def _mean_return_for_tickers(
    r_row: pd.Series,
    tickers: List[str],
    weights: Optional[pd.Series] = None,
) -> Optional[float]:
    tks = [str(t).upper().strip() for t in tickers if str(t).upper().strip() in r_row.index]
    if not tks:
        return None
    rv = r_row.reindex(tks).fillna(0.0).astype(float).values
    if weights is None:
        return float(np.mean(rv))
    w = weights.reindex(tks).fillna(0.0).astype(float).values
    w_sum = float(w.sum())
    if w_sum <= 0:
        return float(np.mean(rv))
    return float(np.dot(w / w_sum, rv))


def _custom_benchmark_returns_for_snapshot(
    base: pd.DataFrame,
    r_row: pd.Series,
    cfg: BacktestConfig,
) -> Dict[str, float]:
    adv = pd.to_numeric(base.get("universe_adv", base.get("adv_20", 0.0)), errors="coerce").fillna(0.0)
    score = _momentum_score(base, "mom_blend_top12")
    ranked = base.assign(momentum_baseline_score=score).sort_values("momentum_baseline_score", ascending=False)
    top100 = base.loc[adv.sort_values(ascending=False).head(100).index]
    out: Dict[str, float] = {}
    mapping = {
        "strategy_universe_equal_weight": (base["ticker"].astype(str).str.upper().tolist(), None),
        "top100_liquidity_equal_weight": (top100["ticker"].tolist(), None),
        "top100_liquidity_cap_weight_proxy": (top100["ticker"].tolist(), adv.loc[top100.index]),
        "sector_neutral_momentum_top12": (_neutralized_momentum_candidates(ranked, cfg, "sector_neutral_momentum"), None),
        "cluster_neutral_momentum_top12": (_neutralized_momentum_candidates(ranked, cfg, "cluster_neutral_momentum"), None),
    }
    for label, (tickers, weights) in mapping.items():
        ret = _mean_return_for_tickers(r_row, tickers, weights)
        if ret is not None:
            out[label] = ret
    return out


def compute_custom_benchmark_returns(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig) -> Dict[str, pd.Series]:
    """Generate simple internal control benchmarks without using model forecasts."""
    if not bool(getattr(cfg, "custom_benchmarks", True)):
        return {}
    dates = sorted(pd.Timestamp(d) for d in features["date"].dropna().unique())
    if len(dates) < 100:
        return {}
    by_date = build_feature_by_date(features)
    names = [
        "strategy_universe_equal_weight",
        "top100_liquidity_equal_weight",
        "top100_liquidity_cap_weight_proxy",
        "sector_neutral_momentum_top12",
        "cluster_neutral_momentum_top12",
    ]
    values: Dict[str, List[Tuple[pd.Timestamp, float]]] = {n: [] for n in names}
    ret_index = returns.index
    for i in range(1, len(dates)):
        prev = dates[i - 1]
        dt = dates[i]
        if dt not in ret_index:
            continue
        snap = by_date.get(prev)
        if snap is None or snap.empty:
            continue
        if "in_universe" in snap.columns:
            base = snap.loc[snap["in_universe"].fillna(False).astype(bool)]
        else:
            base = snap
        if base.empty:
            continue
        daily = _custom_benchmark_returns_for_snapshot(base, returns.loc[dt], cfg)
        for label, ret in daily.items():
            values[label].append((dt, ret))
    out: Dict[str, pd.Series] = {}
    for name, pairs in values.items():
        if pairs:
            idx, vals = zip(*pairs)
            out[name.upper()] = pd.Series(vals, index=pd.DatetimeIndex(idx), name=name.upper()).sort_index()
    return out


def compute_benchmark_comparison(strategy_returns: pd.Series, returns: pd.DataFrame, cfg: BacktestConfig, naive_returns: Optional[pd.DataFrame | pd.Series] = None, custom_returns: Optional[Dict[str, pd.Series]] = None) -> pd.DataFrame:
    rows: List[Dict[str, object]] = []
    benchmark_list = [normalize_yfinance_ticker(cfg.benchmark)] + [t for t in parse_extra_benchmark_tickers(cfg) if t != normalize_yfinance_ticker(cfg.benchmark)]
    for tk in benchmark_list:
        if tk not in returns.columns:
            continue
        row = _benchmark_row(strategy_returns, returns[tk], tk, "downloaded_proxy")
        if row is not None:
            rows.append(row)
    if naive_returns is not None:
        if isinstance(naive_returns, pd.Series):
            naive_df = naive_returns.to_frame()
        else:
            naive_df = naive_returns.copy()
        for col in naive_df.columns:
            row = _benchmark_row(strategy_returns, naive_df[col], str(col), "internal_naive_momentum")
            if row is not None:
                rows.append(row)
    for name, ser in (custom_returns or {}).items():
        row = _benchmark_row(strategy_returns, ser, str(name), "internal_custom_benchmark")
        if row is not None:
            rows.append(row)
    return pd.DataFrame(rows)


def compute_factor_proxy_regression(strategy_returns: pd.Series, returns: pd.DataFrame, cfg: BacktestConfig) -> pd.DataFrame:
    proxy_names = [t for t in parse_extra_benchmark_tickers(cfg) if t in returns.columns]
    if normalize_yfinance_ticker(cfg.benchmark) in returns.columns and normalize_yfinance_ticker(cfg.benchmark) not in proxy_names:
        proxy_names = [normalize_yfinance_ticker(cfg.benchmark)] + proxy_names
    if not proxy_names:
        return pd.DataFrame()
    common = strategy_returns.dropna().index
    for tk in proxy_names:
        common = common.intersection(returns[tk].dropna().index)
    if len(common) < max(100, len(proxy_names) * 20):
        return pd.DataFrame()
    y = strategy_returns.reindex(common).fillna(0.0).values.astype(float)
    X = np.column_stack([np.ones(len(common))] + [returns[tk].reindex(common).fillna(0.0).values.astype(float) for tk in proxy_names])
    try:
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    except Exception:
        return pd.DataFrame()
    fitted = X @ coef
    resid = y - fitted
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    rows = [{"term": "intercept_daily", "coefficient": float(coef[0]), "annualized": float(coef[0] * 252.0), "r_squared": r2, "n_days": len(common)}]
    for tk, c in zip(proxy_names, coef[1:]):
        rows.append({"term": tk, "coefficient": float(c), "annualized": np.nan, "r_squared": r2, "n_days": len(common)})
    rows.append({"term": "residual_annual_vol", "coefficient": float(np.nanstd(resid) * math.sqrt(252)), "annualized": np.nan, "r_squared": r2, "n_days": len(common)})
    return pd.DataFrame(rows)


def newey_west_tstat(x: pd.Series, lags: Optional[int] = None) -> float:
    """Newey-West t-statistic for the mean of a return/excess-return series."""
    s = pd.Series(x).dropna().astype(float)
    n = len(s)
    if n < 10:
        return np.nan
    y = s.values - float(s.mean())
    if lags is None:
        lags = int(max(1, round(4 * (n / 100.0) ** (2.0 / 9.0))))
    gamma0 = float(np.dot(y, y) / n)
    var = gamma0
    for lag in range(1, min(lags, n - 1) + 1):
        cov = float(np.dot(y[lag:], y[:-lag]) / n)
        weight = 1.0 - lag / (lags + 1.0)
        var += 2.0 * weight * cov
    se = math.sqrt(max(var, 0.0) / n)
    return float(s.mean() / se) if se > 0 else np.nan


def _series_sharpe(x: pd.Series) -> float:
    s = pd.Series(x).dropna().astype(float)
    return float((s.mean() / s.std()) * math.sqrt(252.0)) if len(s) > 2 and s.std() > 0 else np.nan


def _deflated_sharpe_proxy(sharpe: float, n_obs: int, n_trials: int) -> float:
    """Conservative deflated-Sharpe-style proxy, not a formal Bailey-Lopez de Prado implementation."""
    if not np.isfinite(sharpe) or n_obs <= 2:
        return np.nan
    trials = max(int(n_trials), 1)
    hurdle = math.sqrt(max(0.0, 2.0 * math.log(trials)) / max(n_obs / 252.0, 1e-9))
    return float(sharpe - hurdle)


def _bootstrap_initializer(strategy: pd.Series, bench: Dict[str, Optional[pd.Series]]) -> None:
    _parallel_worker_bootstrap()
    _CTX.boot_strategy = strategy
    _CTX.boot_bench = bench


def _bootstrap_batch_task(task: Dict[str, Any]) -> Tuple[str, List[Dict[str, float]]]:
    if _CTX.boot_strategy is None or _CTX.boot_bench is None:
        raise RuntimeError("Bootstrap worker was not initialized.")
    label = str(task["label"])
    bench_key = task.get("bench_key")
    b = _CTX.boot_bench.get(str(bench_key)) if bench_key is not None else None
    rng = np.random.default_rng(int(task["seed"]))
    samples = _block_bootstrap_metrics(
        _CTX.boot_strategy,
        b,
        rng,
        iterations=int(task["n_iter"]),
        block=int(task.get("block", 21)),
    )
    return label, samples


def _block_bootstrap_metrics(s: pd.Series, b: Optional[pd.Series], rng: np.random.Generator, iterations: int, block: int = 21) -> List[Dict[str, float]]:
    sr = pd.Series(s).dropna().astype(float)
    if b is not None:
        br = pd.Series(b).reindex(sr.index).dropna().astype(float)
        common = sr.index.intersection(br.index)
        sr = sr.reindex(common).fillna(0.0)
        br = br.reindex(common).fillna(0.0)
    else:
        br = None
    n = len(sr)
    if n < max(60, block * 3) or iterations <= 0:
        return []
    vals = sr.values
    bvals = br.values if br is not None else None
    rows: List[Dict[str, float]] = []
    starts = np.arange(0, n)
    for _ in range(int(iterations)):
        chunks = []
        bchunks = []
        while sum(len(c) for c in chunks) < n:
            st = int(rng.choice(starts))
            idx = np.arange(st, st + block) % n
            chunks.append(vals[idx])
            if bvals is not None:
                bchunks.append(bvals[idx])
        sample = np.concatenate(chunks)[:n]
        ser = pd.Series(sample)
        if bvals is not None:
            bench = pd.Series(np.concatenate(bchunks)[:n])
            met = calculate_metrics(ser, bench)
            excess = ser - bench
            rows.append({
                "cagr": met.get("cagr", np.nan),
                "sharpe_0rf": met.get("sharpe_0rf", np.nan),
                "max_drawdown": met.get("max_drawdown", np.nan),
                "information_ratio": met.get("information_ratio", np.nan),
                "annualized_excess_mean": float(excess.mean() * 252.0),
            })
        else:
            met = calculate_metrics(ser)
            rows.append({
                "cagr": met.get("cagr", np.nan),
                "sharpe_0rf": met.get("sharpe_0rf", np.nan),
                "max_drawdown": met.get("max_drawdown", np.nan),
                "information_ratio": np.nan,
                "annualized_excess_mean": np.nan,
            })
    return rows


def compute_statistical_diagnostics(strategy_returns: pd.Series, returns: pd.DataFrame, cfg: BacktestConfig, benchmark_comparison: Optional[pd.DataFrame] = None, naive_returns: Optional[pd.DataFrame] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if not bool(getattr(cfg, "statistical_diagnostics", True)):
        return pd.DataFrame(), pd.DataFrame()
    s = strategy_returns.dropna().astype(float)
    if s.empty:
        return pd.DataFrame(), pd.DataFrame()
    rows: List[Dict[str, object]] = []
    boot_rows: List[Dict[str, object]] = []
    n_trials = 1
    if benchmark_comparison is not None and not benchmark_comparison.empty:
        n_trials += int(len(benchmark_comparison))
    n_trials += len(["ensemble", "ml_only", "rank_only", "elastic_only", "gbm_only"])
    sr = _series_sharpe(s)
    rows.append({
        "series": "strategy",
        "metric": "mean_daily_return",
        "value": float(s.mean()),
        "annualized": float(s.mean() * 252.0),
        "newey_west_tstat": newey_west_tstat(s),
        "n_days": int(len(s)),
    })
    rows.append({
        "series": "strategy",
        "metric": "sharpe_0rf",
        "value": sr,
        "annualized": sr,
        "newey_west_tstat": np.nan,
        "n_days": int(len(s)),
    })
    rows.append({
        "series": "strategy",
        "metric": "deflated_sharpe_proxy",
        "value": _deflated_sharpe_proxy(sr, len(s), n_trials),
        "annualized": np.nan,
        "newey_west_tstat": np.nan,
        "n_days": int(len(s)),
        "n_trials_proxy": int(n_trials),
    })
    # Excess-return diagnostics against SPY, extra ETFs and the strongest internal baselines.
    candidates: Dict[str, pd.Series] = {}
    for tk in [normalize_yfinance_ticker(cfg.benchmark)] + parse_extra_benchmark_tickers(cfg):
        if tk in returns.columns:
            candidates[tk] = returns[tk]
    if naive_returns is not None and not naive_returns.empty:
        for col in naive_returns.columns:
            candidates[str(col)] = naive_returns[col]
    for name, b in candidates.items():
        common = s.index.intersection(b.dropna().index)
        if len(common) < 30:
            continue
        ex = s.reindex(common).fillna(0.0) - b.reindex(common).fillna(0.0)
        rows.append({
            "series": f"excess_vs_{name}",
            "metric": "mean_daily_excess",
            "value": float(ex.mean()),
            "annualized": float(ex.mean() * 252.0),
            "newey_west_tstat": newey_west_tstat(ex),
            "n_days": int(len(ex)),
        })
    iterations = int(getattr(cfg, "bootstrap_iterations", 0) or 0)
    if iterations > 0:
        base_seed = int(getattr(cfg, "random_seed", 42) or 42)
        boot_targets: Dict[str, Optional[pd.Series]] = {"strategy": None}
        for name in [normalize_yfinance_ticker(cfg.benchmark), "QQQ", "RSP", "MTUM"]:
            if name in returns.columns:
                boot_targets[f"vs_{name}"] = returns[name]
        if naive_returns is not None and not naive_returns.empty:
            for col in list(naive_returns.columns)[:3]:
                boot_targets[f"vs_{col}"] = naive_returns[col]
        boot_tasks: List[Dict[str, Any]] = []
        if parallel_execution_enabled(cfg) and iterations >= 2:
            n_boot_workers = resolve_parallel_workers(cfg, backend="process")
            per_worker = max(1, iterations // n_boot_workers)
            extra = iterations % n_boot_workers
            for label, b in boot_targets.items():
                bench_key = label if b is not None else "__none__"
                for w in range(n_boot_workers):
                    n_iter = per_worker + (1 if w < extra else 0)
                    if n_iter <= 0:
                        continue
                    boot_tasks.append({
                        "label": label,
                        "bench_key": bench_key,
                        "seed": base_seed + w * 10_000 + (sum(ord(c) for c in label) % 10_000),
                        "n_iter": n_iter,
                        "block": 21,
                    })
            bench_map = {label if b is not None else "__none__": b for label, b in boot_targets.items()}
            batch_results = _parallel_map_unordered(
                cfg,
                _bootstrap_batch_task,
                boot_tasks,
                initializer=_bootstrap_initializer,
                initargs=(s, bench_map),
            )
        else:
            rng = np.random.default_rng(base_seed)
            batch_results = [
                (label, _block_bootstrap_metrics(s, b, rng, iterations=iterations, block=21))
                for label, b in boot_targets.items()
            ]
        samples_by_label: Dict[str, List[Dict[str, float]]] = {}
        for label, samples in batch_results:
            if not samples:
                continue
            samples_by_label.setdefault(label, []).extend(samples)
        for label, samples in samples_by_label.items():
            df = pd.DataFrame(samples)
            for metric in ["cagr", "sharpe_0rf", "max_drawdown", "information_ratio", "annualized_excess_mean"]:
                if metric not in df.columns:
                    continue
                vals = pd.to_numeric(df[metric], errors="coerce").dropna()
                if vals.empty:
                    continue
                boot_rows.append({
                    "series": label,
                    "metric": metric,
                    "p05": float(vals.quantile(0.05)),
                    "p50": float(vals.quantile(0.50)),
                    "p95": float(vals.quantile(0.95)),
                    "iterations": int(iterations),
                    "block_length": 21,
                })
    return pd.DataFrame(rows), pd.DataFrame(boot_rows)


def _first_column_as_series(df: pd.DataFrame, col: str) -> pd.Series:
    """Return a single Series for col even when duplicate column labels exist."""
    if df is None or col not in df.columns:
        return pd.Series(dtype="float64")
    data = df.loc[:, col]
    if isinstance(data, pd.DataFrame):
        if data.shape[1] == 0:
            return pd.Series(index=df.index, dtype="float64")
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

def summarize_backtest_diagnostics(decisions: pd.DataFrame, cfg: BacktestConfig) -> Dict[str, float]:
    if decisions.empty or "rebalance_date" not in decisions.columns:
        return {}
    rb = decisions.drop_duplicates("rebalance_date").copy()
    out: Dict[str, float] = {"n_rebalances": float(len(rb))}
    duplicate_labels = rb.columns[rb.columns.duplicated()].tolist()
    if duplicate_labels:
        out["n_duplicate_decision_columns"] = float(len(duplicate_labels))
        out["n_unique_duplicate_decision_columns"] = float(len(set(duplicate_labels)))
    for col in [
        "turnover", "raw_turnover", "tx_cost", "commission_cost", "slippage_cost", "regulatory_fee_cost",
        "sec_fee_cost", "finra_taf_cost", "cat_fee_cost", "clearing_fee_cost", "exchange_fee_cost",
        "pass_through_fee_cost", "fx_fee_cost", "market_impact_cost", "tx_cost_dollars", "commission_dollars",
        "slippage_dollars", "regulatory_fees_dollars", "sec_fee_dollars", "finra_taf_dollars",
        "cat_fee_dollars", "clearing_fee_dollars", "exchange_fee_dollars", "pass_through_fee_dollars",
        "fx_fee_dollars", "market_impact_dollars",
        "n_orders", "fee_price_fallback_orders", "backtest_equity_before_rebalance", "backtest_equity_after_period",
        "desired_exposure", "regime_target_exposure", "exposure_before_constraints", "exposure_after_position_cap", "exposure_after_issuer_cap", "exposure_after_sector_cap", "exposure_after_cluster_cap", "exposure_after_beta_cap", "target_exposure_before_trade_controls", "target_exposure_after_buy_hold", "exposure_after_trade_controls", "exposure_after_tail_prune", "exposure_after_min_trade", "final_validated_exposure", "cash_gap_vs_desired_exposure", "cash_due_to_position_cap", "cash_due_to_issuer_cap", "cash_due_to_sector_cap", "cash_due_to_cluster_cap", "cash_due_to_beta_cap", "cash_due_to_trade_controls", "cash_due_to_min_trade_filter", "cash_due_to_signal_shortage", "cash_due_to_risk_off_regime", "exposure_gap_vs_risk_floor",
        "n_positions_before_tail_prune", "n_positions_after_tail_prune", "exposure_before_tail_prune", "residual_positions_pruned", "residual_weight_pruned", "soft_cap_positions_pruned", "soft_cap_weight_pruned", "total_weight_pruned", "weight_reallocated_after_prune", "weight_left_cash_after_prune", "tail_prune_turnover", "tail_prune_sell_turnover", "tail_prune_reallocation_turnover", "soft_position_cap_breach", "hard_position_cap_breach", "tail_prune_constraint_failure", "tail_prune_reallocation_failed", "soft_cap_relaxed_count", "hard_cap_fallback_count", "tail_prune_full_fallback", "max_position_binding_after_prune", "max_sector_binding_after_prune", "max_cluster_binding_after_prune", "max_beta_binding_after_prune",
        "economic_position_floor", "n_economic_positions_005", "n_dust_positions_below_005", "dust_weight_below_005",
        "n_economic_positions_after_min_trade", "n_dust_positions_after_min_trade", "dust_weight_after_min_trade",
        "portfolio_exposure", "portfolio_beta",
        "max_position_weight", "max_issuer_weight", "max_sector_weight", "max_correlation_cluster_weight", "n_positions", "constraint_violations", "gross_exposure_binding", "max_position_binding", "max_issuer_binding", "max_sector_binding", "max_cluster_binding", "max_beta_binding", "unknown_sector_weight", "unknown_cluster_weight", "unknown_issuer_weight", "n_unknown_sector_positions", "n_unknown_cluster_positions", "n_unknown_issuer_positions", "n_candidates", "n_eligible_candidates", "n_selected_candidates", "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol",
    ]:
        if col in rb.columns:
            s = _numeric_series(rb, col)
            out[f"avg_{col}"] = float(s.mean()) if len(s) else float("nan")
            out[f"max_{col}"] = float(s.max()) if len(s) else float("nan")
    if "turnover" in rb.columns:
        out["approx_annual_turnover"] = float(_numeric_series(rb, "turnover").mean() * 252.0 / max(cfg.rebalance_every, 1))
    if "risk_on" in rb.columns:
        risk_on_mask = _bool_series(rb, "risk_on")
        ro = rb[risk_on_mask]
        out["risk_on_share"] = float(len(ro) / max(len(rb), 1))
        if not ro.empty:
            if "portfolio_exposure" in ro.columns:
                out["avg_exposure_when_risk_on"] = float(_numeric_series(ro, "portfolio_exposure").mean())
            if "portfolio_beta" in ro.columns:
                out["avg_beta_when_risk_on"] = float(_numeric_series(ro, "portfolio_beta").mean())
        rf = rb[~risk_on_mask]
        if not rf.empty and "portfolio_exposure" in rf.columns:
            out["avg_exposure_when_risk_off"] = float(_numeric_series(rf, "portfolio_exposure").mean())
    return out


def write_reporting_errors_json(path: Path, errors: List[Dict[str, str]]) -> None:
    """Write structured reporting failures for tooling/CI (companion to reporting_errors.txt)."""
    payload: Dict[str, Any] = {
        "schema_version": 1,
        "count": len(errors),
        "errors": list(errors),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


T = TypeVar("T")


class ReportingPipeline:
    """Structured optional reporting steps with progress/error logs."""

    def __init__(
        self,
        out_dir: Path,
        *,
        dashboard: Optional[RunDashboard] = None,
        output_files: Optional[List[Path]] = None,
        fail_on_error: bool = False,
    ) -> None:
        self.out_dir = Path(out_dir)
        self.dashboard = dashboard
        self.output_files = output_files if output_files is not None else []
        self.fail_on_error = bool(fail_on_error)
        self.progress_path = self.out_dir / "reporting_progress.txt"
        self.errors_path = self.out_dir / "reporting_errors.txt"
        self.errors: List[Dict[str, str]] = []

    def add_output_file(self, path: Path) -> None:
        try:
            if path.exists() and path not in self.output_files:
                self.output_files.append(path)
        except Exception:
            pass

    def _write_progress(self, step: str, status: str, detail: str = "") -> None:
        try:
            with self.progress_path.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\t{step}\t{status}\t{detail}\n")
            self.add_output_file(self.progress_path)
        except Exception:
            pass

    def _write_error(self, step: str, exc: Exception) -> None:
        tb = traceback.format_exc()
        self.errors.append({"step": step, "type": type(exc).__name__, "message": str(exc)})
        try:
            with self.errors_path.open("a", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write(f"timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"step: {step}\n")
                f.write(f"exception_type: {type(exc).__name__}\n")
                f.write(f"exception_message: {exc}\n")
                f.write(tb)
                f.write("\n")
            self.add_output_file(self.errors_path)
        except Exception:
            pass
        if self.dashboard is not None:
            try:
                self.dashboard.warn(f"Reporting step failed: {step}: {exc}")
            except Exception:
                pass
        if self.fail_on_error:
            raise exc

    def run_step(self, step: str, fn: Callable[[], T], default: T) -> T:
        self._write_progress(step, "START")
        try:
            result = fn()
            self._write_progress(step, "OK")
            return result
        except Exception as exc:
            self._write_progress(step, "ERROR", str(exc))
            self._write_error(step, exc)
            return default

    def finalize(self) -> None:
        if not self.errors:
            return
        json_path = self.out_dir / "reporting_errors.json"
        self.run_step(
            "reporting_errors_json",
            lambda: (write_reporting_errors_json(json_path, self.errors), self.add_output_file(json_path)),
            None,
        )


def run_backtest_reporting(
    out_dir: Path,
    cfg: BacktestConfig,
    *,
    args: argparse.Namespace,
    dashboard: RunDashboard,
    output_files: List[Path],
    features: pd.DataFrame,
    returns: pd.DataFrame,
    strategy_returns: pd.Series,
    benchmark_returns: pd.Series,
    decisions: pd.DataFrame,
    weight_history: pd.DataFrame,
    naive_returns: pd.DataFrame,
    metrics: Dict[str, float],
    bench_metrics: Dict[str, float],
    no_plot: bool = False,
) -> None:
    """Write backtest CSVs, optional diagnostics, and reports."""
    report_path = out_dir / "backtest_report.txt"
    pipeline = ReportingPipeline(
        out_dir,
        dashboard=dashboard,
        output_files=output_files,
        fail_on_error=bool(getattr(args, "fail_on_reporting_error", False)),
    )

    if bool(getattr(cfg, "minimal_backtest_reporting", False)):
        diagnostics = pipeline.run_step(
            "summarize_backtest_diagnostics",
            lambda: summarize_backtest_diagnostics(decisions, cfg),
            {},
        )
        pipeline.run_step(
            "minimal_backtest_report",
            lambda: (write_report(report_path, cfg, metrics, bench_metrics, diagnostics), pipeline.add_output_file(report_path)),
            None,
        )
        pipeline.finalize()
        return

    def _custom_step() -> Dict[str, pd.Series]:
        cr = compute_custom_benchmark_returns(features, returns, cfg)
        if cr:
            custom_path = out_dir / "custom_benchmark_daily_returns.csv"
            pd.DataFrame(cr).to_csv(custom_path)
            pipeline.add_output_file(custom_path)
        return cr

    def _factor_step() -> pd.DataFrame:
        fr = compute_factor_proxy_regression(strategy_returns, returns, cfg)
        if not fr.empty:
            factor_regression_path = out_dir / "factor_proxy_regression.csv"
            fr.to_csv(factor_regression_path, index=False)
            pipeline.add_output_file(factor_regression_path)
        return fr

    with ThreadPoolExecutor(max_workers=3) as reporting_pool:
        fut_diag = reporting_pool.submit(
            pipeline.run_step,
            "summarize_backtest_diagnostics",
            lambda: summarize_backtest_diagnostics(decisions, cfg),
            {},
        )
        fut_custom = reporting_pool.submit(pipeline.run_step, "custom_benchmark_returns", _custom_step, {})
        fut_factor = reporting_pool.submit(pipeline.run_step, "factor_proxy_regression", _factor_step, pd.DataFrame())
        diagnostics = fut_diag.result()
        custom_returns = fut_custom.result()
        factor_regression = fut_factor.result()

    pipeline.run_step(
        "minimal_backtest_report",
        lambda: (write_report(report_path, cfg, metrics, bench_metrics, diagnostics), pipeline.add_output_file(report_path)),
        None,
    )
    if not no_plot:
        pipeline.run_step(
            "equity_curve_plot",
            lambda: (maybe_plot(out_dir, strategy_returns, benchmark_returns), pipeline.add_output_file(out_dir / "equity_curve.png")),
            None,
        )
    if cfg.run_manifest:
        pipeline.run_step(
            "early_run_manifest",
            lambda: (
                write_run_manifest(out_dir / "run_manifest.json", cfg, output_files, args),
                pipeline.add_output_file(out_dir / "run_manifest.json"),
            ),
            None,
        )

    if not naive_returns.empty:
        naive_path = out_dir / "naive_momentum_daily_returns.csv"
        naive_returns.to_csv(naive_path)
        pipeline.add_output_file(naive_path)

    def _benchmark_step() -> pd.DataFrame:
        bc = compute_benchmark_comparison(strategy_returns, returns, cfg, naive_returns, custom_returns)
        if not bc.empty:
            benchmark_comparison_path = out_dir / "benchmark_comparison.csv"
            bc.to_csv(benchmark_comparison_path, index=False)
            pipeline.add_output_file(benchmark_comparison_path)
        return bc

    benchmark_comparison = pipeline.run_step("benchmark_comparison", _benchmark_step, pd.DataFrame())

    def _stat_step() -> Tuple[pd.DataFrame, pd.DataFrame]:
        sd, bi = compute_statistical_diagnostics(strategy_returns, returns, cfg, benchmark_comparison, naive_returns)
        if not sd.empty:
            statistical_path = out_dir / "statistical_diagnostics.csv"
            sd.to_csv(statistical_path, index=False)
            pipeline.add_output_file(statistical_path)
        if not bi.empty:
            bootstrap_path = out_dir / "bootstrap_performance_intervals.csv"
            bi.to_csv(bootstrap_path, index=False)
            pipeline.add_output_file(bootstrap_path)
        return sd, bi

    statistical_diagnostics, bootstrap_intervals = pipeline.run_step(
        "statistical_diagnostics",
        _stat_step,
        (pd.DataFrame(), pd.DataFrame()),
    )

    pipeline.run_step(
        "final_backtest_report",
        lambda: (
            write_report(
                report_path,
                cfg,
                metrics,
                bench_metrics,
                diagnostics,
                benchmark_comparison,
                factor_regression,
                statistical_diagnostics,
                bootstrap_intervals,
            ),
            pipeline.add_output_file(report_path),
        ),
        None,
    )
    if cfg.run_manifest:
        pipeline.run_step(
            "final_run_manifest",
            lambda: (
                write_run_manifest(out_dir / "run_manifest.json", cfg, output_files, args),
                pipeline.add_output_file(out_dir / "run_manifest.json"),
            ),
            None,
        )
    pipeline.finalize()


def write_report(path: Path, cfg: BacktestConfig, metrics: Dict[str, float], bench_metrics: Dict[str, float], diagnostics: Optional[Dict[str, float]] = None, benchmark_comparison: Optional[pd.DataFrame] = None, factor_regression: Optional[pd.DataFrame] = None, statistical_diagnostics: Optional[pd.DataFrame] = None, bootstrap_intervals: Optional[pd.DataFrame] = None) -> None:
    lines = []
    lines.append("Benchmark-Aware Active Alpha Model Report")
    lines.append("=========================")
    lines.append("")
    lines.append("Configuration")
    lines.append("-------------")
    for k, v in cfg.__dict__.items():
        lines.append(f"{k}: {v}")
    lines.append("")
    lines.append("Strategy metrics")
    lines.append("----------------")
    for k, v in metrics.items():
        lines.append(f"{k}: {v:.6f}" if isinstance(v, (float, np.floating)) else f"{k}: {v}")
    lines.append("")
    lines.append("Benchmark metrics")
    lines.append("-----------------")
    for k, v in bench_metrics.items():
        lines.append(f"{k}: {v:.6f}" if isinstance(v, (float, np.floating)) else f"{k}: {v}")
    if diagnostics:
        lines.append("")
        lines.append("Portfolio diagnostics")
        lines.append("---------------------")
        for k, v in diagnostics.items():
            lines.append(f"{k}: {v:.6f}" if isinstance(v, (float, np.floating, int)) else f"{k}: {v}")
    if benchmark_comparison is not None and not benchmark_comparison.empty:
        lines.append("")
        lines.append("Benchmark comparison")
        lines.append("--------------------")
        for _, row in benchmark_comparison.iterrows():
            lines.append(
                f"{row.get('benchmark')}: CAGR diff={_safe_metric_value(row.get('cagr_diff')):.6f}, "
                f"IR={_safe_metric_value(row.get('information_ratio')):.6f}, "
                f"corr={_safe_metric_value(row.get('correlation'), np.nan):.6f}, "
                f"beta={_safe_metric_value(row.get('beta_to_benchmark'), np.nan):.6f}"
            )
    if factor_regression is not None and not factor_regression.empty:
        lines.append("")
        lines.append("Factor proxy regression")
        lines.append("-----------------------")
        r2_vals = factor_regression.get("r_squared")
        if r2_vals is not None and len(r2_vals):
            lines.append(f"r_squared: {_safe_metric_value(pd.Series(r2_vals).dropna().iloc[0] if pd.Series(r2_vals).dropna().size else np.nan, np.nan):.6f}")
        for _, row in factor_regression.iterrows():
            lines.append(f"{row.get('term')}: coefficient={_safe_metric_value(row.get('coefficient'), np.nan):.6f}, annualized={_safe_metric_value(row.get('annualized'), np.nan):.6f}")
    if statistical_diagnostics is not None and not statistical_diagnostics.empty:
        lines.append("")
        lines.append("Statistical diagnostics")
        lines.append("-----------------------")
        for _, row in statistical_diagnostics.iterrows():
            lines.append(
                f"{row.get('series')}.{row.get('metric')}: value={_safe_metric_value(row.get('value'), np.nan):.6f}, "
                f"annualized={_safe_metric_value(row.get('annualized'), np.nan):.6f}, "
                f"NW_t={_safe_metric_value(row.get('newey_west_tstat'), np.nan):.3f}"
            )
    if bootstrap_intervals is not None and not bootstrap_intervals.empty:
        lines.append("")
        lines.append("Bootstrap performance intervals")
        lines.append("-------------------------------")
        for _, row in bootstrap_intervals.iterrows():
            lines.append(
                f"{row.get('series')}.{row.get('metric')}: "
                f"p05={_safe_metric_value(row.get('p05'), np.nan):.6f}, "
                f"p50={_safe_metric_value(row.get('p50'), np.nan):.6f}, "
                f"p95={_safe_metric_value(row.get('p95'), np.nan):.6f}"
            )
    lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("This is a research/paper-trading model. It is not a guarantee of outperformance.")
    lines.append("Before live use: validate data quality, transaction costs, tax effects, slippage, and broker execution.")
    lines.append("DIY point-in-time liquidity universe reduces look-ahead from static current holdings, but it is not a delisting-complete institutional universe.")
    lines.append("Gross exposure is now a hard validated constraint via max_gross_exposure.")
    lines.append("Backtest transaction costs use Trading 212 assumptions only. Frequent signal updates are combined with threshold trading, buy/hold spread logic, exposure recovery and capital-aware execution controls.")
    path.write_text("\n".join(lines), encoding="utf-8")


def maybe_plot(out_dir: Path, strategy_returns: pd.Series, benchmark_returns: pd.Series) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return
    common = strategy_returns.dropna().index.intersection(benchmark_returns.dropna().index)
    if len(common) < 10:
        return
    eq = (1 + strategy_returns.reindex(common).fillna(0)).cumprod()
    beq = (1 + benchmark_returns.reindex(common).fillna(0)).cumprod()
    fig = plt.figure(figsize=(10, 5))
    plt.plot(eq.index, eq.values, label="Strategy")
    plt.plot(beq.index, beq.values, label="Benchmark")
    plt.title("Equity Curve")
    plt.xlabel("Date")
    plt.ylabel("Growth of 1.0")
    plt.legend()
    plt.tight_layout()
    fig.savefig(out_dir / "equity_curve.png", dpi=150)
    plt.close(fig)

