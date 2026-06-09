from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sys
try:
    from importlib import metadata as importlib_metadata
except Exception:  # pragma: no cover - very old Python fallback
    importlib_metadata = None
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aa_config import BacktestConfig

def _hash_file(path: Path) -> str:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


class PhaseTimings:
    """Collect wall-clock seconds for major pipeline stages and write phase_timings.json."""

    def __init__(self) -> None:
        self._sections: Dict[str, float] = {}
        self._active: Dict[str, float] = {}
        self.meta: Dict[str, Any] = {}

    def start(self, key: str) -> None:
        self._active[key] = monotonic()

    def stop(self, key: str) -> float:
        t0 = self._active.pop(key, None)
        if t0 is None:
            return 0.0
        elapsed = monotonic() - t0
        self._sections[key] = self._sections.get(key, 0.0) + elapsed
        return elapsed

    def set(self, key: str, seconds: float) -> None:
        self._sections[key] = float(seconds)

    def as_dict(self) -> Dict[str, Any]:
        sections = {k: round(v, 3) for k, v in sorted(self._sections.items())}
        measured_total = round(sum(self._sections.values()), 3)
        return {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "sections_seconds": sections,
            "total_measured_seconds": measured_total,
            **self.meta,
        }

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.as_dict(), indent=2, sort_keys=True), encoding="utf-8")


def write_run_manifest(path: Path, cfg: BacktestConfig, output_files: List[Path], args: argparse.Namespace) -> None:
    package_names = ["numpy", "pandas", "scikit-learn", "yfinance", "pyarrow", "matplotlib"]
    packages: Dict[str, str] = {}
    if importlib_metadata is not None:
        for name in package_names:
            try:
                packages[name] = importlib_metadata.version(name)
            except Exception:
                pass
    root = Path.cwd()
    files_to_hash = [
        root / "active_alpha_model.py",
        root / "paper_trading_engine.py",
        root / "build_sp500_membership_wikipedia.py",
        root / "check_active_alpha_core.py",
        root / "aa_models.py",
        root / "aa_features.py",
        root / "aa_portfolio.py",
        root / "aa_backtest.py",
        root / "aa_backtest_ml.py",
        root / "aa_execution.py",
        root / "aa_config.py",
        Path(cfg.membership_file),
    ]
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "app_version": __import__("aa_version", fromlist=["APP_VERSION"]).APP_VERSION,
        "model_profile": __import__("aa_version", fromlist=["MODEL_PROFILE"]).MODEL_PROFILE,
        "python": sys.version,
        "platform": platform.platform(),
        "packages": packages,
        "config": cfg.__dict__,
        "argv": sys.argv,
        "output_files": [str(Path(x)) for x in output_files],
        "file_hashes_sha256": {str(p): _hash_file(p) for p in files_to_hash if p.exists()},
        "ticker_count": getattr(args, "_ticker_count", None),
    }
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str), encoding="utf-8")


def fee_model_label(cfg: BacktestConfig) -> str:
    return f"trading212_us+fx_{float(getattr(cfg, 'trading212_fx_bps', 0.0)):g}bps+slippage_{float(getattr(cfg, 'slippage_bps', 0.0)):g}bps"


def effective_alpha_target_roundtrip_decimal(cfg: BacktestConfig) -> float:
    """Round-trip alpha-target haircut aligned with Trading-212 execution assumptions."""
    if not bool(getattr(cfg, "align_target_cost_with_execution", True)):
        return 2.0 * float(getattr(cfg, "cost_bps", 10.0) or 10.0) / 10_000.0
    slippage = float(getattr(cfg, "slippage_bps", 0.0) or 0.0)
    fx = float(getattr(cfg, "trading212_fx_bps", 15.0) or 0.0)
    impact = float(getattr(cfg, "market_impact_bps", 0.0) or 0.0)
    bps = 2.0 * slippage + fx + 2.0 * impact
    if bps <= 0.0:
        bps = float(getattr(cfg, "cost_bps", 10.0) or 10.0)
    return bps / 10_000.0


def estimate_backtest_trade_cost(trade_value: float, shares: float, side: str, cfg: BacktestConfig) -> Dict[str, float]:
    """Estimate Trading-212 execution costs for one backtest trade."""
    gross = abs(float(trade_value))
    shares = abs(float(shares))
    if not np.isfinite(gross) or gross <= 0 or not np.isfinite(shares) or shares <= 0:
        return {
            "commission": 0.0, "slippage": 0.0, "regulatory_fees": 0.0,
            "sec_fee": 0.0, "finra_taf": 0.0, "cat_fee": 0.0,
            "clearing_fee": 0.0, "exchange_fee": 0.0, "pass_through_fee": 0.0,
            "fx_fee": 0.0, "market_impact": 0.0, "total_cost": 0.0,
        }
    if str(getattr(cfg, "fee_model", "trading212_us")).lower() != "trading212_us":
        raise ValueError("Only fee_model='trading212_us' is supported.")
    side_u = str(side).upper()
    commission = 0.0
    slippage = gross * float(getattr(cfg, "slippage_bps", 0.0)) / 10_000.0
    fx_fee = gross * float(getattr(cfg, "trading212_fx_bps", 0.0)) / 10_000.0
    sec_fee = gross * float(getattr(cfg, "trading212_sec_fee_rate", 0.0000278)) if side_u == "SELL" else 0.0
    finra_taf = shares * float(getattr(cfg, "trading212_finra_taf_per_share", 0.000195)) if side_u == "SELL" else 0.0
    market_impact = gross * float(getattr(cfg, "market_impact_bps", 0.0)) / 10_000.0
    regulatory = sec_fee + finra_taf
    total = max(0.0, commission + slippage + regulatory + fx_fee + market_impact)
    return {
        "commission": float(commission),
        "slippage": float(slippage),
        "regulatory_fees": float(regulatory),
        "sec_fee": float(sec_fee),
        "finra_taf": float(finra_taf),
        "cat_fee": 0.0,
        "clearing_fee": 0.0,
        "exchange_fee": 0.0,
        "pass_through_fee": 0.0,
        "fx_fee": float(fx_fee),
        "market_impact": float(market_impact),
        "total_cost": float(total),
    }


def estimate_backtest_rebalance_costs(delta_weights: pd.Series, snapshot: pd.DataFrame, equity: float, cfg: BacktestConfig) -> Dict[str, float]:
    """Estimate dollar and relative costs for a complete backtest rebalance.

    delta_weights is the actual traded weight change after portfolio controls.
    Costs are calculated at current backtest equity and converted back to a
    portfolio-return drag. This function intentionally supports only the Trading-212 production broker model.
    """
    try:
        eq = float(equity)
    except Exception:
        eq = float(getattr(cfg, "backtest_capital", 100000.0) or 100000.0)
    if not np.isfinite(eq) or eq <= 0:
        eq = float(getattr(cfg, "backtest_capital", 100000.0) or 100000.0)

    zero = {
        "n_orders": 0.0,
        "tx_cost": 0.0,
        "commission_cost": 0.0,
        "slippage_cost": 0.0,
        "regulatory_fee_cost": 0.0,
        "sec_fee_cost": 0.0,
        "finra_taf_cost": 0.0,
        "cat_fee_cost": 0.0,
        "clearing_fee_cost": 0.0,
        "exchange_fee_cost": 0.0,
        "pass_through_fee_cost": 0.0,
        "fx_fee_cost": 0.0,
        "market_impact_cost": 0.0,
        "tx_cost_dollars": 0.0,
        "commission_dollars": 0.0,
        "slippage_dollars": 0.0,
        "regulatory_fees_dollars": 0.0,
        "sec_fee_dollars": 0.0,
        "finra_taf_dollars": 0.0,
        "cat_fee_dollars": 0.0,
        "clearing_fee_dollars": 0.0,
        "exchange_fee_dollars": 0.0,
        "pass_through_fee_dollars": 0.0,
        "fx_fee_dollars": 0.0,
        "market_impact_dollars": 0.0,
        "fee_price_fallback_orders": 0.0,
    }
    if delta_weights is None or delta_weights.empty or eq <= 0:
        return zero.copy()

    if snapshot is not None and not snapshot.empty and "ticker" in snapshot.columns:
        meta = snapshot.drop_duplicates("ticker").set_index("ticker")
        if "close" in meta.columns:
            prices = pd.to_numeric(meta["close"], errors="coerce")
        else:
            prices = pd.Series(dtype=float)
    else:
        prices = pd.Series(dtype=float)

    component_keys = [
        "commission", "slippage", "regulatory_fees", "sec_fee", "finra_taf", "cat_fee",
        "clearing_fee", "exchange_fee", "pass_through_fee", "fx_fee", "market_impact", "total_cost",
    ]
    totals = {k: 0.0 for k in component_keys}
    n_orders = 0
    fallback_orders = 0

    for ticker, delta in delta_weights.dropna().items():
        try:
            dw = float(delta)
        except Exception:
            continue
        if abs(dw) <= 1e-12:
            continue
        trade_value = abs(dw) * eq
        if not np.isfinite(trade_value) or trade_value <= 0.01:
            continue
        price = float(prices.get(ticker, np.nan)) if len(prices) else np.nan
        if not np.isfinite(price) or price <= 0:
            # Fallback keeps percentage components intact and gives a conservative
            # one-share proxy for per-share components instead of silently dropping fees.
            price = trade_value
            fallback_orders += 1
        shares = trade_value / price if price > 0 else 0.0
        side = "BUY" if dw > 0 else "SELL"
        cost = estimate_backtest_trade_cost(trade_value=trade_value, shares=shares, side=side, cfg=cfg)
        for key in component_keys:
            totals[key] += float(cost.get(key, 0.0))
        n_orders += 1

    total_cost = float(totals["total_cost"])
    out = zero.copy()
    out.update({
        "n_orders": float(n_orders),
        "tx_cost": total_cost / eq if eq > 0 else 0.0,
        "commission_cost": totals["commission"] / eq if eq > 0 else 0.0,
        "slippage_cost": totals["slippage"] / eq if eq > 0 else 0.0,
        "regulatory_fee_cost": totals["regulatory_fees"] / eq if eq > 0 else 0.0,
        "sec_fee_cost": totals["sec_fee"] / eq if eq > 0 else 0.0,
        "finra_taf_cost": totals["finra_taf"] / eq if eq > 0 else 0.0,
        "cat_fee_cost": totals["cat_fee"] / eq if eq > 0 else 0.0,
        "clearing_fee_cost": totals["clearing_fee"] / eq if eq > 0 else 0.0,
        "exchange_fee_cost": totals["exchange_fee"] / eq if eq > 0 else 0.0,
        "pass_through_fee_cost": totals["pass_through_fee"] / eq if eq > 0 else 0.0,
        "fx_fee_cost": totals["fx_fee"] / eq if eq > 0 else 0.0,
        "market_impact_cost": totals["market_impact"] / eq if eq > 0 else 0.0,
        "tx_cost_dollars": total_cost,
        "commission_dollars": totals["commission"],
        "slippage_dollars": totals["slippage"],
        "regulatory_fees_dollars": totals["regulatory_fees"],
        "sec_fee_dollars": totals["sec_fee"],
        "finra_taf_dollars": totals["finra_taf"],
        "cat_fee_dollars": totals["cat_fee"],
        "clearing_fee_dollars": totals["clearing_fee"],
        "exchange_fee_dollars": totals["exchange_fee"],
        "pass_through_fee_dollars": totals["pass_through_fee"],
        "fx_fee_dollars": totals["fx_fee"],
        "market_impact_dollars": totals["market_impact"],
        "fee_price_fallback_orders": float(fallback_orders),
    })
    return out

def apply_min_trade_value_filter(target: pd.Series, previous: pd.Series, equity: float, cfg: BacktestConfig) -> pd.Series:
    """Apply execution-level order hygiene to backtest target weights.

    The paper engine works in shares, but the backtest works in weights. This
    approximation applies the same dollar-level constraints: suppress sub-minimum
    orders, round non-liquidating order values to full-dollar increments, and
    sell to zero when a partial SELL would leave a broker-invalid residual below
    broker_min_remaining_position_value.
    """
    min_trade_value = float(getattr(cfg, "policy_min_trade_value", 0.0) or 0.0)
    order_value_rounding = max(float(getattr(cfg, "order_value_rounding", 0.0) or 0.0), 0.0)
    broker_min_remaining = max(float(getattr(cfg, "broker_min_remaining_position_value", 0.0) or 0.0), 0.0)
    if min_trade_value <= 0 and order_value_rounding <= 0 and broker_min_remaining <= 0:
        return target[target > 1e-12].sort_values(ascending=False)

    eq = float(equity) if np.isfinite(float(equity)) and float(equity) > 0 else float(getattr(cfg, "backtest_capital", 100000.0))
    if eq <= 0:
        return target[target > 1e-12].sort_values(ascending=False)

    all_names = target.index.union(previous.index)
    target_full = target.reindex(all_names).fillna(0.0).astype(float)
    prev_full = previous.reindex(all_names).fillna(0.0).astype(float)
    controlled = target_full.copy()

    residual_floor = max(float(getattr(cfg, "residual_weight_floor", 0.0) or 0.0), 0.0)
    residual_sell_min_value = max(float(getattr(cfg, "residual_sell_min_value", 0.0) or 0.0), 0.0)
    tail_prune_enabled = bool(getattr(cfg, "tail_prune_enabled", False))

    prev_w = prev_full.values.astype(float)
    tgt_w = controlled.values.astype(float)
    names = np.asarray(all_names, dtype=object)
    delta_w = tgt_w - prev_w
    active = np.abs(delta_w) > 1e-12
    if not active.any():
        return controlled[controlled > 1e-12].sort_values(ascending=False)

    trade_value = np.abs(delta_w) * eq
    is_sell = delta_w < 0.0
    allow_residual_sell_to_zero = (
        tail_prune_enabled
        & is_sell
        & (tgt_w <= 1e-12)
        & (prev_w > 1e-12)
        & (prev_w < residual_floor)
        & ((prev_w * eq) >= residual_sell_min_value)
    )

    if broker_min_remaining > 0:
        remaining_value = np.maximum(0.0, tgt_w) * eq
        liquidate_residual = is_sell & (remaining_value > 0.0) & (remaining_value < broker_min_remaining)
        tgt_w = np.where(liquidate_residual, 0.0, tgt_w)
        controlled.iloc[:] = tgt_w
        delta_w = tgt_w - prev_w
        trade_value = np.abs(delta_w) * eq
        is_sell = delta_w < 0.0

    if min_trade_value > 0:
        suppress = active & (trade_value < min_trade_value) & (~allow_residual_sell_to_zero)
        tgt_w = np.where(suppress, prev_w, tgt_w)
        controlled.iloc[:] = tgt_w
        delta_w = tgt_w - prev_w
        trade_value = np.abs(delta_w) * eq
        is_sell = delta_w < 0.0
        active = np.abs(delta_w) > 1e-12

    if order_value_rounding > 0:
        full_liquidation = is_sell & (prev_w > 1e-12) & (tgt_w <= 1e-12)
        round_mask = active & (~full_liquidation)
        if round_mask.any():
            prev_r = prev_w[round_mask]
            delta_r = tgt_w[round_mask] - prev_r
            tval_r = np.abs(delta_r) * eq
            rounded_val = np.floor(tval_r / order_value_rounding + 0.5) * order_value_rounding
            signed_val = np.where(delta_r > 0.0, rounded_val, -rounded_val)
            new_w = np.where(rounded_val <= 1e-12, prev_r, prev_r + signed_val / eq)
            sell_r = delta_r < 0.0
            new_w = np.where(sell_r, np.maximum(0.0, np.minimum(prev_r, new_w)), new_w)
            if broker_min_remaining > 0:
                remaining = new_w * eq
                liquidate = sell_r & (remaining > 0.0) & (remaining < broker_min_remaining)
                new_w = np.where(liquidate, 0.0, new_w)
            tgt_w[round_mask] = new_w
            controlled.iloc[:] = tgt_w

    controlled = controlled[controlled > 1e-12].sort_values(ascending=False)
    return controlled



def enforce_hard_position_count(weights: pd.Series, ranked: pd.DataFrame, cfg: BacktestConfig) -> pd.Series:
    """Final safety reducer for the hard position-count cap.

    The function never adds risk. It keeps the highest-priority names and leaves
    residual cash if the hard cap would otherwise be breached. The benchmark
    completion ticker, if present, is retained as one position because it carries
    market exposure.
    """
    if weights is None or weights.empty:
        return pd.Series(dtype=float)
    hard_cap = int(getattr(cfg, "max_n_positions_hard", 0) or 0)
    w = weights.replace([np.inf, -np.inf], np.nan).dropna().astype(float).clip(lower=0.0)
    w = w[w > 1e-12].sort_values(ascending=False)
    if hard_cap <= 0 or len(w) <= hard_cap:
        return w
    try:
        from aa_portfolio import _tail_keep_priority  # local import avoids module-level circular import
        priority = _tail_keep_priority(w, pd.Series(dtype=float), ranked, cfg)
    except Exception:
        # Fallback: keep the largest economically meaningful positions. This branch
        # should be rare, but it prevents a late NameError from aborting a completed run.
        priority = w.sort_values(ascending=False)
    keep = list(priority.index[:hard_cap])
    out = w.reindex(keep).dropna()
    return out[out > 1e-12].sort_values(ascending=False)

def final_position_hygiene_metrics(weights: pd.Series, cfg: BacktestConfig) -> Dict[str, float]:
    """Return final-position hygiene metrics after execution/min-trade filtering.

    These metrics distinguish economically meaningful positions from technical
    dust positions. The threshold deliberately reuses residual_weight_floor so
    the report remains aligned with the active tail-prune configuration.
    """
    if weights is None or weights.empty:
        return {
            "n_economic_positions_005": 0.0,
            "max_n_economic_positions_005": 0.0,
            "n_dust_positions_below_005": 0.0,
            "dust_weight_below_005": 0.0,
            "n_economic_positions_after_min_trade": 0.0,
            "n_dust_positions_after_min_trade": 0.0,
            "dust_weight_after_min_trade": 0.0,
            "economic_position_floor": float(max(float(getattr(cfg, "residual_weight_floor", 0.005) or 0.005), 0.0)),
        }
    floor = float(max(float(getattr(cfg, "residual_weight_floor", 0.005) or 0.005), 0.0))
    w = weights.astype(float)
    live = w[w > 1e-12]
    economic = live[live >= max(floor, 0.0) - 1e-12]
    dust = live[live < max(floor, 0.0) - 1e-12]
    return {
        "n_economic_positions_005": float(len(economic)),
        "n_dust_positions_below_005": float(len(dust)),
        "dust_weight_below_005": float(dust.sum()) if not dust.empty else 0.0,
        "n_economic_positions_after_min_trade": float(len(economic)),
        "n_dust_positions_after_min_trade": float(len(dust)),
        "dust_weight_after_min_trade": float(dust.sum()) if not dust.empty else 0.0,
        "economic_position_floor": floor,
    }


def apply_buy_hold_spread(
    target: pd.Series,
    previous: pd.Series,
    ranked: pd.DataFrame,
    cfg: BacktestConfig,
    *,
    forced_exit_tickers: Optional[set] = None,
) -> pd.Series:
    """Keep existing positions when they remain acceptable, even if not in new Top-K.

    This implements a buy/hold spread: new buys must pass the ordinary selection
    threshold, while existing holdings are allowed to stay until their rank has
    deteriorated materially.  It reduces unnecessary churn without freezing the
    portfolio, because exposure recovery still takes precedence later.
    """
    if not bool(getattr(cfg, "buy_hold_spread", True)) or previous.empty or ranked.empty:
        return target
    if "selection_score" not in ranked.columns or "ticker" not in ranked.columns:
        return target
    top_k = max(int(getattr(cfg, "top_k", 10)), 1)
    hold_rank = max(top_k, int(math.ceil(top_k * float(getattr(cfg, "hold_rank_multiple", 2.5) or 2.5))))
    from aa_portfolio import _selection_rank_map, project_to_valid_by_blending

    rank_map = _selection_rank_map(ranked)
    all_names = target.index.union(previous.index)
    out = target.reindex(all_names).fillna(0.0).astype(float)
    prev = previous.reindex(all_names).fillna(0.0).astype(float)
    forced = {str(t) for t in (forced_exit_tickers or set())}
    holds_added = False
    for tk, prev_w in prev.items():
        if prev_w <= 0 or out.get(tk, 0.0) > 0:
            continue
        if str(tk) in forced:
            continue
        r = rank_map.get(str(tk))
        if r is not None and r <= hold_rank:
            out.loc[tk] = min(float(prev_w), float(getattr(cfg, "max_position", 0.10)))
            holds_added = True
    out = out[out > 1e-12].sort_values(ascending=False)
    gross_cap = float(getattr(cfg, "max_gross_exposure", 1.0))
    exposure_scaled = False
    if out.sum() > gross_cap:
        out = out * (gross_cap / out.sum())
        exposure_scaled = True
    if not holds_added and not exposure_scaled:
        return target
    try:
        out = project_to_valid_by_blending(out, target, ranked, cfg, context="buy_hold_spread")
    except Exception:
        # Safer to preserve the original target than to keep an unvalidated hold-over portfolio.
        return target
    return out[out > 1e-12].sort_values(ascending=False)
