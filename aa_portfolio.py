from __future__ import annotations

import math
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig, _clip_float, normalize_yfinance_ticker
from aa_constants import (
    VALIDATION_TOL,
    deduplicate_dataframe_columns,
    ticker_to_correlation_cluster,
    ticker_to_issuer,
    ticker_to_sector,
)
from aa_dashboard import RunDashboard
from aa_features import safe_rank_pct
from aa_parallel import (
    _CTX,
    _estimate_dataframe_gb,
    _parallel_map_unordered,
    _parallel_worker_bootstrap,
    parallel_execution_enabled,
    resolve_parallel_workers,
)

_SNAPSHOT_INDEX_CACHE: Dict[int, pd.DataFrame] = {}


def _snapshot_ticker_index(snapshot: pd.DataFrame) -> pd.DataFrame:
    """Cache ticker-indexed snapshot metadata for repeated constraint checks."""
    if snapshot is None or snapshot.empty or "ticker" not in snapshot.columns:
        return pd.DataFrame()
    cache_key = id(snapshot)
    hit = _SNAPSHOT_INDEX_CACHE.get(cache_key)
    if hit is not None:
        return hit
    meta = snapshot.drop_duplicates("ticker").set_index("ticker")
    _SNAPSHOT_INDEX_CACHE[cache_key] = meta
    if len(_SNAPSHOT_INDEX_CACHE) > 1024:
        _SNAPSHOT_INDEX_CACHE.clear()
    return meta


def _selection_rank_map(ranked: pd.DataFrame) -> Dict[str, int]:
    if ranked is None or ranked.empty or "selection_score" not in ranked.columns or "ticker" not in ranked.columns:
        return {}
    table = ranked.dropna(subset=["selection_score"])
    if table.empty:
        return {}
    if not table["selection_score"].is_monotonic_decreasing:
        table = table.sort_values("selection_score", ascending=False)
    ranks = np.arange(1, len(table) + 1, dtype=np.int32)
    return dict(zip(table["ticker"].astype(str), ranks))



def cap_weights(raw: pd.Series, max_position: float, target_exposure: float) -> pd.Series:
    raw = raw.clip(lower=0).replace([np.inf, -np.inf], np.nan).dropna()
    if raw.empty or raw.sum() <= 0 or target_exposure <= 0:
        return pd.Series(dtype=float)
    w = raw / raw.sum() * target_exposure
    # Iterative cap-and-redistribute.
    for _ in range(20):
        over = w > max_position
        if not over.any():
            break
        capped_sum = max_position * over.sum()
        remainder = target_exposure - capped_sum
        w.loc[over] = max_position
        under = ~over
        if remainder <= 0 or w.loc[under].sum() <= 0:
            w.loc[under] = 0.0
            break
        w.loc[under] = w.loc[under] / w.loc[under].sum() * remainder
    # If caps make exact target impossible, allow lower exposure.
    w = w.clip(upper=max_position)
    if w.sum() > target_exposure:
        w *= target_exposure / w.sum()
    return w


def portfolio_diagnostics(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig) -> Dict[str, float]:
    """Return objective portfolio diagnostics for any target-weight vector.

    Diagnostics are computed from the same metadata used by allocation and hard
    validation. Cluster diagnostics now support static, dynamic and
    both-restrictive cluster caps.
    """
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    if weights.empty:
        return {
            "portfolio_exposure": 0.0,
            "portfolio_beta": 0.0,
            "max_position_weight": 0.0,
            "max_issuer_weight": 0.0,
            "max_sector_weight": 0.0,
            "max_correlation_cluster_weight": 0.0,
            "max_static_cluster_weight": 0.0,
            "max_dynamic_cluster_weight": 0.0,
            "n_positions": 0.0,
            "constraint_violations": 0.0,
        }

    meta = _snapshot_ticker_index(snapshot)
    meta = meta.reindex(weights.index)
    meta = _ensure_cluster_columns(meta)
    sectors = meta["sector"].fillna("Unknown") if "sector" in meta else pd.Series("Unknown", index=weights.index)
    issuers = meta["issuer"].fillna(pd.Series(weights.index, index=weights.index)) if "issuer" in meta else pd.Series(weights.index, index=weights.index)
    betas = pd.to_numeric(meta["beta_252"], errors="coerce") if "beta_252" in meta else pd.Series(np.nan, index=weights.index)
    completion_ticker = _benchmark_completion_ticker(cfg)
    if completion_ticker in weights.index:
        # Treat the benchmark-completion sleeve as market beta, not as an active single-stock issuer/cluster.
        betas.loc[completion_ticker] = 1.0 if not np.isfinite(float(betas.loc[completion_ticker]) if pd.notna(betas.loc[completion_ticker]) else np.nan) else float(betas.loc[completion_ticker])
    active_mask = pd.Series([not _is_benchmark_completion_ticker(tk, cfg) for tk in weights.index], index=weights.index)
    active_weights = weights[active_mask]
    active_sectors = sectors.reindex(active_weights.index)
    active_issuers = issuers.reindex(active_weights.index)
    active_meta = meta.reindex(active_weights.index)

    sector_weight = active_weights.groupby(active_sectors).sum() if not active_weights.empty else pd.Series(dtype=float)
    issuer_weight = active_weights.groupby(active_issuers).sum() if not active_weights.empty else pd.Series(dtype=float)
    known_sector_weight = sector_weight.drop(labels=["Unknown", ""], errors="ignore")
    unknown_sector_weight = float(sector_weight.get("Unknown", 0.0) if "Unknown" in sector_weight.index else 0.0)
    cluster_diag = _cluster_cap_diagnostics(active_weights, active_meta, cfg)
    portfolio_beta = float((weights * betas.fillna(0.0)).sum())
    portfolio_exposure = float(weights.sum())

    tol = VALIDATION_TOL
    violations = 0
    if (weights < -tol).any():
        violations += 1
    if getattr(cfg, "max_gross_exposure", 0) and portfolio_exposure > float(cfg.max_gross_exposure) + tol:
        violations += 1
    if (not active_weights.empty) and active_weights.max() > cfg.max_position + tol:
        violations += 1
    if not issuer_weight.empty and issuer_weight.max() > cfg.max_issuer + tol:
        violations += 1
    if not known_sector_weight.empty and known_sector_weight.max() > cfg.max_sector + tol:
        violations += 1
    if unknown_sector_weight > cfg.max_sector + tol:
        violations += 1
    violations += int(cluster_diag.get("cluster_constraint_violations", 0.0))
    if cfg.max_portfolio_beta and portfolio_beta > cfg.max_portfolio_beta + tol:
        violations += 1

    clusters_for_unknown = meta.get("correlation_cluster", pd.Series("Unknown", index=weights.index)).fillna("Unknown").astype(str)
    sector_unknown = sectors.fillna("Unknown").astype(str).eq("Unknown")
    cluster_unknown = clusters_for_unknown.eq("Unknown")
    issuer_unknown = issuers.fillna("Unknown").astype(str).eq("Unknown")
    return {
        "portfolio_exposure": portfolio_exposure,
        "portfolio_beta": portfolio_beta,
        "max_position_weight": float(active_weights.max()) if not active_weights.empty else 0.0,
        "max_issuer_weight": float(issuer_weight.max()) if not issuer_weight.empty else 0.0,
        "max_sector_weight": float(known_sector_weight.max()) if not known_sector_weight.empty else 0.0,
        "max_correlation_cluster_weight": float(cluster_diag.get("max_correlation_cluster_weight", 0.0)),
        "max_static_cluster_weight": float(cluster_diag.get("max_static_cluster_weight", 0.0)),
        "max_dynamic_cluster_weight": float(cluster_diag.get("max_dynamic_cluster_weight", 0.0)),
        "n_positions": float((weights > 1e-10).sum()),
        "constraint_violations": float(violations),
        "gross_exposure_binding": float(bool(getattr(cfg, "max_gross_exposure", 0)) and portfolio_exposure >= float(cfg.max_gross_exposure) - 1e-4),
        "max_position_binding": float((not active_weights.empty) and active_weights.max() >= cfg.max_position - 1e-4),
        "max_issuer_binding": float((not issuer_weight.empty) and issuer_weight.max() >= cfg.max_issuer - 1e-4),
        "max_sector_binding": float((not known_sector_weight.empty) and known_sector_weight.max() >= cfg.max_sector - 1e-4),
        "max_cluster_binding": float(max(cluster_diag.get("static_cluster_binding", 0.0), cluster_diag.get("dynamic_cluster_binding", 0.0))),
        "max_static_cluster_binding": float(cluster_diag.get("static_cluster_binding", 0.0)),
        "max_dynamic_cluster_binding": float(cluster_diag.get("dynamic_cluster_binding", 0.0)),
        "max_beta_binding": float(bool(cfg.max_portfolio_beta) and portfolio_beta >= float(cfg.max_portfolio_beta) - 1e-4),
        "unknown_sector_weight": float(weights.reindex(sectors.index[sector_unknown]).fillna(0.0).sum()) if sector_unknown.any() else 0.0,
        "unknown_cluster_weight": float(weights.reindex(clusters_for_unknown.index[cluster_unknown]).fillna(0.0).sum()) if cluster_unknown.any() else 0.0,
        "unknown_issuer_weight": float(weights.reindex(issuers.index[issuer_unknown]).fillna(0.0).sum()) if issuer_unknown.any() else 0.0,
        "n_unknown_sector_positions": float(sector_unknown.sum()),
        "n_unknown_cluster_positions": float(cluster_unknown.sum()),
        "n_unknown_issuer_positions": float(issuer_unknown.sum()),
    }

def _aligned_portfolio_metadata(weights: pd.Series, snapshot: pd.DataFrame) -> pd.DataFrame:
    """Ticker metadata aligned to a portfolio vector for diagnostics and reporting."""
    idx = pd.Index([str(x).upper().strip() for x in weights.index], name="ticker")
    meta = pd.DataFrame(index=idx)
    if snapshot is not None and not snapshot.empty and "ticker" in snapshot.columns:
        src = snapshot.copy()
        src["ticker"] = src["ticker"].astype(str).str.upper().str.strip()
        src = src.drop_duplicates("ticker").set_index("ticker")
        meta = meta.join(src.reindex(idx), how="left", rsuffix="_src")
    if "sector" not in meta.columns:
        meta["sector"] = [ticker_to_sector(tk) for tk in idx]
    else:
        fallback = pd.Series([ticker_to_sector(tk) for tk in idx], index=idx)
        meta["sector"] = meta["sector"].replace("", np.nan).fillna(fallback).fillna("Unknown")
    if "issuer" not in meta.columns:
        meta["issuer"] = [ticker_to_issuer(tk) for tk in idx]
    else:
        fallback = pd.Series([ticker_to_issuer(tk) for tk in idx], index=idx)
        meta["issuer"] = meta["issuer"].replace("", np.nan).fillna(fallback).fillna(pd.Series(idx, index=idx))
    if "correlation_cluster" not in meta.columns:
        meta["correlation_cluster"] = [ticker_to_correlation_cluster(tk, meta.loc[tk, "sector"]) for tk in idx]
    else:
        fallback = pd.Series([ticker_to_correlation_cluster(tk, meta.loc[tk, "sector"]) for tk in idx], index=idx)
        meta["correlation_cluster"] = meta["correlation_cluster"].replace("", np.nan).fillna(fallback).fillna("Unknown")
    if "beta_252" not in meta.columns:
        meta["beta_252"] = np.nan
    meta["beta_252"] = pd.to_numeric(meta["beta_252"], errors="coerce")
    return meta



def _ensure_cluster_columns(meta: pd.DataFrame) -> pd.DataFrame:
    """Ensure static, dynamic and active correlation cluster columns exist.

    The static cluster remains the auditable thematic map. Dynamic clusters are
    optional rolling-correlation diagnostics. Risk controls can enforce either or
    both through cfg.cluster_constraint_mode.
    """
    out = meta.copy()
    idx = out.index
    if "sector" not in out.columns:
        out["sector"] = [ticker_to_sector(tk) for tk in idx]
    else:
        fallback_sector = pd.Series([ticker_to_sector(tk) for tk in idx], index=idx)
        out["sector"] = out["sector"].replace("", np.nan).fillna(fallback_sector).fillna("Unknown")
    static_fallback = pd.Series([ticker_to_correlation_cluster(tk, out.loc[tk, "sector"]) for tk in idx], index=idx)
    if "correlation_cluster_static" not in out.columns:
        if "correlation_cluster" in out.columns:
            out["correlation_cluster_static"] = out["correlation_cluster"].replace("", np.nan).fillna(static_fallback)
        else:
            out["correlation_cluster_static"] = static_fallback
    else:
        out["correlation_cluster_static"] = out["correlation_cluster_static"].replace("", np.nan).fillna(static_fallback)
    if "correlation_cluster_dynamic" not in out.columns:
        out["correlation_cluster_dynamic"] = ""
    out["correlation_cluster_dynamic"] = out["correlation_cluster_dynamic"].fillna("").astype(str)
    if "correlation_cluster" not in out.columns:
        out["correlation_cluster"] = out["correlation_cluster_static"]
    out["correlation_cluster"] = out["correlation_cluster"].replace("", np.nan).fillna(out["correlation_cluster_static"]).fillna("Unknown")
    return out


def _active_cluster_specs(meta: pd.DataFrame, cfg: BacktestConfig) -> list[tuple[pd.Series, float, str, bool]]:
    """Return active cluster constraints as (labels, cap, label, include_unknown).

    both_restrictive enforces the static thematic cap and the dynamic statistical
    cap simultaneously. This prevents dynamic clusters from replacing the manual
    AI/Semis-style guardrail.
    """
    m = _ensure_cluster_columns(meta)
    mode = str(getattr(cfg, "cluster_constraint_mode", "both_restrictive") or "both_restrictive").lower().strip()
    if mode not in {"static_only", "dynamic_only", "both_restrictive"}:
        mode = "both_restrictive"
    legacy_cap = float(getattr(cfg, "max_correlation_cluster", 0.0) or 0.0)
    static_cap = float(getattr(cfg, "static_cluster_cap", 0.0) or 0.0) or legacy_cap
    dynamic_cap = float(getattr(cfg, "dynamic_cluster_cap", 0.0) or 0.0) or legacy_cap
    # Backward compatibility: when legacy max_correlation_cluster is explicitly
    # set lower than the static/dynamic defaults, it remains the stricter cap.
    if legacy_cap > 0:
        static_cap = min(static_cap, legacy_cap) if static_cap > 0 else legacy_cap
        dynamic_cap = min(dynamic_cap, legacy_cap) if dynamic_cap > 0 else legacy_cap
    specs: list[tuple[pd.Series, float, str, bool]] = []
    if mode in {"static_only", "both_restrictive"} and static_cap > 0:
        specs.append((m["correlation_cluster_static"].fillna("Unknown").astype(str), static_cap, "static_cluster", True))
    if mode in {"dynamic_only", "both_restrictive"} and dynamic_cap > 0:
        dyn = m["correlation_cluster_dynamic"].fillna("").astype(str).replace("", "Unknown")
        if (dyn != "Unknown").any():
            specs.append((dyn, dynamic_cap, "dynamic_cluster", True))
        elif mode == "dynamic_only":
            # Fallback keeps dynamic_only usable before dynamic diagnostics are available.
            specs.append((m["correlation_cluster"].fillna("Unknown").astype(str), dynamic_cap, "dynamic_cluster", True))
    if not specs and legacy_cap > 0:
        specs.append((m["correlation_cluster"].fillna("Unknown").astype(str), legacy_cap, "correlation_cluster", True))
    return specs


def _cluster_cap_diagnostics(weights: pd.Series, meta: pd.DataFrame, cfg: BacktestConfig) -> dict[str, float]:
    out = {
        "max_correlation_cluster_weight": 0.0,
        "max_static_cluster_weight": 0.0,
        "max_dynamic_cluster_weight": 0.0,
        "cluster_constraint_violations": 0.0,
        "static_cluster_binding": 0.0,
        "dynamic_cluster_binding": 0.0,
    }
    if weights is None or weights.empty:
        return out
    tol = VALIDATION_TOL
    for labels, cap, label, include_unknown in _active_cluster_specs(meta, cfg):
        gsum = weights.groupby(labels.reindex(weights.index).fillna("Unknown")).sum()
        if not include_unknown:
            gsum = gsum.drop(labels=["Unknown", ""], errors="ignore")
        maxw = float(gsum.max()) if not gsum.empty else 0.0
        if label == "static_cluster":
            out["max_static_cluster_weight"] = max(out["max_static_cluster_weight"], maxw)
            out["static_cluster_binding"] = max(out["static_cluster_binding"], float(cap > 0 and maxw >= cap - 1e-4))
        elif label == "dynamic_cluster":
            out["max_dynamic_cluster_weight"] = max(out["max_dynamic_cluster_weight"], maxw)
            out["dynamic_cluster_binding"] = max(out["dynamic_cluster_binding"], float(cap > 0 and maxw >= cap - 1e-4))
        out["max_correlation_cluster_weight"] = max(out["max_correlation_cluster_weight"], maxw)
        if cap > 0 and maxw > cap + tol:
            out["cluster_constraint_violations"] += 1.0
    return out


def effective_beta_cap_from_snapshot(snapshot: pd.DataFrame, risk_on: bool, cfg: BacktestConfig, exposure_diag: Optional[Dict[str, float]] = None) -> float:
    """Return the rebalance-specific beta cap.

    fixed mode returns cfg.max_portfolio_beta. dynamic mode tightens beta in
    risk-off and permits more beta only in strong, broad risk-on regimes.
    """
    base = float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0)
    if base <= 0:
        return 0.0
    mode = str(getattr(cfg, "beta_cap_mode", "dynamic") or "dynamic").lower().strip()
    if mode == "fixed":
        return base
    def scalar(name: str, default: float) -> float:
        try:
            if snapshot is not None and name in snapshot.columns and snapshot[name].notna().any():
                v = float(pd.to_numeric(snapshot[name], errors="coerce").dropna().iloc[0])
                return v if np.isfinite(v) else default
        except Exception:
            pass
        return default
    mtrend = scalar("market_trend_200", 1.0)
    mret63 = scalar("market_ret_63", 0.0)
    breadth = float((exposure_diag or {}).get("signal_breadth_positive", 0.0) or 0.0)
    risk_off_cap = float(getattr(cfg, "dynamic_beta_risk_off", 1.10) or 1.10)
    normal_cap = float(getattr(cfg, "dynamic_beta_normal", base) or base)
    risk_on_cap = float(getattr(cfg, "dynamic_beta_risk_on", 1.35) or 1.35)
    strong_cap = float(getattr(cfg, "dynamic_beta_strong", 1.45) or 1.45)
    if not risk_on:
        return max(0.0, min(base, risk_off_cap))
    cap = max(base, normal_cap)
    if mtrend > 1.05 and mret63 > 0.03 and breadth > 0.35:
        cap = max(cap, risk_on_cap)
    if mtrend > 1.10 and mret63 > 0.08 and breadth > 0.45:
        cap = max(cap, strong_cap)
    return min(cap, float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0) * strong_cap)

def constraint_binding_metrics(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig, *, tol: float = 1e-4) -> Dict[str, float]:
    """Return explicit binding / mapping diagnostics for a target-weight vector."""
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    out: Dict[str, float] = {
        "gross_exposure_binding": 0.0,
        "max_position_binding": 0.0,
        "max_issuer_binding": 0.0,
        "max_sector_binding": 0.0,
        "max_cluster_binding": 0.0,
        "max_beta_binding": 0.0,
        "unknown_sector_weight": 0.0,
        "unknown_cluster_weight": 0.0,
        "unknown_issuer_weight": 0.0,
        "n_unknown_sector_positions": 0.0,
        "n_unknown_cluster_positions": 0.0,
        "n_unknown_issuer_positions": 0.0,
    }
    if weights.empty:
        return out
    meta = _aligned_portfolio_metadata(weights, snapshot)
    diag = portfolio_diagnostics(weights, snapshot, cfg)
    gross_cap = float(getattr(cfg, "max_gross_exposure", 0.0) or 0.0)
    if gross_cap > 0:
        out["gross_exposure_binding"] = float(diag.get("portfolio_exposure", 0.0) >= gross_cap - tol)
    out["max_position_binding"] = float(float(getattr(cfg, "max_position", 0.0) or 0.0) > 0 and diag.get("max_position_weight", 0.0) >= float(getattr(cfg, "max_position", 0.0)) - tol)
    out["max_issuer_binding"] = float(float(getattr(cfg, "max_issuer", 0.0) or 0.0) > 0 and diag.get("max_issuer_weight", 0.0) >= float(getattr(cfg, "max_issuer", 0.0)) - tol)
    out["max_sector_binding"] = float(float(getattr(cfg, "max_sector", 0.0) or 0.0) > 0 and diag.get("max_sector_weight", 0.0) >= float(getattr(cfg, "max_sector", 0.0)) - tol)
    out["max_cluster_binding"] = float(float(getattr(cfg, "max_correlation_cluster", 0.0) or 0.0) > 0 and diag.get("max_correlation_cluster_weight", 0.0) >= float(getattr(cfg, "max_correlation_cluster", 0.0)) - tol)
    out["max_beta_binding"] = float(float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0) > 0 and diag.get("portfolio_beta", 0.0) >= float(getattr(cfg, "max_portfolio_beta", 0.0)) - tol)
    sectors = meta["sector"].fillna("Unknown").astype(str)
    clusters = meta["correlation_cluster"].fillna("Unknown").astype(str)
    issuers = meta["issuer"].fillna("Unknown").astype(str)
    sector_unknown = sectors.eq("Unknown") | sectors.eq("")
    cluster_unknown = clusters.eq("Unknown") | clusters.eq("")
    issuer_unknown = issuers.eq("Unknown") | issuers.eq("")
    out["unknown_sector_weight"] = float(weights.reindex(meta.index[sector_unknown]).fillna(0.0).sum()) if sector_unknown.any() else 0.0
    out["unknown_cluster_weight"] = float(weights.reindex(meta.index[cluster_unknown]).fillna(0.0).sum()) if cluster_unknown.any() else 0.0
    out["unknown_issuer_weight"] = float(weights.reindex(meta.index[issuer_unknown]).fillna(0.0).sum()) if issuer_unknown.any() else 0.0
    out["n_unknown_sector_positions"] = float(sector_unknown.sum())
    out["n_unknown_cluster_positions"] = float(cluster_unknown.sum())
    out["n_unknown_issuer_positions"] = float(issuer_unknown.sum())
    return out


def _allocation_exposure_for_stage(candidates: pd.DataFrame, raw: pd.Series, cfg: BacktestConfig, target_exposure: float, stage: str) -> float:
    """Diagnostic-only exposure after progressively enabling constraint families."""
    try:
        if candidates is None or candidates.empty or raw is None or raw.empty:
            return 0.0
        if stage == "position":
            c = replace(cfg, max_issuer=1.0, max_sector=1.0, max_correlation_cluster=0.0, max_portfolio_beta=0.0)
        elif stage == "issuer":
            c = replace(cfg, max_sector=1.0, max_correlation_cluster=0.0, max_portfolio_beta=0.0)
        elif stage == "sector":
            c = replace(cfg, max_correlation_cluster=0.0, max_portfolio_beta=0.0)
        elif stage == "cluster":
            c = replace(cfg, max_portfolio_beta=0.0)
        else:
            c = cfg
        w = allocate_with_caps(candidates, raw, c, target_exposure)
        return float(w.sum()) if w is not None and not w.empty else 0.0
    except Exception:
        return np.nan


def classify_cash_reason(row: Dict[str, object]) -> Dict[str, object]:
    """Attribute residual cash/exposure gap to the largest observable constraint step."""
    def f(key: str, default: float = 0.0) -> float:
        try:
            val = float(row.get(key, default))
            return val if np.isfinite(val) else default
        except Exception:
            return default
    desired = f("desired_exposure", f("regime_target_exposure", f("target_exposure", 0.0)))
    final = f("final_validated_exposure", f("portfolio_exposure", 0.0))
    before = f("exposure_before_constraints", desired)
    pos = f("exposure_after_position_cap", before)
    issuer = f("exposure_after_issuer_cap", pos)
    sector = f("exposure_after_sector_cap", issuer)
    cluster = f("exposure_after_cluster_cap", sector)
    beta = f("exposure_after_beta_cap", f("target_exposure_before_trade_controls", cluster))
    buy_hold = f("target_exposure_after_buy_hold", beta)
    controls = f("exposure_after_trade_controls", buy_hold)
    tail = f("exposure_after_tail_prune", controls)
    min_trade = f("exposure_after_min_trade", tail)
    gap = max(0.0, desired - final)
    drops = {
        "position_cap": max(0.0, before - pos),
        "issuer_cap": max(0.0, pos - issuer),
        "sector_cap": max(0.0, issuer - sector),
        "cluster_cap": max(0.0, sector - cluster),
        "beta_cap": max(0.0, cluster - beta),
        "buy_hold_spread": max(0.0, beta - buy_hold),
        "trade_controls": max(0.0, buy_hold - controls),
        "tail_prune": max(0.0, controls - tail),
        "min_trade_filter": max(0.0, tail - min_trade),
        "final_projection": max(0.0, min_trade - final),
    }
    risk_on = bool(row.get("risk_on", False))
    risk_off_cash = max(0.0, float(getattr(row, "get", lambda *a: 0)("max_gross_exposure", 1.0)) - desired) if not risk_on else 0.0
    reason = "fully_invested_or_no_gap"
    if gap > 1e-6:
        reason = max(drops.items(), key=lambda kv: kv[1])[0]
        if drops.get(reason, 0.0) <= 1e-6:
            reason = "signal_shortage_or_unattributed_constraints"
    if not risk_on and desired < 0.999:
        # Risk-off may be a deliberate high-level exposure reduction even when later caps also bind.
        reason = "risk_off_regime" if gap >= 1e-6 else "risk_off_regime_target_met"
    return {
        "cash_gap_vs_desired_exposure": float(gap),
        "cash_reason": reason,
        "cash_due_to_position_cap": float(drops["position_cap"]),
        "cash_due_to_issuer_cap": float(drops["issuer_cap"]),
        "cash_due_to_sector_cap": float(drops["sector_cap"]),
        "cash_due_to_cluster_cap": float(drops["cluster_cap"]),
        "cash_due_to_beta_cap": float(drops["beta_cap"]),
        "cash_due_to_buy_hold_spread": float(drops["buy_hold_spread"]),
        "cash_due_to_trade_controls": float(drops["trade_controls"]),
        "cash_due_to_tail_prune": float(drops["tail_prune"]),
        "cash_due_to_min_trade_filter": float(drops["min_trade_filter"]),
        "cash_due_to_final_projection": float(drops["final_projection"]),
        "cash_due_to_signal_shortage": float(max(0.0, gap - sum(drops.values()))),
        "cash_due_to_risk_off_regime": float(max(0.0, 1.0 - desired) if not risk_on else 0.0),
    }


def write_constraint_binding_history(out_dir: Path, decisions: pd.DataFrame) -> Optional[Path]:
    if decisions is None or decisions.empty or "rebalance_date" not in decisions.columns:
        return None
    rb = decisions.drop_duplicates("rebalance_date").copy()
    preferred = [
        "rebalance_date", "risk_on", "desired_exposure", "regime_target_exposure", "exposure_controller_score", "signal_breadth_positive", "avg_alpha_lcb", "n_positive_candidates_for_exposure", "exposure_after_cash_filler", "cash_filler_enabled", "cash_filler_added_weight", "cash_filler_n_names", "target_exposure_before_trade_controls",
        "target_exposure_after_buy_hold", "exposure_after_trade_controls", "exposure_after_tail_prune",
        "exposure_after_min_trade", "final_validated_exposure", "final_portfolio_exposure", "final_portfolio_beta",
        "final_constraint_violations", "final_n_positions", "selected_target_exposure_pre_execution",
        "portfolio_exposure", "portfolio_beta",
        "gross_exposure_binding", "max_position_binding", "max_issuer_binding", "max_sector_binding",
        "max_cluster_binding", "max_beta_binding", "max_position_binding_after_prune", "max_sector_binding_after_prune",
        "max_cluster_binding_after_prune", "max_beta_binding_after_prune", "cash_reason", "cash_gap_vs_desired_exposure",
        "cash_due_to_beta_cap", "cash_due_to_cluster_cap", "cash_due_to_signal_shortage", "cash_due_to_trade_controls",
        "cash_due_to_min_trade_filter", "n_candidates", "n_eligible_candidates", "n_selected_candidates",
        "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol", "unknown_sector_weight",
        "unknown_cluster_weight", "unknown_issuer_weight", "n_unknown_sector_positions", "n_unknown_cluster_positions",
        "n_unknown_issuer_positions", "n_positions", "constraint_violations",
    ]
    cols = [c for c in preferred if c in rb.columns]
    path = out_dir / "constraint_binding_history.csv"
    rb[cols].to_csv(path, index=False)
    return path


def data_quality_report(features: pd.DataFrame) -> pd.DataFrame:
    """Lightweight PIT data-quality audit derived from the feature table."""
    rows: List[Dict[str, object]] = []
    if features is None or features.empty:
        return pd.DataFrame(columns=["check", "value", "severity"])
    def add(check: str, value: object, severity: str = "info") -> None:
        rows.append({"check": check, "value": value, "severity": severity})
    add("n_rows", int(len(features)))
    add("n_tickers", int(features["ticker"].nunique()) if "ticker" in features.columns else 0)
    add("start_date", str(pd.to_datetime(features["date"], errors="coerce").min().date()) if "date" in features.columns else "")
    add("end_date", str(pd.to_datetime(features["date"], errors="coerce").max().date()) if "date" in features.columns else "")
    for col in ["close", "adv_20", "vol_20", "beta_252", "target"]:
        if col in features.columns:
            miss = int(pd.to_numeric(features[col], errors="coerce").isna().sum())
            add(f"missing_{col}", miss, "warn" if miss else "info")
    if {"ticker", "date"}.issubset(features.columns):
        dup = int(features.duplicated(["ticker", "date"]).sum())
        add("duplicate_ticker_date_rows", dup, "warn" if dup else "info")
    if "ret_1" in features.columns:
        r = pd.to_numeric(features["ret_1"], errors="coerce")
        extreme = int((r.abs() > 0.50).sum())
        add("extreme_abs_daily_returns_gt_50pct", extreme, "warn" if extreme else "info")
        zero = int((r == 0).sum())
        add("zero_daily_return_rows", zero, "info")
    elif "close" in features.columns and {"ticker", "date"}.issubset(features.columns):
        df = features[["ticker", "date", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df.sort_values(["ticker", "date"], inplace=True)
        rr = df.groupby("ticker")["close"].pct_change()
        add("extreme_abs_close_returns_gt_50pct", int((rr.abs() > 0.50).sum()), "warn" if int((rr.abs() > 0.50).sum()) else "info")
    for col in ["in_universe", "membership_allowed"]:
        if col in features.columns:
            val = int((~features[col].fillna(False).astype(bool)).sum())
            add(f"false_{col}_rows", val, "info")
    return pd.DataFrame(rows)


def unknown_mapping_rows(df: pd.DataFrame, *, weight_col: str = "target_weight") -> Dict[str, pd.DataFrame]:
    if df is None or df.empty or "ticker" not in df.columns:
        empty = pd.DataFrame(columns=["ticker", "weight", "sector", "issuer", "correlation_cluster"])
        return {"sector": empty.copy(), "issuer": empty.copy(), "cluster": empty.copy()}
    out = df.copy()
    out["ticker"] = out["ticker"].astype(str).str.upper().str.strip()
    if weight_col not in out.columns:
        out[weight_col] = 0.0
    out["weight"] = pd.to_numeric(out[weight_col], errors="coerce").fillna(0.0)
    if "sector" not in out.columns:
        out["sector"] = out["ticker"].map(ticker_to_sector)
    if "issuer" not in out.columns:
        out["issuer"] = out["ticker"].map(ticker_to_issuer)
    if "correlation_cluster" not in out.columns:
        out["correlation_cluster"] = [ticker_to_correlation_cluster(tk, sec) for tk, sec in zip(out["ticker"], out["sector"])]
    cols = [c for c in ["ticker", "weight", "sector", "issuer", "correlation_cluster", "signal_date", "date"] if c in out.columns]
    sec = out[out["sector"].fillna("Unknown").astype(str).eq("Unknown")][cols].copy()
    iss = out[out["issuer"].fillna("Unknown").astype(str).eq("Unknown")][cols].copy()
    clu = out[out["correlation_cluster"].fillna("Unknown").astype(str).eq("Unknown")][cols].copy()
    return {"sector": sec, "issuer": iss, "cluster": clu}


def write_unknown_mapping_reports(out_dir: Path, df: pd.DataFrame, *, weight_col: str = "target_weight") -> List[Path]:
    paths: List[Path] = []
    reports = unknown_mapping_rows(df, weight_col=weight_col)
    filenames = {
        "sector": "unknown_sector_report.csv",
        "issuer": "unknown_issuer_report.csv",
        "cluster": "unknown_cluster_report.csv",
    }
    for key, rep in reports.items():
        path = out_dir / filenames[key]
        rep.to_csv(path, index=False)
        paths.append(path)
    return paths


def target_portfolio_explained(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    if "target_weight" in out.columns:
        out = out[pd.to_numeric(out["target_weight"], errors="coerce").fillna(0.0) > 0].copy()
    reason_parts = []
    for _, row in out.iterrows():
        parts = []
        try:
            if float(row.get("alpha_lcb", 0.0)) > 0:
                parts.append("positive_alpha_lcb")
        except Exception:
            pass
        try:
            if float(row.get("rank_score", 0.0)) >= 0.5:
                parts.append("above_median_rank_score")
        except Exception:
            pass
        try:
            if float(row.get("rel_strength_63", 0.0)) > 0:
                parts.append("positive_relative_strength")
        except Exception:
            pass
        if bool(row.get("eligible", False)):
            parts.append("eligible")
        reason_parts.append(";".join(parts) if parts else "selected_by_final_optimizer")
    if len(out):
        out["reason_selected"] = reason_parts
    preferred = [
        "signal_date", "ticker", "target_weight", "mu_hat", "alpha_lcb", "rank_score", "selection_score",
        "beta_252", "vol_63", "vol_20", "sector", "issuer", "correlation_cluster",
        "portfolio_beta", "max_position_weight", "max_issuer_weight", "max_sector_weight",
        "max_correlation_cluster_weight", "risk_on", "target_exposure", "eligible", "reason_selected",
    ]
    cols = [c for c in preferred if c in out.columns]
    return out[cols].sort_values("target_weight", ascending=False) if "target_weight" in out.columns else out[cols]


def _constraint_validation_errors(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig) -> List[str]:
    """Fast hard-constraint check without full diagnostic side fields."""
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    if weights.empty:
        return []
    tol = VALIDATION_TOL
    meta = _snapshot_ticker_index(snapshot).reindex(weights.index)
    meta = _ensure_cluster_columns(meta)
    sectors = meta["sector"].fillna("Unknown") if "sector" in meta.columns else pd.Series("Unknown", index=weights.index)
    issuers = meta["issuer"].fillna(pd.Series(weights.index, index=weights.index)) if "issuer" in meta.columns else pd.Series(weights.index, index=weights.index)
    betas = pd.to_numeric(meta["beta_252"], errors="coerce") if "beta_252" in meta.columns else pd.Series(np.nan, index=weights.index)
    completion_ticker = _benchmark_completion_ticker(cfg)
    if completion_ticker in weights.index:
        bval = betas.loc[completion_ticker]
        if not np.isfinite(float(bval) if pd.notna(bval) else np.nan):
            betas.loc[completion_ticker] = 1.0
    active_mask = pd.Series([not _is_benchmark_completion_ticker(tk, cfg) for tk in weights.index], index=weights.index)
    active_weights = weights[active_mask]
    errors: List[str] = []
    exposure = float(weights.sum())
    if getattr(cfg, "max_gross_exposure", 0) and exposure > float(cfg.max_gross_exposure) + tol:
        errors.append(f"gross exposure cap exceeded: {exposure:.6f} > {float(cfg.max_gross_exposure):.6f}")
    if not active_weights.empty and float(active_weights.max()) > cfg.max_position + tol:
        errors.append(f"position cap exceeded: {float(active_weights.max()):.6f} > {cfg.max_position:.6f}")
    if not active_weights.empty:
        issuer_weight = active_weights.groupby(issuers.reindex(active_weights.index)).sum()
        if not issuer_weight.empty and float(issuer_weight.max()) > cfg.max_issuer + tol:
            errors.append(f"issuer cap exceeded: {float(issuer_weight.max()):.6f} > {cfg.max_issuer:.6f}")
        sector_weight = active_weights.groupby(sectors.reindex(active_weights.index)).sum()
        known_sector_weight = sector_weight.drop(labels=["Unknown", ""], errors="ignore")
        unknown_sector_weight = float(sector_weight.get("Unknown", 0.0) if "Unknown" in sector_weight.index else 0.0)
        if not known_sector_weight.empty and float(known_sector_weight.max()) > cfg.max_sector + tol:
            errors.append(f"sector cap exceeded: {float(known_sector_weight.max()):.6f} > {cfg.max_sector:.6f}")
        if unknown_sector_weight > cfg.max_sector + tol:
            errors.append(f"unknown sector cap exceeded: {unknown_sector_weight:.6f} > {cfg.max_sector:.6f}")
    cluster_diag = _cluster_cap_diagnostics(active_weights, meta.reindex(active_weights.index), cfg)
    if cluster_diag.get("cluster_constraint_violations", 0.0) > 0:
        static_cap = float(getattr(cfg, "static_cluster_cap", 0.0) or getattr(cfg, "max_correlation_cluster", 0.0) or 0.0)
        dynamic_cap = float(getattr(cfg, "dynamic_cluster_cap", 0.0) or getattr(cfg, "max_correlation_cluster", 0.0) or 0.0)
        details = []
        if static_cap > 0 and cluster_diag.get("max_static_cluster_weight", 0.0) > static_cap + tol:
            details.append(f"static {cluster_diag.get('max_static_cluster_weight', 0.0):.6f} > {static_cap:.6f}")
        if dynamic_cap > 0 and cluster_diag.get("max_dynamic_cluster_weight", 0.0) > dynamic_cap + tol:
            details.append(f"dynamic {cluster_diag.get('max_dynamic_cluster_weight', 0.0):.6f} > {dynamic_cap:.6f}")
        if not details:
            details.append(f"max {cluster_diag.get('max_correlation_cluster_weight', 0.0):.6f}")
        errors.append("correlation cluster cap exceeded: " + "; ".join(details))
    portfolio_beta = float((weights * betas.fillna(0.0)).sum())
    if cfg.max_portfolio_beta and portfolio_beta > cfg.max_portfolio_beta + tol:
        errors.append(f"beta cap exceeded: {portfolio_beta:.6f} > {cfg.max_portfolio_beta:.6f}")
    return errors


def validate_weights(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig, *, context: str = "portfolio") -> None:
    """Hard validation for portfolio constraints.

    Raises ValueError if any hard constraint is breached. This makes allocator
    bugs explicit instead of silently leaking into the backtest. Numerical noise
    is tolerated only up to VALIDATION_TOL.
    """
    errors = _constraint_validation_errors(weights, snapshot, cfg)
    if errors:
        raise ValueError(f"Constraint validation failed for {context}: " + "; ".join(errors))



def trim_to_exposure_cap(weights: pd.Series, cfg: BacktestConfig, *, buffer: float = 1e-6) -> pd.Series:
    """Scale long weights down when total gross exposure exceeds the hard cap.

    Scaling a long-only portfolio down cannot worsen position, issuer, sector,
    cluster or beta upper bounds. It simply leaves residual cash.
    """
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    cap = float(getattr(cfg, "max_gross_exposure", 1.0) or 0.0)
    if weights.empty or cap <= 0:
        return weights
    exposure = float(weights.sum())
    if exposure <= cap - buffer:
        return weights
    scale = max((cap - buffer) / exposure, 0.0)
    weights = (weights * scale).clip(lower=0.0)
    return weights[weights > 1e-10]


def trim_to_group_caps(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig, *, buffer: float = 1e-6) -> pd.Series:
    """Scale down any marginally over-capped issuer/sector/correlation group.

    The operation only reduces long weights and therefore preserves all other
    upper-bound constraints while allowing a small cash residual. It is used as a
    final safety projection after trade controls, where prior holdings can make a
    mixed portfolio sit exactly on a group boundary.
    """
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    if weights.empty:
        return weights
    meta = _snapshot_ticker_index(snapshot).reindex(weights.index)
    sectors = meta["sector"].fillna("Unknown") if "sector" in meta else pd.Series("Unknown", index=weights.index)
    issuers = meta["issuer"].fillna(pd.Series(weights.index, index=weights.index)) if "issuer" in meta else pd.Series(weights.index, index=weights.index)
    meta = _ensure_cluster_columns(meta)

    group_specs = [(issuers, float(cfg.max_issuer), True), (sectors, float(cfg.max_sector), True)]
    group_specs.extend([(labels, cap, include_unknown) for labels, cap, _label, include_unknown in _active_cluster_specs(meta, cfg)])

    out = weights.copy()
    for _ in range(5):
        changed = False
        for groups, cap, include_unknown in group_specs:
            if cap <= 0:
                continue
            gsum = out.groupby(groups).sum()
            if not include_unknown:
                gsum = gsum.drop(labels=["Unknown"], errors="ignore")
            for g, total in gsum.items():
                if total > cap - buffer:
                    target = max(cap - buffer, 0.0)
                    if target <= 0:
                        out.loc[groups == g] = 0.0
                    else:
                        out.loc[groups == g] *= min(target / float(total), 1.0)
                    changed = True
        out = out[out > 1e-10]
        if not changed:
            break
        if out.empty:
            break
    return out[out > 1e-10]


def trim_to_beta_cap(weights: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig, *, buffer: float = 1e-6) -> pd.Series:
    """Reduce exposure slightly when weighted beta is numerically at or above the cap.

    Beta is a weighted-sum constraint. Scaling all long weights down preserves
    position, issuer and sector caps while adding cash. This is deliberately
    only a final safety projection for numerical boundary cases or beta drift
    after trade controls; it does not replace the allocator.
    """
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-10]
    if weights.empty or not cfg.max_portfolio_beta or float(cfg.max_portfolio_beta) <= 0:
        return weights
    diag = portfolio_diagnostics(weights, snapshot, cfg)
    beta = float(diag.get("portfolio_beta", 0.0))
    cap = float(cfg.max_portfolio_beta)
    if beta <= 0 or beta < cap - buffer:
        return weights
    target_beta = max(cap - buffer, 0.0)
    if target_beta <= 0:
        return pd.Series(dtype=float)
    scale = min(target_beta / beta, 1.0)
    weights = (weights * scale).clip(lower=0.0)
    return weights[weights > 1e-10]


def project_to_valid_by_blending(candidate: pd.Series, anchor: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig, *, context: str = "projection") -> pd.Series:
    """Move an invalid candidate portfolio toward a valid anchor until hard constraints pass.

    Trade controls can mix the previous portfolio with the current target. The
    previous portfolio may have been valid on the prior rebalance date but become
    invalid under today's refreshed beta estimates or metadata. Because the hard
    constraints are convex and the current target has already been validated, a
    sufficient blend toward the target restores feasibility. Turnover controls are
    subordinate to hard risk constraints.
    """
    candidate = candidate.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    anchor = anchor.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    all_names = candidate.index.union(anchor.index)
    candidate = candidate.reindex(all_names).fillna(0.0)
    anchor = anchor.reindex(all_names).fillna(0.0)

    try:
        candidate_trimmed = trim_to_exposure_cap(candidate[candidate > 1e-10], cfg)
        validate_weights(candidate_trimmed, snapshot, cfg, context=context)
        return candidate_trimmed.sort_values(ascending=False)
    except ValueError:
        pass

    # The anchor should be the freshly allocated target portfolio. If it sits
    # exactly on the beta boundary, trim an immaterial amount of exposure so
    # numerical noise cannot trip the hard validator. If it is still infeasible,
    # surface the real error instead of masking it.
    anchor = trim_to_exposure_cap(anchor[anchor > 1e-10], cfg)
    anchor = trim_to_group_caps(anchor, snapshot, cfg)
    anchor = trim_to_beta_cap(anchor, snapshot, cfg).reindex(all_names).fillna(0.0)
    validate_weights(anchor[anchor > 1e-10], snapshot, cfg, context=f"{context}_anchor")

    c_arr = candidate.to_numpy(dtype=np.float64, copy=False)
    a_arr = anchor.to_numpy(dtype=np.float64, copy=False)
    lo, hi = 0.0, 1.0
    best = anchor.copy()
    for _ in range(60):
        mid = (lo + hi) / 2.0
        trial_vals = (1.0 - mid) * c_arr + mid * a_arr
        trial = pd.Series(trial_vals, index=all_names)
        trial = trim_to_exposure_cap(trial[trial > 1e-10], cfg)
        try:
            validate_weights(trial, snapshot, cfg, context=context)
            best = trial.reindex(all_names).fillna(0.0)
            hi = mid
        except ValueError:
            lo = mid

    best = best[best > 1e-10].sort_values(ascending=False)
    best = trim_to_exposure_cap(best, cfg)
    best = trim_to_group_caps(best, snapshot, cfg)
    best = trim_to_beta_cap(best, snapshot, cfg).sort_values(ascending=False)
    validate_weights(best, snapshot, cfg, context=context)
    return best

def allocate_with_caps(candidates: pd.DataFrame, raw: pd.Series, cfg: BacktestConfig, target_exposure: float) -> pd.Series:
    """Long-only allocation with hard position, issuer, sector and optional beta caps.

    The previous greedy allocator could breach group caps when several names from
    the same issuer or sector were allocated simultaneously. This version updates
    all group capacities after every single allocation increment and validates the
    final portfolio before returning it.
    """
    if candidates.empty or raw.empty or target_exposure <= 0:
        return pd.Series(dtype=float)

    meta = candidates.drop_duplicates("ticker").set_index("ticker")
    needed_cols = {"sector", "issuer"}
    missing = needed_cols - set(meta.columns)
    if missing:
        raise ValueError(f"Candidates missing required columns: {sorted(missing)}")

    raw = raw.reindex(meta.index).clip(lower=0).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    raw = raw[raw > 0]
    if raw.empty:
        return pd.Series(dtype=float)

    weights = pd.Series(0.0, index=raw.index, dtype=float)
    gross_cap = float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0)
    target_exposure = float(min(max(target_exposure, 0.0), max(gross_cap, 0.0)))
    remaining_target = target_exposure

    betas = pd.to_numeric(meta.get("beta_252", pd.Series(np.nan, index=meta.index)), errors="coerce").fillna(0.0)
    meta = _ensure_cluster_columns(meta)

    def capacity_left(tk: str) -> float:
        sector = str(meta.loc[tk, "sector"])
        issuer = str(meta.loc[tk, "issuer"])
        pos_left = cfg.max_position - float(weights.loc[tk])
        issuer_tickers = meta.index[meta["issuer"] == issuer]
        issuer_left = cfg.max_issuer - float(weights.reindex(issuer_tickers).fillna(0.0).sum())
        if sector == "Unknown":
            sector_tickers = meta.index[meta["sector"] == "Unknown"]
            sector_left = cfg.max_sector - float(weights.reindex(sector_tickers).fillna(0.0).sum())
        else:
            sector_tickers = meta.index[meta["sector"] == sector]
            sector_left = cfg.max_sector - float(weights.reindex(sector_tickers).fillna(0.0).sum())
        cluster_left = target_exposure
        for labels, cap, _label, include_unknown in _active_cluster_specs(meta, cfg):
            cluster = str(labels.loc[tk]) if tk in labels.index else "Unknown"
            if cap > 0 and (include_unknown or cluster not in {"", "Unknown"}):
                group_weight = float(weights[labels.reindex(weights.index).fillna("Unknown") == cluster].sum())
                cluster_left = min(cluster_left, cap - group_weight)
        beta_left = target_exposure
        if cfg.max_portfolio_beta and betas.loc[tk] > 0:
            current_beta = float((weights * betas.reindex(weights.index).fillna(0.0)).sum())
            beta_left = (cfg.max_portfolio_beta - current_beta) / float(betas.loc[tk])
        return max(min(pos_left, issuer_left, sector_left, cluster_left, beta_left, remaining_target), 0.0)

    # Iteratively allocate signal-proportional desired increments. Capped names are
    # removed from the active set; uncapped names receive their desired increment
    # and remain active only if exposure still needs redistribution.
    active = list(raw.sort_values(ascending=False).index)
    for _ in range(200):
        if remaining_target <= 1e-10 or not active:
            break
        active = [tk for tk in active if capacity_left(tk) > 1e-10 and raw.loc[tk] > 0]
        if not active:
            break
        rr = raw.reindex(active).clip(lower=0)
        if rr.sum() <= 0:
            break

        desired = rr / rr.sum() * remaining_target
        capped_this_round = []
        total_added = 0.0
        for tk in rr.sort_values(ascending=False).index:
            cap = capacity_left(tk)
            if cap <= 1e-10:
                capped_this_round.append(tk)
                continue
            delta = float(min(desired.loc[tk], cap, remaining_target))
            if delta <= 1e-12:
                continue
            weights.loc[tk] += delta
            remaining_target -= delta
            total_added += delta
            if delta < float(desired.loc[tk]) - 1e-10 or capacity_left(tk) <= 1e-10:
                capped_this_round.append(tk)
            if remaining_target <= 1e-10:
                break

        active = [tk for tk in active if tk not in set(capped_this_round)]
        if total_added <= 1e-12:
            break

    weights = weights[weights > 1e-10]
    if weights.sum() > target_exposure + 1e-10:
        weights *= target_exposure / weights.sum()
    weights = trim_to_exposure_cap(weights, cfg)
    weights = trim_to_group_caps(weights, candidates, cfg)
    weights = trim_to_beta_cap(weights, candidates, cfg).sort_values(ascending=False)
    validate_weights(weights, candidates, cfg, context="allocation")
    return weights.sort_values(ascending=False)


def apply_trade_controls(target: pd.Series, previous: pd.Series, snapshot: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Apply no-trade band, smoothing and turnover controls with exposure recovery.

    Scientific rationale: signal refresh can be frequent, but trading should be
    threshold-based.  However, in risk-on regimes the previous version could get
    trapped at ~60% exposure.  Exposure recovery overrides smoothing/turnover
    only when actual exposure is materially below the risk-on floor.
    """
    target = target.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    previous = previous.replace([np.inf, -np.inf], np.nan).dropna().astype(float)
    all_names = target.index.union(previous.index)
    target = target.reindex(all_names).fillna(0.0)
    previous = previous.reindex(all_names).fillna(0.0)
    if all_names.empty:
        return pd.Series(dtype=float)

    prev_exposure = float(previous.clip(lower=0.0).sum())
    target_exposure = float(target.clip(lower=0.0).sum())
    risk_floor = float(getattr(cfg, "risk_on_exposure_floor", 0.0) or 0.0)
    exposure_recovery = target_exposure >= max(0.80, risk_floor - 1e-8) and prev_exposure < max(0.0, risk_floor - 0.05)

    if prev_exposure < 1e-8 or exposure_recovery:
        # Initial entry and risk-on exposure recovery should not be throttled by
        # smoothing or by the ordinary turnover cap; otherwise the model can be
        # structurally unable to reach its benchmark-aware exposure target.
        controlled = target.copy()
    else:
        smoothing = min(max(float(cfg.weight_smoothing), 0.0), 1.0)
        controlled = previous + smoothing * (target - previous)
        if cfg.max_turnover is not None and float(cfg.max_turnover) > 0:
            delta = controlled - previous
            turnover = float(delta.abs().sum())
            if turnover > float(cfg.max_turnover):
                controlled = previous + delta * (float(cfg.max_turnover) / turnover)

    if cfg.no_trade_band > 0 and prev_exposure >= 1e-8 and not exposure_recovery:
        banded = controlled.copy()
        small = (target - previous).abs() < float(cfg.no_trade_band)
        banded.loc[small] = previous.loc[small]
        banded = banded[banded.abs() > 1e-10]
        try:
            validate_weights(banded, snapshot, cfg, context="trade_controls_banded")
            controlled = banded.reindex(all_names).fillna(0.0)
        except ValueError:
            pass

    controlled = controlled[controlled.abs() > 1e-10].clip(lower=0.0)
    controlled = trim_to_exposure_cap(controlled, cfg)
    controlled = project_to_valid_by_blending(controlled, target, snapshot, cfg, context="trade_controls")
    controlled = trim_to_exposure_cap(controlled, cfg)
    validate_weights(controlled, snapshot, cfg, context="trade_controls_final")
    return controlled.sort_values(ascending=False)




def _empty_tail_prune_diag(weights: pd.Series, cfg: BacktestConfig) -> Dict[str, float]:
    n = float(len(weights[weights > 1e-12]) if isinstance(weights, pd.Series) else 0.0)
    exposure = float(weights[weights > 1e-12].sum()) if isinstance(weights, pd.Series) and not weights.empty else 0.0
    hard_cap = int(getattr(cfg, "max_n_positions_hard", 0) or 0)
    return {
        "n_positions_before_tail_prune": n,
        "n_positions_after_tail_prune": n,
        "residual_positions_pruned": 0.0,
        "residual_weight_pruned": 0.0,
        "exposure_before_tail_prune": exposure,
        "weight_reallocated_after_prune": 0.0,
        "weight_left_cash_after_prune": 0.0,
        "exposure_after_tail_prune": exposure,
        "soft_position_cap_breach": 0.0,
        "hard_position_cap_breach": float(hard_cap > 0 and n > hard_cap),
        "soft_cap_positions_pruned": 0.0,
        "soft_cap_weight_pruned": 0.0,
        "total_weight_pruned": 0.0,
        "tail_prune_turnover": 0.0,
        "tail_prune_sell_turnover": 0.0,
        "tail_prune_reallocation_turnover": 0.0,
        "tail_prune_constraint_failure": 0.0,
        "tail_prune_reallocation_failed": 0.0,
        "soft_cap_relaxed_count": 0.0,
        "hard_cap_fallback_count": 0.0,
        "tail_prune_full_fallback": 0.0,
        "max_position_binding_after_prune": 0.0,
        "max_sector_binding_after_prune": 0.0,
        "max_cluster_binding_after_prune": 0.0,
        "max_beta_binding_after_prune": 0.0,
    }


def _tail_rank_table(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked is None or ranked.empty or "ticker" not in ranked.columns:
        return pd.DataFrame(columns=["ticker", "_rank", "selection_score", "alpha_lcb"])
    rank_col = "selection_score" if "selection_score" in ranked.columns else "alpha_lcb"
    out = ranked.drop_duplicates("ticker").copy()
    if rank_col not in out.columns:
        out[rank_col] = 0.0
    out[rank_col] = pd.to_numeric(out[rank_col], errors="coerce").fillna(-np.inf)
    out.sort_values(rank_col, ascending=False, inplace=True)
    out["_rank"] = np.arange(1, len(out) + 1)
    if "selection_score" not in out.columns:
        out["selection_score"] = out[rank_col]
    if "alpha_lcb" not in out.columns:
        out["alpha_lcb"] = 0.0
    return out


def _tail_keep_priority(weights: pd.Series, previous: pd.Series, ranked: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    rank_table = _tail_rank_table(ranked)
    if rank_table.empty:
        return weights.sort_values(ascending=False)
    meta = rank_table.set_index("ticker")
    top_k = max(int(getattr(cfg, "top_k", 10) or 10), 1)
    hold_rank = max(top_k, int(math.ceil(top_k * float(getattr(cfg, "hold_rank_multiple", 2.5) or 2.5))))
    score = pd.Series(0.0, index=weights.index, dtype=float)
    rank = pd.to_numeric(meta.reindex(weights.index)["_rank"], errors="coerce")
    score += (rank <= top_k).fillna(False).astype(float) * 1000.0
    score += (rank <= hold_rank).fillna(False).astype(float) * 500.0
    if "alpha_lcb" in meta.columns:
        score += pd.to_numeric(meta.reindex(weights.index)["alpha_lcb"], errors="coerce").fillna(0.0) * 100.0
    if "selection_score" in meta.columns:
        score += pd.to_numeric(meta.reindex(weights.index)["selection_score"], errors="coerce").fillna(0.0) * 10.0
    score += weights.reindex(score.index).fillna(0.0) * 5.0
    score += previous.reindex(score.index).fillna(0.0) * 2.0
    score += (1.0 / rank.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return score.sort_values(ascending=False)



def _tail_metadata(weights: pd.Series, ranked: pd.DataFrame, cfg: Optional[BacktestConfig] = None) -> pd.DataFrame:
    """Return ticker metadata aligned to weights for tail-prune cap checks."""
    idx = pd.Index([str(x) for x in weights.index], name="ticker")
    meta = pd.DataFrame(index=idx)
    if ranked is not None and not ranked.empty and "ticker" in ranked.columns:
        src = ranked.drop_duplicates("ticker").copy()
        src["ticker"] = src["ticker"].astype(str)
        src = src.set_index("ticker")
        meta = meta.join(src.reindex(idx), how="left", rsuffix="_src")
    if "sector" not in meta.columns:
        meta["sector"] = [ticker_to_sector(tk) for tk in idx]
    else:
        meta["sector"] = meta["sector"].fillna(pd.Series([ticker_to_sector(tk) for tk in idx], index=idx))
    if "issuer" not in meta.columns:
        meta["issuer"] = [ticker_to_issuer(tk) for tk in idx]
    else:
        meta["issuer"] = meta["issuer"].fillna(pd.Series([ticker_to_issuer(tk) for tk in idx], index=idx))
    meta = _ensure_cluster_columns(meta)
    if "beta_252" not in meta.columns:
        meta["beta_252"] = np.nan
    meta["beta_252"] = pd.to_numeric(meta["beta_252"], errors="coerce").fillna(0.0)
    try:
        completion_ticker = _benchmark_completion_ticker(cfg)  # type: ignore[name-defined]
    except Exception:
        completion_ticker = "SPY"
    if completion_ticker in meta.index and float(meta.loc[completion_ticker, "beta_252"]) == 0.0:
        meta.loc[completion_ticker, "beta_252"] = 1.0
    return meta


def _tail_increment_capacity(ticker: str, weights: pd.Series, ranked: pd.DataFrame, cfg: BacktestConfig, *, already_added: float = 0.0) -> Tuple[float, str]:
    """Maximum additional weight for one ticker under all hard caps.

    Unknown sector / cluster are treated as explicit conservative buckets capped at
    max_sector / max_correlation_cluster (governance remediation V5R matrix).
    """
    ticker = str(ticker)
    weights = weights.astype(float).clip(lower=0.0)
    if ticker not in weights.index:
        # Increment-capacity is also used for new cash-filler names. Add the
        # candidate with zero current weight so metadata/capacity can be evaluated.
        weights = weights.reindex(weights.index.union([ticker])).fillna(0.0)
    meta = _tail_metadata(weights, ranked, cfg)
    w = float(weights.get(ticker, 0.0))
    caps: Dict[str, float] = {}
    caps["position"] = float(getattr(cfg, "max_position", 0.0) or 0.0) - w

    issuer = str(meta.loc[ticker, "issuer"])
    issuer_weight = float(weights[meta["issuer"] == issuer].sum())
    caps["issuer"] = float(getattr(cfg, "max_issuer", 0.0) or 0.0) - issuer_weight

    sector = str(meta.loc[ticker, "sector"])
    sector_weight = float(weights[meta["sector"] == sector].sum())
    caps["sector"] = float(getattr(cfg, "max_sector", 0.0) or 0.0) - sector_weight

    for labels, cap, label, include_unknown in _active_cluster_specs(meta, cfg):
        cluster = str(labels.loc[ticker]) if ticker in labels.index else "Unknown"
        if cap > 0:
            cluster_weight = float(weights[labels.reindex(weights.index).fillna("Unknown") == cluster].sum())
            caps[label] = cap - cluster_weight

    gross_cap_cfg = float(getattr(cfg, "max_gross_exposure", 0.0) or 0.0)
    if gross_cap_cfg > 0:
        caps["gross"] = gross_cap_cfg - float(weights.sum())

    beta_cap_cfg = float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0)
    beta = float(meta.loc[ticker, "beta_252"])
    if beta_cap_cfg > 0 and beta > 0:
        current_beta = float((weights * meta["beta_252"].reindex(weights.index).fillna(0.0)).sum())
        caps["beta"] = (beta_cap_cfg - current_beta) / beta

    per_name_cap = float(getattr(cfg, "max_tail_reallocation_per_name", 0.0) or 0.0)
    if per_name_cap > 0:
        caps["per_name_tail"] = per_name_cap - float(already_added)

    finite_caps = {k: float(v) for k, v in caps.items() if np.isfinite(float(v))}
    if not finite_caps:
        return 0.0, "no_finite_cap"
    reason, cap = min(finite_caps.items(), key=lambda kv: kv[1])
    return max(0.0, float(cap)), reason


def _reallocate_tail_weight(current_weights: pd.Series, target_exposure: float, ranked: pd.DataFrame, cfg: BacktestConfig, priority: Optional[pd.Series] = None) -> Tuple[pd.Series, Dict[str, float]]:
    """Cap-aware waterfall reallocation of weight freed by residual/soft-cap pruning."""
    out = current_weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    out = out[out > 1e-12].sort_values(ascending=False)
    target_exposure = min(float(target_exposure), float(getattr(cfg, "max_gross_exposure", target_exposure) or target_exposure))
    remaining = max(0.0, target_exposure - float(out.sum()))
    diag = {
        "tail_reallocation_attempted_weight": float(remaining),
        "tail_reallocation_allocated_weight": 0.0,
        "tail_reallocation_left_cash": float(remaining),
        "tail_reallocation_blocked_names": 0.0,
    }
    if remaining <= 1e-12 or out.empty or not bool(getattr(cfg, "tail_prune_reallocate", True)):
        return out, diag

    if priority is None or priority.empty:
        priority = out.sort_values(ascending=False)
    names = [str(x) for x in priority.index if str(x) in out.index]
    if not names:
        names = list(out.index)

    step = max(float(getattr(cfg, "tail_reallocation_step", 0.0025) or 0.0025), 1e-6)
    rounds = max(int(getattr(cfg, "tail_reallocation_rounds", 10) or 10), 1)
    added_by_name = {tk: 0.0 for tk in out.index}
    blocked = set()

    for _ in range(rounds):
        if remaining <= 1e-10:
            break
        allocated_this_round = 0.0
        for tk in names:
            if remaining <= 1e-10:
                break
            cap, reason = _tail_increment_capacity(tk, out, ranked, cfg, already_added=added_by_name.get(tk, 0.0))
            if cap <= 1e-10:
                blocked.add(f"{tk}:{reason}")
                continue
            add = min(remaining, cap, step)
            if add <= 1e-12:
                continue
            out.loc[tk] = float(out.loc[tk]) + float(add)
            added_by_name[tk] = added_by_name.get(tk, 0.0) + float(add)
            remaining -= float(add)
            allocated_this_round += float(add)
        if allocated_this_round <= 1e-12:
            break

    diag["tail_reallocation_allocated_weight"] = float(sum(added_by_name.values()))
    diag["tail_reallocation_left_cash"] = float(max(0.0, target_exposure - float(out.sum())))
    diag["tail_reallocation_blocked_names"] = float(len(blocked))
    return out[out > 1e-12].sort_values(ascending=False), diag


def apply_tail_pruning(weights: pd.Series, previous: pd.Series, ranked: pd.DataFrame, cfg: BacktestConfig) -> Tuple[pd.Series, Dict[str, float]]:
    """Residual-position sweep plus constraint-aware soft position cap.

    The function is deliberately conservative: it never normalizes after dropping
    names. Freed weight is reallocated only through cap headroom. If validation or
    exposure preservation fails, the function relaxes the soft cap or falls back to
    the pre-prune portfolio.
    """
    weights = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    weights = weights[weights > 1e-12].sort_values(ascending=False)
    previous = previous.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    if not bool(getattr(cfg, "tail_prune_enabled", False)) or weights.empty:
        return weights, _empty_tail_prune_diag(weights, cfg)

    original = weights.copy()
    exposure_before = float(original.sum())
    residual_floor = max(float(getattr(cfg, "residual_weight_floor", 0.0) or 0.0), 0.0)
    soft_cap = max(int(getattr(cfg, "max_n_positions_soft", 0) or 0), 0)
    hard_cap = max(int(getattr(cfg, "max_n_positions_hard", 0) or 0), soft_cap)
    exposure_buffer = max(float(getattr(cfg, "tail_prune_min_exposure_buffer", 0.02) or 0.0), 0.0)

    diag = _empty_tail_prune_diag(original, cfg)
    diag["n_positions_before_tail_prune"] = float(len(original))
    diag["exposure_before_tail_prune"] = exposure_before
    diag["soft_position_cap_breach"] = float(soft_cap > 0 and len(original) > soft_cap)
    diag["hard_position_cap_breach"] = float(hard_cap > 0 and len(original) > hard_cap)

    rank_table = _tail_rank_table(ranked)
    top_k = max(int(getattr(cfg, "top_k", 10) or 10), 1)
    hold_rank = max(top_k, int(math.ceil(top_k * float(getattr(cfg, "hold_rank_multiple", 2.5) or 2.5))))
    hold_universe = set(rank_table.loc[rank_table["_rank"] <= hold_rank, "ticker"].astype(str)) if not rank_table.empty else set(original.index)

    working = original.copy()
    if residual_floor > 0:
        residual_candidates = [tk for tk, w in working.items() if float(w) < residual_floor and str(tk) not in hold_universe]
        if residual_candidates:
            diag["residual_positions_pruned"] = float(len(residual_candidates))
            diag["residual_weight_pruned"] = float(working.reindex(residual_candidates).fillna(0.0).sum())
            working = working.drop(residual_candidates, errors="ignore")

    priority = _tail_keep_priority(working, previous, ranked, cfg)

    # Minimum exposure guard. In risk-on snapshots, keep the portfolio close to the risk-on floor;
    # otherwise preserve the pre-prune exposure as far as caps allow.
    min_required_exposure = max(0.0, exposure_before - 0.03)
    try:
        if ranked is not None and not ranked.empty and "risk_on" in ranked.columns and ranked["risk_on"].dropna().astype(bool).any():
            min_required_exposure = max(0.0, min(exposure_before, float(getattr(cfg, "risk_on_exposure_floor", exposure_before) or exposure_before) - exposure_buffer))
    except Exception:
        pass

    def try_candidate(base: pd.Series, label: str) -> Tuple[Optional[pd.Series], Dict[str, float]]:
        local_diag: Dict[str, float] = {}
        candidate = base[base > 1e-12].sort_values(ascending=False)
        if bool(getattr(cfg, "tail_prune_reallocate", True)) and float(candidate.sum()) < exposure_before - 1e-10:
            candidate, realloc_diag = _reallocate_tail_weight(candidate, exposure_before, ranked, cfg, priority.reindex(candidate.index).dropna().sort_values(ascending=False))
            local_diag.update(realloc_diag)
        try:
            validate_weights(candidate, ranked, cfg, context=label)
        except Exception:
            local_diag["tail_prune_constraint_failure"] = 1.0
            return None, local_diag
        if float(candidate.sum()) < min_required_exposure - 1e-8:
            local_diag["tail_prune_reallocation_failed"] = 1.0
            return None, local_diag
        return candidate, local_diag

    # Apply the soft cap by trying soft_cap first, then relaxing up to hard_cap when constraints or exposure require it.
    if soft_cap > 0 and len(working) > soft_cap:
        before_soft = working.copy()
        max_limit = min(len(priority), hard_cap if hard_cap > 0 else len(priority))
        accepted = None
        accepted_limit = None
        failures = 0.0
        for limit in range(soft_cap, max_limit + 1):
            names = list(priority.index[:limit])
            base = working.reindex(names).dropna()
            candidate, local_diag = try_candidate(base, f"tail_prune_soft_cap_{limit}")
            failures += float(local_diag.get("tail_prune_constraint_failure", 0.0)) + float(local_diag.get("tail_prune_reallocation_failed", 0.0))
            if candidate is not None:
                accepted = candidate
                accepted_limit = limit
                break
        if accepted is not None:
            working = accepted
            diag["soft_cap_positions_pruned"] = float(max(0, len(before_soft) - len(working)))
            dropped_by_cap = before_soft.drop(index=working.index, errors="ignore")
            diag["soft_cap_weight_pruned"] = float(dropped_by_cap.sum()) if not dropped_by_cap.empty else 0.0
            if accepted_limit is not None and accepted_limit > soft_cap:
                diag["soft_cap_relaxed_count"] = 1.0
        else:
            diag["tail_prune_constraint_failure"] += max(1.0, failures)
            diag["hard_cap_fallback_count"] = 1.0
            # Keep only the residual sweep; if residual sweep itself damages exposure, final fallback below will revert.

    # If only residual pruning occurred, reallocate freed exposure through cap headroom.
    if bool(getattr(cfg, "tail_prune_reallocate", True)) and float(working.sum()) < exposure_before - 1e-10:
        candidate, local_diag = _reallocate_tail_weight(working, exposure_before, ranked, cfg, priority.reindex(working.index).dropna().sort_values(ascending=False))
        try:
            validate_weights(candidate, ranked, cfg, context="tail_prune_reallocate_final")
            if float(candidate.sum()) >= min_required_exposure - 1e-8:
                working = candidate
            else:
                diag["tail_prune_reallocation_failed"] += 1.0
        except Exception:
            diag["tail_prune_constraint_failure"] += 1.0
            diag["tail_prune_reallocation_failed"] += 1.0

    working = working[working > 1e-12].sort_values(ascending=False)
    working = trim_to_exposure_cap(working, cfg)

    try:
        validate_weights(working, ranked, cfg, context="tail_prune_final")
        if float(working.sum()) < min_required_exposure - 1e-8 and len(working) < len(original):
            raise ValueError("tail_prune exposure guard failed")
    except Exception:
        diag["tail_prune_constraint_failure"] += 1.0
        diag["tail_prune_full_fallback"] = 1.0
        working = original.copy()

    all_names = original.index.union(working.index)
    before_full = original.reindex(all_names).fillna(0.0)
    after_full = working.reindex(all_names).fillna(0.0)
    decreases = (before_full - after_full).clip(lower=0.0)
    increases = (after_full - before_full).clip(lower=0.0)

    diag["n_positions_after_tail_prune"] = float(len(working))
    diag["exposure_after_tail_prune"] = float(working.sum()) if not working.empty else 0.0
    diag["total_weight_pruned"] = float(decreases.sum())
    diag["weight_reallocated_after_prune"] = float(increases.sum())
    diag["weight_left_cash_after_prune"] = float(max(0.0, exposure_before - float(working.sum())))
    diag["tail_prune_turnover"] = float((after_full - before_full).abs().sum())
    diag["tail_prune_sell_turnover"] = float(decreases.sum())
    diag["tail_prune_reallocation_turnover"] = float(increases.sum())
    diag["hard_position_cap_breach"] = float(hard_cap > 0 and len(working) > hard_cap)

    pdiag = portfolio_diagnostics(working, ranked, cfg)
    diag["max_position_binding_after_prune"] = float(float(getattr(cfg, "max_position", 0.0) or 0.0) > 0 and pdiag.get("max_position_weight", 0.0) >= float(getattr(cfg, "max_position", 0.0)) - 1e-4)
    diag["max_sector_binding_after_prune"] = float(float(getattr(cfg, "max_sector", 0.0) or 0.0) > 0 and pdiag.get("max_sector_weight", 0.0) >= float(getattr(cfg, "max_sector", 0.0)) - 1e-4)
    diag["max_cluster_binding_after_prune"] = float(float(getattr(cfg, "max_correlation_cluster", 0.0) or 0.0) > 0 and pdiag.get("max_correlation_cluster_weight", 0.0) >= float(getattr(cfg, "max_correlation_cluster", 0.0)) - 1e-4)
    diag["max_beta_binding_after_prune"] = float(float(getattr(cfg, "max_portfolio_beta", 0.0) or 0.0) > 0 and pdiag.get("portfolio_beta", 0.0) >= float(getattr(cfg, "max_portfolio_beta", 0.0)) - 1e-4)

    return working.sort_values(ascending=False), diag

def determine_risk_on(market_trend_200: float, market_ret_63: float, cfg: BacktestConfig) -> bool:
    """Return market risk regime using an explicit robustness-test mode.

    The default reproduces the original rule. strict/loose are intended for
    robustness diagnostics and should be selected deliberately through the CLI.
    """
    mode = str(getattr(cfg, "risk_regime_mode", "normal") or "normal").lower().strip()
    try:
        trend = float(market_trend_200)
    except Exception:
        trend = 0.0
    try:
        ret63 = float(market_ret_63)
    except Exception:
        ret63 = -1.0
    if mode == "strict":
        return bool(trend > 1.02 and ret63 > -0.03)
    if mode == "loose":
        return bool(trend > 0.98 and ret63 > -0.12)
    return bool(trend >= 1.0 and ret63 > -0.07)




def compute_target_exposure(snapshot: pd.DataFrame, risk_on: bool, cfg: BacktestConfig) -> tuple[float, Dict[str, float]]:
    """Return target exposure using the Stage-3 gradual controller.

    The old binary controller remains available through --exposure-controller binary.
    The gradual controller uses only snapshot-date information: SPY trend/return/
    volatility and cross-sectional signal breadth.
    """
    max_gross = float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0)
    good = float(getattr(cfg, "good_regime_exposure", 1.0) or 1.0)
    bad = float(getattr(cfg, "bad_regime_exposure", 0.60) or 0.60)
    floor = float(getattr(cfg, "risk_on_exposure_floor", 0.0) or 0.0)
    mode = str(getattr(cfg, "exposure_controller", "gradual") or "gradual").lower().strip()

    def scalar(name: str, default: float) -> float:
        try:
            if name in snapshot.columns and snapshot[name].notna().any():
                val = float(pd.to_numeric(snapshot[name], errors="coerce").dropna().iloc[0])
                return val if np.isfinite(val) else default
        except Exception:
            pass
        return default

    mtrend = scalar("market_trend_200", 1.0)
    mret63 = scalar("market_ret_63", 0.0)
    mvol20 = scalar("market_vol_20", 0.20)

    if mode == "binary":
        exposure = good if risk_on else bad
        if risk_on:
            exposure = max(exposure, floor)
        exposure = min(max(exposure, 0.0), max_gross)
        return exposure, {
            "exposure_controller_mode": 0.0,
            "exposure_controller_score": float(1.0 if risk_on else 0.0),
            "signal_breadth_positive": np.nan,
            "avg_alpha_lcb": np.nan,
            "n_positive_candidates_for_exposure": np.nan,
        }

    sig = pd.Series(dtype=float)
    if "alpha_lcb" in snapshot.columns:
        sig = pd.to_numeric(snapshot["alpha_lcb"], errors="coerce")
    elif "mu_hat" in snapshot.columns:
        sig = pd.to_numeric(snapshot["mu_hat"], errors="coerce")
    if "eligible" in snapshot.columns:
        sig = sig.reindex(snapshot.index)[snapshot["eligible"].fillna(False).astype(bool)]
    else:
        sig = sig.dropna()
    n_sig = int(sig.notna().sum())
    n_pos = int((sig > 0).sum()) if n_sig else 0
    breadth = float(n_pos / max(n_sig, 1)) if n_sig else 0.0
    avg_alpha = float(sig.mean()) if n_sig else 0.0

    trend_score = _clip_float((mtrend - 0.96) / 0.10, 0.0, 1.0)
    return_score = _clip_float((mret63 + 0.12) / 0.24, 0.0, 1.0)
    vol_score = _clip_float(1.0 - max(0.0, mvol20 - 0.18) / 0.32, 0.0, 1.0)
    breadth_score = _clip_float((breadth - 0.25) / 0.50, 0.0, 1.0)
    alpha_score = _clip_float((avg_alpha + 0.0025) / 0.0100, 0.0, 1.0)
    score = float(0.30 * trend_score + 0.20 * return_score + 0.20 * vol_score + 0.20 * breadth_score + 0.10 * alpha_score)
    raw = bad + (good - bad) * score
    if mode == "gradual_alpha" and risk_on:
        # Alpha-return default: remain benchmark-like when the market regime is constructive.
        raw = max(raw, floor)
    elif risk_on:
        raw = max(raw, floor)
    exposure = min(max(raw, 0.0), max_gross)
    return exposure, {
        "exposure_controller_mode": 1.0,
        "exposure_controller_score": score,
        "exposure_controller_trend_score": float(trend_score),
        "exposure_controller_return_score": float(return_score),
        "exposure_controller_vol_score": float(vol_score),
        "exposure_controller_breadth_score": float(breadth_score),
        "exposure_controller_alpha_score": float(alpha_score),
        "signal_breadth_positive": float(breadth),
        "avg_alpha_lcb": float(avg_alpha),
        "n_positive_candidates_for_exposure": float(n_pos),
    }



def _benchmark_completion_ticker(cfg: BacktestConfig) -> str:
    return normalize_yfinance_ticker(getattr(cfg, "benchmark_completion_ticker", "SPY") or "SPY") or "SPY"

def _is_benchmark_completion_ticker(ticker: str, cfg: BacktestConfig) -> bool:
    return normalize_yfinance_ticker(ticker) == _benchmark_completion_ticker(cfg)

def apply_benchmark_completion(weights: pd.Series, cfg: BacktestConfig, target_exposure: float) -> tuple[pd.Series, Dict[str, float]]:
    """Complete residual exposure with the benchmark ETF instead of weak low-beta names.

    The sleeve is included in gross exposure and beta, but is excluded from
    single-stock position/issuer/sector/cluster caps by portfolio_diagnostics.
    """
    diag = {
        "benchmark_completion_enabled": 1.0,
        "benchmark_completion_added_weight": 0.0,
        "benchmark_completion_weight": 0.0,
        "benchmark_completion_ticker_code": 0.0,
    }
    out = weights.copy().astype(float) if isinstance(weights, pd.Series) else pd.Series(dtype=float)
    out = out.replace([np.inf, -np.inf], np.nan).dropna().clip(lower=0.0)
    out = out[out > 1e-12]
    ticker = _benchmark_completion_ticker(cfg)
    max_w = max(float(getattr(cfg, "benchmark_completion_max_weight", 0.25) or 0.25), 0.0)
    target_exposure = min(float(target_exposure), float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0))
    gap = max(0.0, target_exposure - float(out.sum()))
    current = float(out.get(ticker, 0.0))
    add = min(gap, max(0.0, max_w - current))
    if add > 1e-10:
        out.loc[ticker] = current + add
        diag["benchmark_completion_added_weight"] = float(add)
    out = trim_to_exposure_cap(out, cfg)
    diag["benchmark_completion_weight"] = float(out.get(ticker, 0.0))
    return out[out > 1e-12].sort_values(ascending=False), diag

def apply_cash_filler(weights: pd.Series, ranked: pd.DataFrame, cfg: BacktestConfig, target_exposure: float, *, risk_on: bool) -> Tuple[pd.Series, Dict[str, float]]:
    """Controlled filler sleeve for residual risk-on cash.

    Stage A adds positive-score candidates. Stage B (balanced_plus_low_beta)
    adds small low-beta, diversifying names when beta/cluster caps block the
    main alpha sleeve. Hard portfolio validation always remains in force.
    """
    diag = {
        "cash_filler_enabled": 0.0,
        "cash_filler_added_weight": 0.0,
        "cash_filler_n_names": 0.0,
        "cash_filler_failed": 0.0,
        "low_beta_filler_added_weight": 0.0,
        "low_beta_filler_n_names": 0.0,
        "low_beta_filler_enabled": 0.0,
        "benchmark_completion_enabled": 0.0,
        "benchmark_completion_added_weight": 0.0,
        "benchmark_completion_weight": 0.0,
    }
    mode = str(getattr(cfg, "cash_filler_mode", "balanced_plus_low_beta") or "balanced_plus_low_beta").lower().strip()
    current = weights.copy().astype(float) if weights is not None and not weights.empty else pd.Series(dtype=float)
    current = current[current > 1e-12]
    if mode == "off" or not risk_on:
        return current.sort_values(ascending=False), diag
    if mode == "benchmark_completion":
        completed, bdiag = apply_benchmark_completion(current, cfg, target_exposure)
        diag.update(bdiag)
        diag["cash_filler_enabled"] = 1.0
        diag["cash_filler_added_weight"] = float(bdiag.get("benchmark_completion_added_weight", 0.0))
        diag["cash_filler_n_names"] = float(1.0 if bdiag.get("benchmark_completion_added_weight", 0.0) > 0 else 0.0)
        return completed.sort_values(ascending=False), diag
    if ranked is None or ranked.empty:
        return current.sort_values(ascending=False), diag
    target_exposure = min(float(target_exposure), float(getattr(cfg, "max_gross_exposure", 1.0) or 1.0))
    gap = max(0.0, target_exposure - float(current.sum()))
    if gap < 0.01:
        return current.sort_values(ascending=False), diag
    diag["cash_filler_enabled"] = 1.0
    ranked2 = ranked.copy()
    if "ticker" not in ranked2.columns:
        return current.sort_values(ascending=False), diag
    ranked2["ticker"] = ranked2["ticker"].astype(str).str.upper().str.strip()
    if "selection_score" not in ranked2.columns:
        ranked2["selection_score"] = pd.to_numeric(ranked2.get("alpha_lcb", 0.0), errors="coerce").fillna(0.0)
    ranked2["selection_score"] = pd.to_numeric(ranked2["selection_score"], errors="coerce").fillna(-999.0)
    if "eligible" in ranked2.columns:
        ranked2 = ranked2[ranked2["eligible"].fillna(False).astype(bool)].copy()
    work = current.copy()

    def add_candidates(cands: pd.DataFrame, *, max_add_per_name: float, diag_weight_key: str, diag_n_key: str, context: str) -> int:
        nonlocal work, gap
        added = 0
        for _, row in cands.iterrows():
            if gap <= 1e-8:
                break
            tk = str(row.get("ticker", "")).upper().strip()
            if not tk or tk in work.index:
                continue
            cap, reason = _tail_increment_capacity(tk, work, ranked2, cfg)
            add = min(gap, max_add_per_name, max(0.0, cap))
            if add <= 1e-8:
                continue
            trial = work.copy()
            trial.loc[tk] = float(add)
            trial = trim_to_exposure_cap(trial, cfg)
            try:
                validate_weights(trial, ranked2, cfg, context=context)
            except Exception:
                continue
            work = trial[trial > 1e-12]
            gap = max(0.0, target_exposure - float(work.sum()))
            diag[diag_weight_key] += float(add)
            added += 1
        diag[diag_n_key] += float(added)
        return added

    max_add = float(getattr(cfg, "cash_filler_max_position", 0.03) or 0.03)
    if mode == "conservative":
        max_add = min(max_add, 0.02)
    min_score = float(getattr(cfg, "cash_filler_min_score", 0.0) or 0.0)
    alpha_cands = ranked2[ranked2["selection_score"] >= min_score].sort_values("selection_score", ascending=False)
    add_candidates(alpha_cands, max_add_per_name=max_add, diag_weight_key="cash_filler_added_weight", diag_n_key="cash_filler_n_names", context="cash_filler_alpha")

    # Cause-aware recovery: when beta or cluster caps block the high-alpha sleeve,
    # try small, low-beta diversifiers instead of forcing more high-beta winners.
    if mode in {"balanced_plus_low_beta", "low_beta", "balanced_low_beta"} and gap > 0.01:
        diag["low_beta_filler_enabled"] = 1.0
        beta_max = float(getattr(cfg, "low_beta_filler_beta_max", 0.90) or 0.90)
        low_beta_max_add = float(getattr(cfg, "low_beta_filler_max_position", 0.015) or 0.015)
        low_beta_min_score = float(getattr(cfg, "low_beta_filler_min_score", -0.05) or -0.05)
        max_vol63 = float(getattr(cfg, "low_beta_filler_max_vol_63", 0.75) or 0.75)
        lb = ranked2.copy()
        if "beta_252" not in lb.columns:
            lb["beta_252"] = np.nan
        if "vol_63" not in lb.columns:
            lb["vol_63"] = np.nan
        if "rel_strength_63" not in lb.columns:
            lb["rel_strength_63"] = 0.0
        lb["beta_252"] = pd.to_numeric(lb["beta_252"], errors="coerce").fillna(9.0)
        lb["vol_63"] = pd.to_numeric(lb["vol_63"], errors="coerce").fillna(9.0)
        lb["rel_strength_63"] = pd.to_numeric(lb["rel_strength_63"], errors="coerce").fillna(0.0)
        lb = lb[
            (lb["selection_score"] >= low_beta_min_score)
            & (lb["beta_252"] > 0)
            & (lb["beta_252"] <= beta_max)
            & (lb["vol_63"] <= max_vol63)
            & (lb["rel_strength_63"] >= -0.05)
        ].copy()
        # Favor beta efficiency rather than raw momentum in this sleeve.
        lb["filler_efficiency_score"] = lb["selection_score"] - 0.15 * lb["beta_252"] - 0.05 * lb["vol_63"]
        lb.sort_values("filler_efficiency_score", ascending=False, inplace=True)
        add_candidates(lb, max_add_per_name=low_beta_max_add, diag_weight_key="low_beta_filler_added_weight", diag_n_key="low_beta_filler_n_names", context="cash_filler_low_beta")

    diag["cash_filler_added_weight"] += float(diag.get("low_beta_filler_added_weight", 0.0))
    diag["cash_filler_n_names"] += float(diag.get("low_beta_filler_n_names", 0.0))
    if diag["cash_filler_n_names"] == 0 and float(work.sum()) < target_exposure - 0.01:
        diag["cash_filler_failed"] = 1.0
    return work.sort_values(ascending=False), diag

def _corr_components(corr: pd.DataFrame, threshold: float) -> Dict[str, str]:
    labels: Dict[str, str] = {}
    if corr is None or corr.empty:
        return labels
    names = [str(x) for x in corr.columns]
    parent = {n: n for n in names}
    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    vals = corr.fillna(0.0).values
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            if vals[i, j] >= threshold:
                union(names[i], names[j])
    comps: Dict[str, List[str]] = {}
    for n in names:
        comps.setdefault(find(n), []).append(n)
    k = 1
    for _, members in sorted(comps.items(), key=lambda kv: (-len(kv[1]), sorted(kv[1])[0])):
        if len(members) < 2:
            for m in members:
                labels[m] = ""
        else:
            lab = f"DYN_CLUSTER_{k:03d}"
            for m in members:
                labels[m] = lab
            k += 1
    return labels


def _dynamic_cluster_initializer(returns: pd.DataFrame) -> None:
    _parallel_worker_bootstrap()
    _CTX.returns = returns


def _dynamic_cluster_date_task(
    payload: Tuple[pd.Timestamp, pd.DataFrame, str, int, int, float, float],
) -> Tuple[pd.DataFrame, List[Dict[str, object]]]:
    if _CTX.returns is None:
        raise RuntimeError("Dynamic-cluster worker was not initialized.")
    d, snap, mode, w_short, w_long, threshold, min_overlap = payload
    returns = _CTX.returns
    rows: List[Dict[str, object]] = []
    if "in_universe" in snap.columns:
        tickers = snap.loc[snap["in_universe"].fillna(False).astype(bool), "ticker"].astype(str).str.upper().tolist()
    else:
        tickers = snap["ticker"].astype(str).str.upper().tolist()
    tickers = [t for t in tickers if t in returns.columns]
    if len(tickers) < 5:
        return snap, rows
    hs = returns.loc[returns.index < d, tickers].tail(w_short)
    hl = returns.loc[returns.index < d, tickers].tail(w_long)
    if len(hs) < max(40, w_short // 2):
        return snap, rows
    cs = hs.corr(min_periods=max(20, min(63, len(hs) // 2))).clip(lower=-1.0, upper=1.0)
    cl = hl.corr(min_periods=max(40, min(126, len(hl) // 2))).clip(lower=-1.0, upper=1.0) if len(hl) >= max(80, w_long // 2) else pd.DataFrame()
    ls = _corr_components(cs, threshold)
    ll = _corr_components(cl, threshold) if not cl.empty else {}
    comp_s: Dict[str, set[str]] = {}
    comp_l: Dict[str, set[str]] = {}
    for tk, lab in ls.items():
        if lab:
            comp_s.setdefault(lab, set()).add(tk)
    for tk, lab in ll.items():
        if lab:
            comp_l.setdefault(lab, set()).add(tk)
    for i in snap.index:
        tk = str(snap.at[i, "ticker"]).upper().strip()
        slab, llab = ls.get(tk, ""), ll.get(tk, "")
        overlap = 0.0
        stable = False
        if slab and llab and slab in comp_s and llab in comp_l:
            a, b = comp_s[slab], comp_l[llab]
            overlap = len(a & b) / max(len(a | b), 1)
            stable = overlap >= min_overlap
        use_dyn = (mode == "dynamic_enforced" and bool(slab)) or (mode == "dynamic_guardrail" and stable)
        if slab:
            snap.at[i, "correlation_cluster_dynamic"] = slab
        if stable:
            snap.at[i, "dynamic_cluster_stable"] = 1.0
        if use_dyn:
            snap.at[i, "correlation_cluster"] = slab
            snap.at[i, "correlation_cluster_source"] = "dynamic_enforced" if mode == "dynamic_enforced" else "dynamic_stable_guardrail"
        rows.append({
            "date": pd.Timestamp(d).date().isoformat(),
            "ticker": tk,
            "static_cluster": snap.at[i, "correlation_cluster_static"],
            "dynamic_cluster": slab,
            "long_window_cluster": llab,
            "dynamic_cluster_stable": float(stable),
            "cluster_overlap_score": float(overlap),
            "cluster_source": snap.at[i, "correlation_cluster_source"],
        })
    return snap, rows


def apply_dynamic_cluster_overlay(features: pd.DataFrame, returns: pd.DataFrame, cfg: BacktestConfig, dashboard: Optional[RunDashboard] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    mode = str(getattr(cfg, "cluster_mode", "dynamic_guardrail") or "dynamic_guardrail").lower().strip()
    out = features.copy()
    out["correlation_cluster_static"] = out.get("correlation_cluster", pd.Series("Unknown", index=out.index)).fillna("Unknown").astype(str)
    out["correlation_cluster_dynamic"] = ""
    out["correlation_cluster_source"] = "static"
    out["dynamic_cluster_stable"] = 0.0
    if mode == "static" or returns is None or returns.empty or "date" not in out.columns:
        return out, pd.DataFrame()
    dates = sorted(pd.Timestamp(d) for d in out["date"].dropna().unique())
    if not dates:
        return out, pd.DataFrame()
    first_possible = pd.Timestamp(getattr(cfg, "start", dates[0])) + pd.DateOffset(years=int(getattr(cfg, "train_years", 7) or 7))
    step = max(int(getattr(cfg, "rebalance_every", 5) or 5), 1)
    rb_dates = [d for idx, d in enumerate(dates) if d >= first_possible and idx % step == 0]
    if dates[-1] not in rb_dates:
        rb_dates.append(dates[-1])
    w_short = max(int(getattr(cfg, "dynamic_cluster_window_short", 126) or 126), 20)
    w_long = max(int(getattr(cfg, "dynamic_cluster_window_long", 252) or 252), w_short)
    threshold = float(getattr(cfg, "dynamic_cluster_corr_threshold", 0.65) or 0.65)
    min_overlap = float(getattr(cfg, "dynamic_cluster_min_overlap", 0.50) or 0.50)
    rows: List[Dict[str, object]] = []
    n_cluster_workers = resolve_parallel_workers(cfg, backend="process")
    cluster_tasks: List[Tuple[pd.Timestamp, pd.DataFrame, str, int, int, float, float]] = []
    for d in rb_dates:
        snap_idx = out.index[out["date"].eq(d)]
        if len(snap_idx) == 0:
            continue
        snap = out.loc[snap_idx].copy()
        cluster_tasks.append((pd.Timestamp(d), snap, mode, w_short, w_long, threshold, min_overlap))
    if dashboard is not None:
        dashboard.start_phase(
            "Dynamische Clusterdiagnostik",
            total=max(len(cluster_tasks), 1),
            step=f"Rolling-Korrelationen ({n_cluster_workers} Worker)" if n_cluster_workers > 1 else "Rolling-Korrelationen",
        )
    if parallel_execution_enabled(cfg) and cluster_tasks:
        for snap_updated, diag_rows in _parallel_map_unordered(
            cfg,
            _dynamic_cluster_date_task,
            cluster_tasks,
            initializer=_dynamic_cluster_initializer,
            initargs=(returns,),
            feature_table_gb=_estimate_dataframe_gb(returns),
        ):
            out.loc[snap_updated.index, snap_updated.columns] = snap_updated
            rows.extend(diag_rows)
            if dashboard is not None:
                dashboard.advance_phase(1, step="Cluster (parallel)", candidates=len(snap_updated))
    else:
        _dynamic_cluster_initializer(returns)
        for task in cluster_tasks:
            snap_updated, diag_rows = _dynamic_cluster_date_task(task)
            out.loc[snap_updated.index, snap_updated.columns] = snap_updated
            rows.extend(diag_rows)
            if dashboard is not None:
                dashboard.advance_phase(1, step=str(pd.Timestamp(task[0]).date()), candidates=len(snap_updated))
    if dashboard is not None:
        dashboard.finish_phase()
    return out, pd.DataFrame(rows)


def enforce_reproducibility_inputs(cfg: BacktestConfig) -> None:
    from aa_config import enforce_reproducibility_inputs as _enforce

    _enforce(cfg)


def _log_constraint_fallback(dashboard: Optional[RunDashboard], context: str, detail: str) -> None:
    if dashboard is not None:
        dashboard.warn(f"Constraint fallback ({context}): {detail}")


def _base_eligibility_mask(snap: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    if "in_universe" not in snap.columns:
        snap = snap.copy()
        snap["in_universe"] = True
    mu_ok = snap["mu_hat"].notna() if "mu_hat" in snap.columns else pd.Series(True, index=snap.index)
    return (
        mu_ok
        & snap["in_universe"].fillna(False).astype(bool)
        & (pd.to_numeric(snap.get("adv_20", 0.0), errors="coerce").fillna(0.0) >= cfg.min_adv)
        & (pd.to_numeric(snap.get("vol_20", 99.0), errors="coerce").fillna(99.0) <= cfg.max_ann_vol)
    )


def _momentum_rank_pct(snap: pd.DataFrame, cfg: BacktestConfig, variant: Optional[str] = None) -> pd.Series:
    v = str(variant or getattr(cfg, "risk_off_momentum_variant", "mom_blend_top12") or "mom_blend_top12")
    mom = _momentum_score(snap, v)
    return safe_rank_pct(mom, ascending=True)


def _legacy_risk_off_gate_mask(snap: pd.DataFrame, cfg: BacktestConfig, base_ok: pd.Series, trend_count: pd.Series) -> pd.Series:
    alpha = pd.to_numeric(snap.get("alpha_lcb", snap.get("mu_hat", 0.0)), errors="coerce")
    return base_ok & (trend_count >= 1) & (alpha > -cfg.min_edge)


def compute_risk_off_eligibility(snap: pd.DataFrame, cfg: BacktestConfig, risk_on: bool) -> pd.Series:
    """Return per-name eligibility including configurable risk-off gates."""
    trend_count = snap["trend_50"].fillna(0) + snap["trend_200"].fillna(0) if "trend_50" in snap.columns else pd.Series(0.0, index=snap.index)
    base_ok = _base_eligibility_mask(snap, cfg)
    if risk_on:
        return base_ok
    gate_mode = str(getattr(cfg, "risk_off_gate_mode", "legacy") or "legacy").lower().strip()
    if gate_mode == "base_only":
        return base_ok
    legacy_ok = _legacy_risk_off_gate_mask(snap, cfg, base_ok, trend_count)
    if gate_mode == "legacy":
        return legacy_ok
    rescue_q = float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.70) or 0.70)
    mom_rank = _momentum_rank_pct(snap, cfg)
    momentum_rescue_ok = base_ok & (mom_rank >= rescue_q)
    return legacy_ok | momentum_rescue_ok


def compute_risk_off_forced_exit_tickers(
    snap: pd.DataFrame,
    previous: pd.Series,
    cfg: BacktestConfig,
    *,
    risk_on: bool,
) -> set:
    """Held names to exclude from buy/hold spread restoration in risk-off."""
    if not bool(getattr(cfg, "risk_off_force_exit_enabled", False)) or risk_on or previous.empty:
        return set()
    trend_count = snap["trend_50"].fillna(0) + snap["trend_200"].fillna(0) if "trend_50" in snap.columns else pd.Series(0.0, index=snap.index)
    base_ok = _base_eligibility_mask(snap, cfg)
    legacy_ok = _legacy_risk_off_gate_mask(snap, cfg, base_ok, trend_count)
    rescue_q = float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.70) or 0.70)
    mom_rank = _momentum_rank_pct(snap, cfg)
    momentum_rescue_ok = base_ok & (mom_rank >= rescue_q)
    ticker_col = snap["ticker"].astype(str) if "ticker" in snap.columns else snap.index.astype(str)
    legacy_map = dict(zip(ticker_col, legacy_ok.fillna(False).astype(bool)))
    rescue_map = dict(zip(ticker_col, momentum_rescue_ok.fillna(False).astype(bool)))
    forced: set = set()
    for tk, prev_w in previous.items():
        if float(prev_w) <= 0:
            continue
        tk_s = str(tk)
        if not legacy_map.get(tk_s, False) and not rescue_map.get(tk_s, False):
            forced.add(tk_s)
    return forced


def _ensemble_selection_score(cross: pd.DataFrame) -> pd.Series:
    def centered_rank(col: str, ascending: bool = True) -> pd.Series:
        return safe_rank_pct(cross[col], ascending=ascending) - 0.5

    return (
        0.50 * centered_rank("alpha_lcb", ascending=True)
        + 0.25 * (cross["rank_score"].fillna(0.5) - 0.5)
        + 0.15 * centered_rank("rel_strength_63", ascending=True)
        + 0.05 * centered_rank("sector_rel_strength_63", ascending=True)
        + 0.05 * (0.5 * cross["trend_50"].fillna(0) + 0.5 * cross["trend_200"].fillna(0) - 0.5)
        - 0.04 * centered_rank("vol_20", ascending=True)
        - 0.02 * centered_rank("idio_vol_63", ascending=True)
    )


def _blended_risk_off_selection_score(cross: pd.DataFrame, cfg: BacktestConfig, risk_on: bool) -> pd.Series:
    ensemble = _ensemble_selection_score(cross)
    if risk_on:
        return ensemble
    mode = str(getattr(cfg, "risk_off_selection_mode", "legacy") or "legacy").lower().strip()
    if mode == "legacy":
        return ensemble
    variant = str(getattr(cfg, "risk_off_momentum_variant", "mom_blend_top12") or "mom_blend_top12")
    mom_rank = _momentum_rank_pct(cross, cfg, variant=variant)
    if mode == "mom_blend_replace":
        return mom_rank - 0.5
    w = float(getattr(cfg, "risk_off_momentum_weight", 0.70) or 0.70)
    w = min(max(w, 0.0), 1.0)
    ens_rank = safe_rank_pct(ensemble, ascending=True)
    blended = (1.0 - w) * ens_rank + w * mom_rank
    return blended - 0.5


def select_portfolio(snapshot: pd.DataFrame, rmse: float, cfg: BacktestConfig) -> Tuple[pd.Series, pd.DataFrame]:
    snap = snapshot.copy()
    uncertainty_charge = cfg.lcb_z * cfg.lcb_scale * (rmse if np.isfinite(rmse) else 0.0)
    snap["alpha_lcb"] = snap["mu_hat"] - uncertainty_charge

    # Benchmark-aware regime control:
    # In risk-on markets the model stays nearly fully invested and ranks candidates.
    # In risk-off markets it reduces exposure and requires at least some positive evidence.
    mtrend = float(snap["market_trend_200"].dropna().iloc[0]) if snap["market_trend_200"].notna().any() else 0.0
    if snap["market_ret_63"].notna().any():
        mret63 = float(snap["market_ret_63"].dropna().iloc[0])
    else:
        # Fail-closed default -1.0 erzeugt RISK_OFF trotz trend>=1 — nur wenn ret63 wirklich fehlt.
        mret63 = -1.0
    risk_on = determine_risk_on(mtrend, mret63, cfg)
    exposure, exposure_controller_diag = compute_target_exposure(snap, risk_on, cfg)

    if "in_universe" not in snap.columns:
        snap["in_universe"] = True
    trend_count = snap["trend_50"].fillna(0) + snap["trend_200"].fillna(0)
    variant = str(getattr(cfg, "risk_off_momentum_variant", "mom_blend_top12") or "mom_blend_top12")
    base_ok = _base_eligibility_mask(snap, cfg)
    legacy_ok = _legacy_risk_off_gate_mask(snap, cfg, base_ok, trend_count)
    momentum_score = _momentum_score(snap, variant)
    momentum_rank = _momentum_rank_pct(snap, cfg, variant=variant)
    rescue_q = float(getattr(cfg, "risk_off_momentum_rescue_quantile", 0.70) or 0.70)
    rescue_ok = base_ok & (momentum_rank >= rescue_q)
    eligible = compute_risk_off_eligibility(snap, cfg, risk_on)
    ensemble_score = _ensemble_selection_score(snap)
    ensemble_rank = safe_rank_pct(ensemble_score, ascending=True)
    from aa_risk_off import attach_risk_off_diagnostics

    snap = attach_risk_off_diagnostics(
        snap,
        cfg,
        risk_on=risk_on,
        base_ok=base_ok,
        legacy_ok=legacy_ok,
        rescue_ok=rescue_ok,
        eligible=eligible,
        ensemble_score=ensemble_score,
        ensemble_rank=ensemble_rank,
        momentum_score=momentum_score,
        momentum_rank=momentum_rank,
    )
    snap["eligible"] = eligible
    snap["legacy_risk_off_ok"] = legacy_ok
    snap["momentum_rescue_ok"] = rescue_ok
    # Recompute gradual exposure after eligibility is known so signal breadth is
    # based on tradable candidates rather than the raw downloaded universe.
    exposure, exposure_controller_diag = compute_target_exposure(snap, risk_on, cfg)
    effective_beta_cap = effective_beta_cap_from_snapshot(snap, risk_on, cfg, exposure_controller_diag)
    cfg_eff = replace(cfg, max_portfolio_beta=effective_beta_cap)

    cross = snap.loc[eligible].copy()
    if cross.empty or exposure <= 0:
        snap["target_weight"] = 0.0
        snap["risk_on"] = risk_on
        snap["desired_exposure"] = exposure
        snap["regime_target_exposure"] = exposure
        snap["target_exposure"] = exposure
        for _k, _v in exposure_controller_diag.items():
            snap[_k] = _v
        snap["effective_max_portfolio_beta"] = float(effective_beta_cap)
        snap["beta_cap_mode_effective"] = 1.0 if str(getattr(cfg, "beta_cap_mode", "dynamic")).lower() == "dynamic" else 0.0
        snap["exposure_before_constraints"] = float(exposure)
        snap["exposure_after_position_cap"] = 0.0
        snap["exposure_after_issuer_cap"] = 0.0
        snap["exposure_after_sector_cap"] = 0.0
        snap["exposure_after_cluster_cap"] = 0.0
        snap["exposure_after_beta_cap"] = 0.0
        snap["n_candidates"] = int(len(snap))
        snap["n_eligible_candidates"] = int(eligible.sum()) if "eligible" in locals() else 0
        snap["n_selected_candidates"] = 0
        snap["n_rejected_by_membership"] = int((~snap.get("in_universe", pd.Series(True, index=snap.index)).fillna(False).astype(bool)).sum()) if "in_universe" in snap.columns else 0
        snap["n_rejected_by_adv"] = int(((pd.to_numeric(snap.get("adv_20", pd.Series(np.nan, index=snap.index)), errors="coerce") < cfg.min_adv) & snap["mu_hat"].notna()).sum()) if "adv_20" in snap.columns else 0
        snap["n_rejected_by_vol"] = int((pd.to_numeric(snap.get("vol_20", pd.Series(np.nan, index=snap.index)), errors="coerce").fillna(99) > cfg.max_ann_vol).sum()) if "vol_20" in snap.columns else 0
        for k, v in constraint_binding_metrics(pd.Series(dtype=float), snap, cfg_eff).items():
            snap[k] = v
        return pd.Series(dtype=float), snap.sort_values("alpha_lcb", ascending=False)

    cross["selection_score"] = _blended_risk_off_selection_score(cross, cfg, risk_on)

    cross.sort_values("selection_score", ascending=False, inplace=True)
    # Select enough names to fill exposure under max-position and issuer caps.
    min_names_needed = int(math.ceil(exposure / max(cfg.max_position, 1e-9)))
    n_select = max(cfg.top_k, min_names_needed)
    pool = cross.head(max(n_select * 2, cfg.top_k + 10)).copy()
    candidates = pool.head(n_select).copy()

    # Sizing: signal-weighted, only mildly volatility-adjusted.
    # Using sqrt(vol) rather than vol avoids cutting strong winners too aggressively.
    shifted = candidates["selection_score"] - candidates["selection_score"].min() + 1e-4
    vol_adj = np.sqrt(candidates.set_index("ticker")["vol_20"].clip(lower=0.05))
    raw = pd.Series(shifted.values, index=candidates["ticker"]) / vol_adj
    weights = allocate_with_caps(candidates, raw, cfg_eff, exposure)

    # If caps prevent full investment in risk-on, broaden the candidate pool once.
    if risk_on and weights.sum() < min(cfg.risk_on_exposure_floor, exposure) - 0.05 and len(pool) > len(candidates):
        candidates = pool.copy()
        shifted = candidates["selection_score"] - candidates["selection_score"].min() + 1e-4
        vol_adj = np.sqrt(candidates.set_index("ticker")["vol_20"].clip(lower=0.05))
        raw = pd.Series(shifted.values, index=candidates["ticker"]) / vol_adj
        weights = allocate_with_caps(candidates, raw, cfg_eff, exposure)

    weights, cash_filler_diag = apply_cash_filler(weights, cross, cfg_eff, exposure, risk_on=risk_on)
    try:
        validate_weights(weights, cross, cfg_eff, context="post_cash_filler")
    except ValueError:
        _log_constraint_fallback(None, "post_cash_filler", "trim after cash filler")
        weights = trim_to_exposure_cap(weights, cfg_eff)
        weights = trim_to_group_caps(weights, cross, cfg_eff)
        weights = trim_to_beta_cap(weights, cross, cfg_eff)
        validate_weights(weights, cross, cfg_eff, context="post_cash_filler_strict_final")

    exposure_before_constraints = float(exposure)
    exposure_after_position_cap = _allocation_exposure_for_stage(candidates, raw, cfg_eff, exposure, "position")
    exposure_after_issuer_cap = _allocation_exposure_for_stage(candidates, raw, cfg_eff, exposure, "issuer")
    exposure_after_sector_cap = _allocation_exposure_for_stage(candidates, raw, cfg_eff, exposure, "sector")
    exposure_after_cluster_cap = _allocation_exposure_for_stage(candidates, raw, cfg_eff, exposure, "cluster")
    exposure_after_beta_cap = float(weights.sum()) if not weights.empty else 0.0

    n_candidates_total = int(len(snap))
    n_rejected_by_membership = int((~snap.get("in_universe", pd.Series(True, index=snap.index)).fillna(False).astype(bool)).sum()) if "in_universe" in snap.columns else 0
    n_rejected_by_adv = int(((pd.to_numeric(snap.get("adv_20", pd.Series(np.nan, index=snap.index)), errors="coerce") < cfg.min_adv) & snap["mu_hat"].notna()).sum()) if "adv_20" in snap.columns else 0
    n_rejected_by_vol = int((pd.to_numeric(snap.get("vol_20", pd.Series(np.nan, index=snap.index)), errors="coerce").fillna(99) > cfg.max_ann_vol).sum()) if "vol_20" in snap.columns else 0

    extra_weight_rows = []
    for _tk in [str(x) for x in weights.index if str(x) not in set(snap["ticker"].astype(str))]:
        extra_weight_rows.append({"ticker": _tk, "date": snap["date"].iloc[0] if "date" in snap.columns and len(snap) else pd.NaT, "target_weight": float(weights.get(_tk, 0.0)), "eligible": False, "sector": "Benchmark", "issuer": _tk, "correlation_cluster": "Benchmark_Completion", "correlation_cluster_static": "Benchmark_Completion", "correlation_cluster_dynamic": "Benchmark_Completion", "beta_252": 1.0, "selection_score": 0.0, "alpha_lcb": 0.0, "rank_score": 0.0})
    snap["target_weight"] = snap["ticker"].map(weights).fillna(0.0)
    if extra_weight_rows:
        snap = pd.concat([snap, pd.DataFrame(extra_weight_rows)], ignore_index=True, sort=False)
    snap["risk_on"] = risk_on
    snap["desired_exposure"] = exposure
    snap["regime_target_exposure"] = exposure
    snap["target_exposure"] = exposure
    for _k, _v in exposure_controller_diag.items():
        snap[_k] = _v
    snap["effective_max_portfolio_beta"] = float(effective_beta_cap)
    snap["beta_cap_mode_effective"] = 1.0 if str(getattr(cfg, "beta_cap_mode", "dynamic")).lower() == "dynamic" else 0.0
    for _k, _v in cash_filler_diag.items():
        snap[_k] = _v
    snap["exposure_after_cash_filler"] = float(weights.sum()) if not weights.empty else 0.0
    snap["exposure_before_constraints"] = exposure_before_constraints
    snap["exposure_after_position_cap"] = exposure_after_position_cap
    snap["exposure_after_issuer_cap"] = exposure_after_issuer_cap
    snap["exposure_after_sector_cap"] = exposure_after_sector_cap
    snap["exposure_after_cluster_cap"] = exposure_after_cluster_cap
    snap["exposure_after_beta_cap"] = exposure_after_beta_cap
    snap["n_candidates"] = n_candidates_total
    snap["n_eligible_candidates"] = int(eligible.sum())
    snap["n_selected_candidates"] = int((weights > 1e-12).sum()) if not weights.empty else 0
    snap["n_rejected_by_membership"] = n_rejected_by_membership
    snap["n_rejected_by_adv"] = n_rejected_by_adv
    snap["n_rejected_by_vol"] = n_rejected_by_vol
    if not weights.empty:
        diag = portfolio_diagnostics(weights, snap, cfg_eff)
        diag.update(constraint_binding_metrics(weights, snap, cfg_eff))
        for k, v in diag.items():
            snap[k] = v
    else:
        snap["portfolio_exposure"] = 0.0
        snap["portfolio_beta"] = 0.0
        snap["max_position_weight"] = 0.0
        snap["max_issuer_weight"] = 0.0
        snap["max_sector_weight"] = 0.0
        snap["max_correlation_cluster_weight"] = 0.0
        snap["n_positions"] = 0.0
        snap["constraint_violations"] = 0.0
        for k, v in constraint_binding_metrics(pd.Series(dtype=float), snap, cfg_eff).items():
            snap[k] = v
    # Attach selection_score from the eligible cross-section without creating
    # selection_score_x/selection_score_y when benchmark-completion rows have
    # already introduced a selection_score column. A duplicated/renamed score
    # column causes sort_values("selection_score") to fail with KeyError.
    _score_col = "selection_score"
    _score_tmp = "__selection_score_from_cross"
    if _score_tmp in snap.columns:
        snap = snap.drop(columns=[_score_tmp])
    _score_map = cross[["ticker", "selection_score"]].rename(columns={"selection_score": _score_tmp})
    snap = snap.merge(_score_map, on="ticker", how="left")
    if _score_col in snap.columns:
        snap[_score_col] = pd.to_numeric(snap[_score_col], errors="coerce").combine_first(
            pd.to_numeric(snap[_score_tmp], errors="coerce")
        )
    else:
        snap[_score_col] = pd.to_numeric(snap[_score_tmp], errors="coerce")
    snap = snap.drop(columns=[_score_tmp], errors="ignore")
    snap = deduplicate_dataframe_columns(snap)
    return weights, snap.sort_values("selection_score", ascending=False, na_position="last")
def parse_naive_momentum_variants(cfg: BacktestConfig) -> List[str]:
    raw = str(getattr(cfg, "naive_momentum_variants", "") or "")
    variants = [x.strip().lower() for x in raw.split(",") if x.strip()]
    if not variants:
        variants = ["mom_blend_top12"]
    out: List[str] = []
    for v in variants:
        if v not in out:
            out.append(v)
    return out


def _momentum_variant_label(variant: str) -> str:
    return "NAIVE_MOMENTUM_" + str(variant).upper().replace("-", "_").replace(" ", "_")


def _momentum_score(snapshot: pd.DataFrame, variant: str) -> pd.Series:
    v = str(variant).lower().strip()
    idx = snapshot.index
    def col(name: str, default: float = 0.0) -> pd.Series:
        if name in snapshot.columns:
            return pd.to_numeric(snapshot[name], errors="coerce").fillna(default)
        return pd.Series(default, index=idx, dtype=float)
    # 1-day momentum (daily-alpha benchmark). "mom_1_" / exact "mom_1" only;
    # "mom_126"/"mom_252" do not match "mom_1_" so existing variants are untouched.
    if v == "mom_1" or v.startswith("mom_1_"):
        return col("mom_1")
    if v.startswith("mom_63"):
        return col("mom_63_21")
    if v.startswith("mom_126"):
        return col("mom_126_21")
    if v.startswith("mom_252"):
        return col("mom_252_21")
    # Blend: deliberately simple, auditable and distinct from the ML stack.
    return 0.50 * col("mom_252_21") + 0.30 * col("mom_126_21") + 0.20 * col("mom_63_21")


def _neutralized_momentum_candidates(ranked: pd.DataFrame, cfg: BacktestConfig, variant: str) -> List[str]:
    """Pick candidates with simple sector/cluster neutrality for a fairer control."""
    top_k = max(int(getattr(cfg, "top_k", 12) or 12), 1)
    v = str(variant).lower().strip()
    group_col = "sector" if "sector" in v else "correlation_cluster"
    if group_col not in ranked.columns:
        return ranked.head(top_k)["ticker"].tolist()
    selected: List[str] = []
    counts: Dict[str, int] = {}
    max_per_group = max(1, int(math.ceil(top_k / 4.0)))
    for _, row in ranked.iterrows():
        tk = str(row.get("ticker", "")).upper().strip()
        grp = str(row.get(group_col, "Unknown") or "Unknown")
        if not tk:
            continue
        if counts.get(grp, 0) >= max_per_group:
            continue
        selected.append(tk)
        counts[grp] = counts.get(grp, 0) + 1
        if len(selected) >= top_k:
            break
    if len(selected) < top_k:
        for tk in ranked["ticker"].astype(str).str.upper().tolist():
            if tk not in selected:
                selected.append(tk)
            if len(selected) >= top_k:
                break
    return selected[:top_k]
