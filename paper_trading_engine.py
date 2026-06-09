#!/usr/bin/env python3
"""
Paper Trading Engine for Active Alpha Model.

Purpose
-------
Transforms latest_target_portfolio.csv from active_alpha_model.py into a
persistent virtual paper portfolio using current Yahoo Finance data.

It does not connect to a broker and does not place real orders.

Core outputs
------------
- paper_output/paper_state.json
- paper_output/paper_orders.csv
- paper_output/paper_trades.csv
- paper_output/paper_positions.csv
- paper_output/paper_equity.csv
- paper_output/paper_report.txt

Recommended operational sequence
--------------------------------
1. Run active_alpha_model.py in --mode signal after market close.
2. Run this engine in --mode rebalance with --execute.
3. Use paper_output as the source of truth for virtual portfolio state.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import sys
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

try:
    from rich.console import Console
    from rich.live import Live
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich import box

    RICH_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for minimal environments
    Console = None
    Live = None
    Panel = None
    Table = None
    Text = None
    box = None
    RICH_AVAILABLE = False


@dataclass
class DashboardState:
    title: str = "Active Alpha Paper Trading"
    phase: str = "Initialisierung"
    step: str = ""
    stage: int = 0
    total_stages: int = 1
    signal_date: str = "-"
    trade_date: str = "-"
    target_file: str = "-"
    paper_dir: str = "-"
    tickers: int = 0
    prices: int = 0
    missing_prices: int = 0
    n_orders: int = 0
    n_positions: int = 0
    cash: float = 0.0
    equity: float = 0.0
    positions_value: float = 0.0
    target_exposure: float = 0.0
    realized_exposure: float = 0.0
    turnover: float = 0.0
    costs: float = 0.0
    fee_model: str = "-"
    policy_mode: str = "manual"
    capital_profile: str = "-"
    policy_rebalance_every: int = 0
    policy_top_k: int = 0
    policy_max_position: float = 0.0
    policy_max_issuer: float = 0.0
    policy_risk_on_exposure_floor: float = 0.0
    policy_max_turnover: float = 0.0
    policy_no_trade_band: float = 0.0
    policy_min_trade_value: float = 0.0
    policy_fractional_recommended: bool = False
    policy_reason: str = ""
    benchmark: str = "SPY"
    benchmark_price: float = np.nan
    last_file: str = "-"
    warning: str = ""
    started_at: float = field(default_factory=time.time)

    @property
    def pct(self) -> float:
        if self.total_stages <= 0:
            return 0.0
        return max(0.0, min(1.0, self.stage / self.total_stages))

    @property
    def elapsed(self) -> str:
        return format_seconds(time.time() - self.started_at)

    @property
    def eta(self) -> str:
        if self.stage <= 0 or self.total_stages <= 0:
            return "-"
        elapsed = time.time() - self.started_at
        total = elapsed / max(self.stage, 1) * self.total_stages
        remaining = max(0.0, total - elapsed)
        return format_seconds(remaining)


class Dashboard:
    def __init__(self, state: DashboardState, *, plain: bool = False) -> None:
        self.state = state
        self.plain = plain or not RICH_AVAILABLE
        self.console = Console() if RICH_AVAILABLE and not self.plain else None
        self.live = None
        self._last_plain_stage = -1

    def __enter__(self):
        if self.plain:
            self._print_plain(force=True)
            return self
        self.live = Live(self._render(), console=self.console, refresh_per_second=4, transient=False)
        self.live.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.live is not None:
            self.live.update(self._render())
            self.live.stop()
        elif self.plain:
            self._print_plain(force=True)

    def update(self, **kwargs) -> None:
        for key, value in kwargs.items():
            if hasattr(self.state, key):
                setattr(self.state, key, value)
        if self.plain:
            self._print_plain()
        elif self.live is not None:
            self.live.update(self._render())

    def _bar(self, width: int = 36) -> str:
        filled = int(round(width * self.state.pct))
        filled = max(0, min(width, filled))
        return "█" * filled + "░" * (width - filled)

    def _render(self):
        st = self.state
        header = Text(st.title, style="bold cyan")
        header.append(f"  {st.stage}/{st.total_stages}  {st.pct * 100:5.1f}%", style="bold white")

        main = Table.grid(expand=True)
        main.add_column(ratio=1)

        status = Table(show_header=False, box=box.SIMPLE, expand=True, padding=(0, 1))
        status.add_column("Feld", style="bold white", width=24)
        status.add_column("Wert", style="white")
        status.add_row("Phase", st.phase)
        status.add_row("Schritt", st.step or "-")
        status.add_row("Fortschritt", f"[cyan]{self._bar()}[/cyan] {st.pct * 100:5.1f}%")
        status.add_row("Elapsed / ETA", f"{st.elapsed} / {st.eta}")
        status.add_row("Signal-Datum", st.signal_date)
        status.add_row("Trade-Datum", st.trade_date)
        status.add_row("Tickers / Preise / Fehlend", f"{st.tickers} / {st.prices} / {st.missing_prices}")
        status.add_row("Orders / Positionen", f"{st.n_orders} / {st.n_positions}")
        status.add_row("Cash", usd(st.cash))
        status.add_row("Positionswert", usd(st.positions_value))
        status.add_row("Equity", usd(st.equity))
        status.add_row("Target / Realized Exposure", f"{st.target_exposure:.2%} / {st.realized_exposure:.2%}")
        status.add_row("Turnover / Kosten", f"{st.turnover:.2%} / {usd(st.costs)}")
        status.add_row("Gebührenmodell", st.fee_model)
        if st.capital_profile and st.capital_profile != "-":
            status.add_row("Kapital-Policy", f"{st.policy_mode} / {st.capital_profile}")
            status.add_row("Policy Parameter", f"RB {st.policy_rebalance_every}d, Top-K {st.policy_top_k}, MaxPos {st.policy_max_position:.0%}, MaxIssuer {st.policy_max_issuer:.0%}, RiskFloor {st.policy_risk_on_exposure_floor:.0%}, TO {st.policy_max_turnover:.0%}, Band {st.policy_no_trade_band:.1%}, MinOrder {usd(st.policy_min_trade_value)}")
        bpx = "-" if not np.isfinite(st.benchmark_price) else f"{st.benchmark_price:,.2f}"
        status.add_row("Benchmark", f"{st.benchmark} @ {bpx}")
        status.add_row("Letzte Datei", st.last_file)
        if st.warning:
            status.add_row("Warnung", f"[yellow]{st.warning}[/yellow]")

        main.add_row(Panel(status, title=header, border_style="cyan"))
        return main

    def _print_plain(self, force: bool = False) -> None:
        st = self.state
        if not force and st.stage == self._last_plain_stage:
            return
        self._last_plain_stage = st.stage
        print(
            f"[{st.stage}/{st.total_stages}] {st.phase}: {st.step} | "
            f"Equity={usd(st.equity)} Cash={usd(st.cash)} Orders={st.n_orders} "
            f"Elapsed={st.elapsed} ETA={st.eta}"
        )
        if st.warning:
            print(f"[WARN] {st.warning}")


def format_seconds(seconds: float) -> str:
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def usd(x: float) -> str:
    try:
        if not np.isfinite(float(x)):
            return "-"
        return f"${float(x):,.2f}"
    except Exception:
        return "-"


def now_stamp() -> str:
    return pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")


def run_id() -> str:
    return pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")


def safe_float(x, default: float = 0.0) -> float:
    try:
        y = float(x)
        if np.isfinite(y):
            return y
        return default
    except Exception:
        return default


def round_half_up_to_increment(value: float, increment: float) -> float:
    """Round a positive dollar value to the nearest increment using half-up semantics."""
    inc = float(increment)
    val = float(value)
    if not np.isfinite(val) or val <= 0 or not np.isfinite(inc) or inc <= 0:
        return max(0.0, val if np.isfinite(val) else 0.0)
    return float(math.floor(val / inc + 0.5) * inc)


def adjust_order_shares_for_broker_constraints(
    *,
    side: str,
    trade_shares: float,
    price: float,
    prev_shares: float,
    order_value_rounding: float,
    broker_min_remaining_position_value: float,
) -> tuple[float, dict[str, float | bool | str]]:
    """Apply live-trading hygiene to generated paper orders.

    Non-liquidating BUY/SELL orders are rounded to full-dollar gross values when
    order_value_rounding > 0. Full sell-to-zero orders are kept as exact share
    liquidation because a broker cannot liquidate an exact holding and guarantee
    an integer-dollar fill value at the same time.

    SELL orders that would leave a positive residual position below
    broker_min_remaining_position_value are promoted to full sell-to-zero.
    """
    side_u = str(side).upper()
    px = abs(float(price))
    prev = max(0.0, float(prev_shares))
    signed = float(trade_shares)
    original_signed = signed
    reason = ""
    rounded = False
    residual_forced = False

    if px <= 0 or abs(signed) <= 1e-12:
        return signed, {
            "unrounded_gross_value": 0.0,
            "rounded_gross_value": 0.0,
            "rounding_adjustment": 0.0,
            "order_value_rounding": float(max(order_value_rounding, 0.0)),
            "broker_min_remaining_position_value": float(max(broker_min_remaining_position_value, 0.0)),
            "order_value_rounded": False,
            "broker_residual_sell_to_zero": False,
            "rounding_reason": "NO_ORDER",
        }

    # Clamp sells defensively before any rounding.
    if side_u == "SELL":
        signed = -min(abs(signed), prev)

    unrounded_gross = abs(signed) * px
    full_liquidation = side_u == "SELL" and prev > 1e-12 and abs(signed) >= prev - 1e-12

    if order_value_rounding > 0 and not full_liquidation:
        rounded_gross = round_half_up_to_increment(unrounded_gross, order_value_rounding)
        if rounded_gross <= 1e-12:
            signed = 0.0
            reason = "ROUNDED_TO_ZERO"
        else:
            rounded_abs_shares = rounded_gross / px
            if side_u == "SELL":
                rounded_abs_shares = min(rounded_abs_shares, prev)
                signed = -rounded_abs_shares
            else:
                signed = rounded_abs_shares
            rounded = abs((abs(signed) * px) - unrounded_gross) > 1e-9
            reason = "FULL_DOLLAR_ROUNDING" if rounded else "ALREADY_FULL_DOLLAR"

    # After rounding, enforce minimum remaining position value for sells.
    min_residual = max(float(broker_min_remaining_position_value), 0.0)
    if side_u == "SELL" and prev > 1e-12 and min_residual > 0 and abs(signed) > 1e-12:
        remaining_shares = max(0.0, prev - abs(signed))
        remaining_value = remaining_shares * px
        if 0.0 < remaining_value < min_residual:
            signed = -prev
            residual_forced = True
            full_liquidation = True
            reason = "BROKER_MIN_REMAINING_POSITION_SELL_TO_ZERO"

    adjusted_gross = abs(signed) * px
    return signed, {
        "unrounded_gross_value": float(unrounded_gross),
        "rounded_gross_value": float(adjusted_gross),
        "rounding_adjustment": float(adjusted_gross - unrounded_gross),
        "order_value_rounding": float(max(order_value_rounding, 0.0)),
        "broker_min_remaining_position_value": float(min_residual),
        "order_value_rounded": bool(rounded),
        "broker_residual_sell_to_zero": bool(residual_forced),
        "rounding_reason": reason or ("SELL_TO_ZERO_EXACT_SHARES" if full_liquidation else "NONE"),
    }


def read_csv_if_exists(path: Path, columns: Optional[List[str]] = None) -> pd.DataFrame:
    if path.exists() and path.stat().st_size > 0:
        return pd.read_csv(path)
    return pd.DataFrame(columns=columns or [])


def append_csv(path: Path, df: pd.DataFrame) -> None:
    """Append rows while preserving CSV schema compatibility.

    Older paper_equity.csv files can have fewer diagnostic columns than newer
    engine versions. Appending a wider row under an older header corrupts the
    CSV, so when columns differ the file is rewritten with the union schema.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        return
    if not path.exists() or path.stat().st_size == 0:
        df.to_csv(path, index=False)
        return

    try:
        existing = pd.read_csv(path)
    except Exception:
        backup = path.with_name(path.stem + ".corrupt_backup" + path.suffix)
        try:
            shutil.copy2(path, backup)
        except Exception:
            pass
        df.to_csv(path, index=False)
        return

    existing_cols = list(existing.columns)
    new_cols = list(df.columns)
    union_cols = existing_cols + [c for c in new_cols if c not in existing_cols]

    if existing_cols == new_cols:
        df.to_csv(path, mode="a", index=False, header=False)
        return

    combined = pd.concat(
        [existing.reindex(columns=union_cols), df.reindex(columns=union_cols)],
        ignore_index=True,
    )
    combined.to_csv(path, index=False)


def load_target_portfolio(path: Path, max_gross_exposure: float) -> Tuple[pd.DataFrame, List[str]]:
    if not path.exists():
        raise FileNotFoundError(f"Target portfolio not found: {path}")
    df = pd.read_csv(path)
    required = {"ticker", "target_weight"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Target portfolio missing columns: {sorted(missing)}")
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    df["target_weight"] = pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0)
    df = df[(df["ticker"] != "") & (df["target_weight"] > 1e-12)].copy()
    # Collapse duplicate ticker rows defensively.
    first_cols = [c for c in df.columns if c not in {"target_weight"}]
    agg = {"target_weight": "sum"}
    for c in first_cols:
        if c != "ticker":
            agg[c] = "first"
    df = df.groupby("ticker", as_index=False).agg(agg)
    warnings_list: List[str] = []
    gross = float(df["target_weight"].sum())
    if max_gross_exposure > 0 and gross > max_gross_exposure + 1e-8:
        scale = max_gross_exposure / gross
        df["target_weight"] *= scale
        warnings_list.append(
            f"Target weights scaled from {gross:.2%} to max_gross_exposure {max_gross_exposure:.2%}."
        )
    df.sort_values("target_weight", ascending=False, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df, warnings_list


def load_state(paper_dir: Path, initial_capital: float, reset: bool = False) -> Dict[str, object]:
    state_path = paper_dir / "paper_state.json"
    if reset and paper_dir.exists():
        for name in [
            "paper_state.json",
            "paper_positions.csv",
            "paper_orders.csv",
            "paper_trades.csv",
            "paper_equity.csv",
            "paper_report.txt",
        ]:
            p = paper_dir / name
            if p.exists():
                p.unlink()
    paper_dir.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    state = {
        "cash": float(initial_capital),
        "initial_capital": float(initial_capital),
        "created_at": now_stamp(),
        "last_run_id": "",
        "last_update": "",
    }
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def save_state(paper_dir: Path, state: Dict[str, object]) -> None:
    (paper_dir / "paper_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_positions(paper_dir: Path) -> pd.DataFrame:
    cols = ["ticker", "shares", "avg_cost", "last_price", "market_value", "weight", "updated_at"]
    df = read_csv_if_exists(paper_dir / "paper_positions.csv", cols)
    if df.empty:
        return pd.DataFrame(columns=cols)
    df = df.copy()
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    for c in ["shares", "avg_cost", "last_price", "market_value", "weight"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df = df[df["shares"].abs() > 1e-12].copy()
    df = df.drop_duplicates("ticker", keep="last")
    return df


def save_positions(paper_dir: Path, positions: pd.DataFrame) -> None:
    cols = ["ticker", "shares", "avg_cost", "last_price", "market_value", "weight", "updated_at"]
    if positions.empty:
        pd.DataFrame(columns=cols).to_csv(paper_dir / "paper_positions.csv", index=False)
        return
    positions = positions.copy()
    for c in cols:
        if c not in positions.columns:
            positions[c] = 0.0 if c not in {"ticker", "updated_at"} else ""
    positions = positions[cols]
    positions.to_csv(paper_dir / "paper_positions.csv", index=False)


def yahoo_download_prices(
    tickers: Iterable[str],
    *,
    period_days: int = 10,
    interval: str = "1d",
    dashboard: Optional[Dashboard] = None,
) -> Tuple[pd.DataFrame, Dict[str, float], Dict[str, str], List[str]]:
    tickers = sorted({str(t).upper().strip() for t in tickers if str(t).strip()})
    if not tickers:
        return pd.DataFrame(), {}, {}, []
    try:
        import yfinance as yf
    except ImportError as e:
        raise SystemExit("yfinance is not installed. Run: pip install -r requirements_active_alpha.txt") from e

    if dashboard:
        dashboard.update(
            phase="Yahoo Finance Daten",
            step=f"Lade aktuelle Preise für {len(tickers)} Symbole ...",
            tickers=len(tickers),
        )

    period = f"{max(2, int(period_days))}d"
    raw = yf.download(
        tickers,
        period=period,
        interval=interval,
        auto_adjust=True,
        group_by="ticker",
        threads=True,
        progress=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("Yahoo Finance returned no price data.")

    prices: Dict[str, float] = {}
    price_dates: Dict[str, str] = {}
    missing: List[str] = []

    def extract_single(single_df: pd.DataFrame, tk: str) -> None:
        if single_df is None or single_df.empty or "Close" not in single_df.columns:
            missing.append(tk)
            return
        close = pd.to_numeric(single_df["Close"], errors="coerce").dropna()
        if close.empty:
            missing.append(tk)
            return
        last_dt = close.index[-1]
        prices[tk] = float(close.iloc[-1])
        try:
            price_dates[tk] = pd.Timestamp(last_dt).strftime("%Y-%m-%d")
        except Exception:
            price_dates[tk] = str(last_dt)

    if isinstance(raw.columns, pd.MultiIndex):
        level0 = raw.columns.get_level_values(0)
        for tk in tickers:
            if tk in level0:
                extract_single(raw[tk].copy(), tk)
            else:
                missing.append(tk)
    else:
        # yfinance returns a single-column layout when only one ticker is requested.
        extract_single(raw.copy(), tickers[0])

    if dashboard:
        dashboard.update(prices=len(prices), missing_prices=len(missing))
    return raw, prices, price_dates, sorted(set(missing))


def mark_positions(
    positions: pd.DataFrame,
    prices: Dict[str, float],
    total_equity_hint: Optional[float] = None,
) -> pd.DataFrame:
    if positions.empty:
        return positions.copy()
    out = positions.copy()
    updated_prices = []
    for _, row in out.iterrows():
        tk = str(row["ticker"]).upper()
        px = prices.get(tk, safe_float(row.get("last_price", 0.0), 0.0))
        updated_prices.append(px)
    out["last_price"] = updated_prices
    out["market_value"] = out["shares"].astype(float) * out["last_price"].astype(float)
    total = float(out["market_value"].sum()) if total_equity_hint is None else float(total_equity_hint)
    if total > 0:
        out["weight"] = out["market_value"] / total
    else:
        out["weight"] = 0.0
    out["updated_at"] = now_stamp()
    return out


@dataclass
class FeeConfig:
    """Trading-212 execution-cost model used by the paper-trading ledger.

    This package intentionally supports only Trading 212 US stock execution:
    zero broker commission, configurable FX fee, sell-side US SEC/FINRA fees,
    plus optional slippage/spread and market-impact assumptions.
    """
    fee_model: str = "trading212_us"
    slippage_bps: float = 0.0
    market_impact_bps: float = 0.0
    trading212_sec_fee_rate: float = 0.0000278
    trading212_finra_taf_per_share: float = 0.000195
    trading212_fx_bps: float = 15.0

    @property
    def label(self) -> str:
        return f"trading212_us+fx_{self.trading212_fx_bps:g}bps+slippage_{self.slippage_bps:g}bps"


@dataclass
class CapitalAwarePolicy:
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


def _interp_log_capital(capital: float, anchors: List[Tuple[float, float]]) -> float:
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


def _snap_to_allowed(value: float, allowed: List[int]) -> int:
    allowed = sorted(int(v) for v in allowed)
    return min(allowed, key=lambda v: abs(float(v) - float(value)))

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


def choose_capital_curve_policy(capital: float, *, fee_model: str = "trading212_us", policy: str = "balanced") -> CapitalAwarePolicy:
    """Trading-212-only continuous execution policy used by paper trading.

    The paper engine enforces the minimum trade value and displays the policy;
    run_paper_trading.bat also passes the same policy to active_alpha_model.py so
    signal generation and paper execution remain aligned.
    """
    cap = float(capital)
    if not np.isfinite(cap) or cap <= 0:
        raise ValueError("capital must be positive")
    policy_name = str(policy or "balanced").lower().strip()
    if policy_name not in {"conservative", "balanced", "active", "threshold"}:
        raise ValueError("policy must be conservative, balanced, active or threshold")

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
            (1_000, 10),
            (5_000, 15),
            (25_000, 20),
            (100_000, 25),
        ]

        maxpos_anchors = [
            (1_000, 0.150),
            (5_000, 0.125),
            (25_000, 0.100),
            (100_000, 0.075),
        ]

        issuer_anchors = [
            (1_000, 0.150),
            (5_000, 0.125),
            (25_000, 0.100),
            (100_000, 0.075),
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
    else:
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
    max_position = _clip_float(maxpos_cont, 0.075, 0.20)
    max_issuer = _clip_float(maxissuer_cont, 0.075, 0.20)
    max_turnover = _clip_float(_interp_log_capital(cap, turnover_cap_anchors), 0.20, 0.55)
    no_trade_band = _clip_float(_interp_log_capital(cap, no_trade_band_anchors), 0.005, 0.03)
    min_trade_value = _smooth_micro_min_trade_value(
        cap,
        max_position,
        min_trade_value_anchors,
    )

    return CapitalAwarePolicy(
        capital=cap, profile="trading212_" + policy_name,
        rebalance_every=int(_snap_to_allowed(rb_cont, [5, 10, 20])),
        top_k=int(round(_clip_float(topk_cont, 8, 25))),
        max_position=float(max_position), max_issuer=float(max_issuer),
        risk_on_exposure_floor=float(risk_floor), max_turnover=float(max_turnover),
        no_trade_band=float(no_trade_band), min_trade_value=float(min_trade_value),
        max_annual_cost_budget=float(cost_budget), fractional_shares_recommended=True,
        continuous_rebalance_every=float(rb_cont), continuous_top_k=float(topk_cont),
        continuous_max_position=float(maxpos_cont), continuous_max_issuer=float(maxissuer_cont),
        policy_name=policy_name,
        reason=(f"Trading-212 {policy_name} policy: aligns paper execution with the signal model, "
                "using lower minimum order values, exposure-aware trading and threshold controls."),
    )


def choose_capital_aware_execution_policy(capital: float, *, fee_model: str = "trading212_us", policy: str = "balanced") -> CapitalAwarePolicy:
    return choose_capital_curve_policy(capital, fee_model=fee_model, policy=policy)


def policy_as_dict(policy: CapitalAwarePolicy, *, mode: str = "manual") -> Dict[str, object]:
    return {
        "execution_policy_mode": mode,
        "capital_profile": policy.profile,
        "policy_capital": float(policy.capital),
        "policy_rebalance_every": int(policy.rebalance_every),
        "policy_top_k": int(policy.top_k),
        "policy_max_position": float(policy.max_position),
        "policy_max_issuer": float(policy.max_issuer),
        "policy_risk_on_exposure_floor": float(policy.risk_on_exposure_floor),
        "policy_max_turnover": float(policy.max_turnover),
        "policy_no_trade_band": float(policy.no_trade_band),
        "policy_min_trade_value": float(policy.min_trade_value),
        "policy_max_annual_cost_budget": float(policy.max_annual_cost_budget),
        "policy_continuous_rebalance_every": float(policy.continuous_rebalance_every),
        "policy_continuous_top_k": float(policy.continuous_top_k),
        "policy_continuous_max_position": float(policy.continuous_max_position),
        "policy_continuous_max_issuer": float(policy.continuous_max_issuer),
        "policy_name": policy.policy_name,
        "policy_fractional_shares_recommended": bool(policy.fractional_shares_recommended),
        "policy_reason": policy.reason,
    }


def fee_config_from_args(args: argparse.Namespace) -> FeeConfig:
    return FeeConfig(
        fee_model="trading212_us",
        slippage_bps=float(args.slippage_bps),
        market_impact_bps=float(args.market_impact_bps),
        trading212_sec_fee_rate=float(args.trading212_sec_fee_rate),
        trading212_finra_taf_per_share=float(args.trading212_finra_taf_per_share),
        trading212_fx_bps=float(args.trading212_fx_bps),
    )


def estimate_trade_cost(shares: float, price: float, side: str, fee: FeeConfig) -> Dict[str, float | str]:
    """Estimate broker execution costs for a single paper-trading order."""
    shares = abs(float(shares))
    price = abs(float(price))
    gross = shares * price
    if shares <= 0 or price <= 0 or gross <= 0:
        return {
            "fee_model": fee.fee_model,
            "commission": 0.0, "slippage": 0.0, "regulatory_fees": 0.0,
            "sec_fee": 0.0, "finra_taf": 0.0, "cat_fee": 0.0,
            "clearing_fee": 0.0, "exchange_fee": 0.0, "pass_through_fee": 0.0,
            "fx_fee": 0.0, "market_impact": 0.0, "total_cost": 0.0,
        }

    side_u = str(side).upper()
    commission = 0.0
    slippage = gross * fee.slippage_bps / 10_000.0
    fx_fee = gross * fee.trading212_fx_bps / 10_000.0
    sec_fee = gross * fee.trading212_sec_fee_rate if side_u == "SELL" else 0.0
    finra_taf = shares * fee.trading212_finra_taf_per_share if side_u == "SELL" else 0.0
    cat_fee = clearing_fee = exchange_fee = pass_through_fee = 0.0
    market_impact = gross * fee.market_impact_bps / 10_000.0
    regulatory = sec_fee + finra_taf
    total = max(0.0, commission + slippage + regulatory + fx_fee + market_impact)
    return {
        "fee_model": fee.fee_model,
        "commission": float(commission),
        "slippage": float(slippage),
        "regulatory_fees": float(regulatory),
        "sec_fee": float(sec_fee),
        "finra_taf": float(finra_taf),
        "cat_fee": float(cat_fee),
        "clearing_fee": float(clearing_fee),
        "exchange_fee": float(exchange_fee),
        "pass_through_fee": float(pass_through_fee),
        "fx_fee": float(fx_fee),
        "market_impact": float(market_impact),
        "total_cost": float(total),
    }


def generate_orders(
    target: pd.DataFrame,
    positions: pd.DataFrame,
    prices: Dict[str, float],
    cash: float,
    *,
    fee_config: FeeConfig,
    fractional: bool,
    min_trade_value: float,
    max_gross_exposure: float,
    residual_weight_floor: float = 0.005,
    residual_sell_min_value: float = 0.01,
    allow_residual_sell_to_zero: bool = True,
    order_value_rounding: float = 1.0,
    broker_min_remaining_position_value: float = 1.0,
) -> Tuple[pd.DataFrame, Dict[str, float]]:
    current_shares = {str(r.ticker).upper(): safe_float(r.shares) for r in positions.itertuples(index=False)} if not positions.empty else {}
    current_avg = {str(r.ticker).upper(): safe_float(r.avg_cost) for r in positions.itertuples(index=False)} if not positions.empty else {}
    all_tickers = sorted(set(target["ticker"].astype(str)) | set(current_shares.keys()))

    # Use only priced holdings in equity. Missing held prices are expected to have been filled by last_price fallback.
    positions_value = sum(current_shares.get(tk, 0.0) * prices.get(tk, 0.0) for tk in current_shares)
    equity = float(cash) + float(positions_value)
    if equity <= 0:
        raise ValueError("Paper equity is not positive; cannot generate orders.")

    target_weights = dict(zip(target["ticker"].astype(str), target["target_weight"].astype(float)))
    target_gross = float(sum(max(0.0, w) for w in target_weights.values()))
    if max_gross_exposure > 0 and target_gross > max_gross_exposure:
        scale = max_gross_exposure / target_gross
        target_weights = {tk: w * scale for tk, w in target_weights.items()}
        target_gross = max_gross_exposure

    rows: List[Dict[str, object]] = []
    orders_blocked_by_min_trade_value = 0
    sell_to_zero_orders_below_min_trade = 0
    residual_sell_to_zero_orders = 0
    min_trade_value = max(float(min_trade_value), 0.0)
    residual_weight_floor = max(float(residual_weight_floor), 0.0)
    residual_sell_min_value = max(float(residual_sell_min_value), 0.0)
    order_value_rounding = max(float(order_value_rounding), 0.0)
    broker_min_remaining_position_value = max(float(broker_min_remaining_position_value), 0.0)
    orders_rounded_to_full_dollar = 0
    broker_residual_sell_to_zero_orders = 0
    for tk in all_tickers:
        price = prices.get(tk)
        if price is None or not np.isfinite(price) or price <= 0:
            continue
        prev_shares = current_shares.get(tk, 0.0)
        prev_value = prev_shares * price
        tw = max(0.0, float(target_weights.get(tk, 0.0)))
        target_value = tw * equity
        if fractional:
            desired_shares = target_value / price
        else:
            desired_shares = math.floor(target_value / price + 1e-12)
        trade_shares = desired_shares - prev_shares
        side = "BUY" if trade_shares > 0 else "SELL"
        current_weight = prev_value / equity if equity > 0 else 0.0

        trade_shares, rounding_info = adjust_order_shares_for_broker_constraints(
            side=side,
            trade_shares=trade_shares,
            price=price,
            prev_shares=prev_shares,
            order_value_rounding=order_value_rounding,
            broker_min_remaining_position_value=broker_min_remaining_position_value,
        )
        trade_value = trade_shares * price
        if abs(trade_shares) <= 1e-12 or abs(trade_value) <= 1e-12:
            continue
        side = "BUY" if trade_shares > 0 else "SELL"
        if bool(rounding_info.get("order_value_rounded", False)):
            orders_rounded_to_full_dollar += 1
        if bool(rounding_info.get("broker_residual_sell_to_zero", False)):
            broker_residual_sell_to_zero_orders += 1

        is_sell_to_zero = side == "SELL" and prev_shares > 1e-12 and abs(trade_shares) >= prev_shares - 1e-12
        residual_sell_to_zero = (
            bool(allow_residual_sell_to_zero)
            and is_sell_to_zero
            and (
                current_weight < residual_weight_floor
                or bool(rounding_info.get("broker_residual_sell_to_zero", False))
            )
            and abs(trade_value) >= residual_sell_min_value
        )
        if abs(trade_value) < min_trade_value and not residual_sell_to_zero:
            orders_blocked_by_min_trade_value += 1
            continue
        if residual_sell_to_zero:
            residual_sell_to_zero_orders += 1
            if abs(trade_value) < min_trade_value:
                sell_to_zero_orders_below_min_trade += 1
        _cost_info = estimate_trade_cost(abs(trade_shares), price, side, fee_config)
        rows.append(
            {
                "ticker": tk,
                "side": side,
                "shares": float(abs(trade_shares)),
                "signed_shares": float(trade_shares),
                "price": float(price),
                "gross_value": float(abs(trade_value)),
                "unrounded_gross_value": float(rounding_info.get("unrounded_gross_value", abs(trade_value))),
                "rounding_adjustment": float(rounding_info.get("rounding_adjustment", 0.0)),
                "order_value_rounding": float(rounding_info.get("order_value_rounding", order_value_rounding)),
                "order_value_rounded": bool(rounding_info.get("order_value_rounded", False)),
                "broker_min_remaining_position_value": float(rounding_info.get("broker_min_remaining_position_value", broker_min_remaining_position_value)),
                "broker_residual_sell_to_zero": bool(rounding_info.get("broker_residual_sell_to_zero", False)),
                "rounding_reason": str(rounding_info.get("rounding_reason", "")),
                "current_weight": float(current_weight),
                "residual_sell_to_zero": bool(residual_sell_to_zero),
                "min_trade_value_exempt": bool(residual_sell_to_zero and abs(trade_value) < min_trade_value),
                "estimated_cost": float(_cost_info["total_cost"]),
                "estimated_commission": float(_cost_info["commission"]),
                "estimated_slippage": float(_cost_info["slippage"]),
                "estimated_regulatory_fees": float(_cost_info["regulatory_fees"]),
                "estimated_sec_fee": float(_cost_info.get("sec_fee", 0.0)),
                "estimated_finra_taf": float(_cost_info.get("finra_taf", 0.0)),
                "estimated_cat_fee": float(_cost_info.get("cat_fee", 0.0)),
                "estimated_clearing_fee": float(_cost_info.get("clearing_fee", 0.0)),
                "estimated_exchange_fee": float(_cost_info.get("exchange_fee", 0.0)),
                "estimated_pass_through_fee": float(_cost_info.get("pass_through_fee", 0.0)),
                "estimated_fx_fee": float(_cost_info.get("fx_fee", 0.0)),
                "estimated_market_impact": float(_cost_info.get("market_impact", 0.0)),
                "fee_model": fee_config.fee_model,
                "previous_shares": float(prev_shares),
                "previous_value": float(prev_value),
                "target_weight": float(tw),
                "target_value": float(target_value),
                "current_avg_cost": float(current_avg.get(tk, 0.0)),
            }
        )
    # Broker hygiene sweep: even when the target portfolio implies no new
    # SELL order, do not carry a positive holding whose current market value is
    # below the broker minimum. This catches stale residuals from earlier runs.
    ordered_tickers = {str(r.get("ticker", "")).upper() for r in rows}
    if broker_min_remaining_position_value > 0:
        for tk in sorted(current_shares.keys()):
            if tk in ordered_tickers:
                continue
            price = prices.get(tk)
            if price is None or not np.isfinite(price) or price <= 0:
                continue
            prev_shares = current_shares.get(tk, 0.0)
            if prev_shares <= 1e-12:
                continue
            prev_value = prev_shares * price
            if not (0.0 < prev_value < broker_min_remaining_position_value):
                continue

            tw = max(0.0, float(target_weights.get(tk, 0.0)))
            target_value = tw * equity
            trade_shares = -float(prev_shares)
            trade_value = trade_shares * price
            _cost_info = estimate_trade_cost(abs(trade_shares), price, "SELL", fee_config)
            broker_residual_sell_to_zero_orders += 1
            residual_sell_to_zero_orders += 1
            if abs(trade_value) < min_trade_value:
                sell_to_zero_orders_below_min_trade += 1

            rows.append(
                {
                    "ticker": tk,
                    "side": "SELL",
                    "shares": float(abs(trade_shares)),
                    "signed_shares": float(trade_shares),
                    "price": float(price),
                    "gross_value": float(abs(trade_value)),
                    "unrounded_gross_value": float(abs(trade_value)),
                    "rounding_adjustment": 0.0,
                    "order_value_rounding": float(order_value_rounding),
                    "order_value_rounded": False,
                    "broker_min_remaining_position_value": float(broker_min_remaining_position_value),
                    "broker_residual_sell_to_zero": True,
                    "rounding_reason": "BROKER_MIN_POSITION_SWEEP_SELL_TO_ZERO",
                    "current_weight": float(prev_value / equity if equity > 0 else 0.0),
                    "residual_sell_to_zero": True,
                    "min_trade_value_exempt": bool(abs(trade_value) < min_trade_value),
                    "estimated_cost": float(_cost_info["total_cost"]),
                    "estimated_commission": float(_cost_info["commission"]),
                    "estimated_slippage": float(_cost_info["slippage"]),
                    "estimated_regulatory_fees": float(_cost_info["regulatory_fees"]),
                    "estimated_sec_fee": float(_cost_info.get("sec_fee", 0.0)),
                    "estimated_finra_taf": float(_cost_info.get("finra_taf", 0.0)),
                    "estimated_cat_fee": float(_cost_info.get("cat_fee", 0.0)),
                    "estimated_clearing_fee": float(_cost_info.get("clearing_fee", 0.0)),
                    "estimated_exchange_fee": float(_cost_info.get("exchange_fee", 0.0)),
                    "estimated_pass_through_fee": float(_cost_info.get("pass_through_fee", 0.0)),
                    "estimated_fx_fee": float(_cost_info.get("fx_fee", 0.0)),
                    "estimated_market_impact": float(_cost_info.get("market_impact", 0.0)),
                    "fee_model": fee_config.fee_model,
                    "previous_shares": float(prev_shares),
                    "previous_value": float(prev_value),
                    "target_weight": float(tw),
                    "target_value": float(target_value),
                    "current_avg_cost": float(current_avg.get(tk, 0.0)),
                }
            )

    orders = pd.DataFrame(rows)
    if orders.empty:
        orders = pd.DataFrame(
            columns=[
                "ticker",
                "side",
                "shares",
                "signed_shares",
                "price",
                "gross_value",
                "unrounded_gross_value",
                "rounding_adjustment",
                "order_value_rounding",
                "order_value_rounded",
                "broker_min_remaining_position_value",
                "broker_residual_sell_to_zero",
                "rounding_reason",
                "current_weight",
                "residual_sell_to_zero",
                "min_trade_value_exempt",
                "estimated_cost",
                "estimated_commission",
                "estimated_slippage",
                "estimated_regulatory_fees",
                "estimated_sec_fee",
                "estimated_finra_taf",
                "estimated_cat_fee",
                "estimated_clearing_fee",
                "estimated_exchange_fee",
                "estimated_pass_through_fee",
                "estimated_fx_fee",
                "estimated_market_impact",
                "fee_model",
                "previous_shares",
                "previous_value",
                "target_weight",
                "target_value",
                "current_avg_cost",
            ]
        )
    # Execute sells before buys for cash management.
    if not orders.empty:
        side_order = orders["side"].map({"SELL": 0, "BUY": 1}).fillna(2)
        orders = orders.assign(_side_order=side_order).sort_values(["_side_order", "ticker"]).drop(columns="_side_order")
        orders.reset_index(drop=True, inplace=True)
    diagnostics = {
        "cash": float(cash),
        "positions_value": float(positions_value),
        "equity": float(equity),
        "target_exposure": float(target_gross),
        "orders_blocked_by_min_trade_value": float(orders_blocked_by_min_trade_value),
        "sell_to_zero_orders_below_min_trade": float(sell_to_zero_orders_below_min_trade),
        "residual_sell_to_zero_orders": float(residual_sell_to_zero_orders),
        "residual_weight_floor": float(residual_weight_floor),
        "residual_sell_min_value": float(residual_sell_min_value),
        "order_value_rounding": float(order_value_rounding),
        "broker_min_remaining_position_value": float(broker_min_remaining_position_value),
        "orders_rounded_to_full_dollar": float(orders_rounded_to_full_dollar),
        "broker_residual_sell_to_zero_orders": float(broker_residual_sell_to_zero_orders),
    }
    return orders, diagnostics


def apply_orders(
    orders: pd.DataFrame,
    positions: pd.DataFrame,
    cash: float,
    *,
    fee_config: FeeConfig,
    fractional: bool,
) -> Tuple[pd.DataFrame, float, pd.DataFrame, float, float]:
    positions_map: Dict[str, Dict[str, float]] = {}
    if not positions.empty:
        for r in positions.itertuples(index=False):
            tk = str(r.ticker).upper()
            positions_map[tk] = {
                "shares": safe_float(r.shares),
                "avg_cost": safe_float(r.avg_cost),
                "last_price": safe_float(r.last_price),
            }

    executed_rows: List[Dict[str, object]] = []
    cash_after = float(cash)
    total_costs = 0.0
    turnover_value = 0.0

    # First, execute all sells as requested.
    sells = orders[orders["side"] == "SELL"].copy() if not orders.empty else pd.DataFrame()
    buys = orders[orders["side"] == "BUY"].copy() if not orders.empty else pd.DataFrame()

    for row in sells.itertuples(index=False):
        tk = str(row.ticker).upper()
        price = safe_float(row.price)
        req_shares = safe_float(row.shares)
        pos = positions_map.get(tk, {"shares": 0.0, "avg_cost": 0.0, "last_price": price})
        exec_shares = min(req_shares, max(0.0, pos["shares"]))
        if exec_shares <= 0 or price <= 0:
            continue
        gross = exec_shares * price
        cost_info = estimate_trade_cost(exec_shares, price, "SELL", fee_config)
        cost = float(cost_info["total_cost"])
        cash_after += gross - cost
        pos["shares"] -= exec_shares
        pos["last_price"] = price
        total_costs += cost
        turnover_value += gross
        positions_map[tk] = pos
        executed_rows.append(order_execution_row(row, exec_shares, price, gross, cost_info, cash_after))

    # Then, scale buy orders if costs would exceed available cash.
    if not buys.empty:
        requested_cash = float((buys["shares"] * buys["price"] + buys["estimated_cost"].fillna(0.0)).sum())
        scale = 1.0 if requested_cash <= cash_after + 1e-8 else max(0.0, cash_after / requested_cash)
        for row in buys.itertuples(index=False):
            tk = str(row.ticker).upper()
            price = safe_float(row.price)
            req_shares = safe_float(row.shares) * scale
            if not fractional:
                req_shares = math.floor(req_shares + 1e-12)
            if req_shares <= 0 or price <= 0:
                continue
            gross = req_shares * price
            cost_info = estimate_trade_cost(req_shares, price, "BUY", fee_config)
            cost = float(cost_info["total_cost"])
            total_cash_needed = gross + cost
            if total_cash_needed > cash_after + 1e-8:
                req_shares = max_affordable_buy_shares(req_shares, price, cash_after, fee_config, fractional)
                gross = req_shares * price
                cost_info = estimate_trade_cost(req_shares, price, "BUY", fee_config)
                cost = float(cost_info["total_cost"])
                total_cash_needed = gross + cost
            if req_shares <= 0 or total_cash_needed > cash_after + 1e-8:
                continue
            pos = positions_map.get(tk, {"shares": 0.0, "avg_cost": 0.0, "last_price": price})
            old_shares = pos["shares"]
            old_basis = old_shares * pos["avg_cost"]
            new_shares = old_shares + req_shares
            new_basis = old_basis + gross + cost
            pos["shares"] = new_shares
            pos["avg_cost"] = new_basis / new_shares if new_shares > 0 else 0.0
            pos["last_price"] = price
            positions_map[tk] = pos
            cash_after -= total_cash_needed
            total_costs += cost
            turnover_value += gross
            executed_rows.append(order_execution_row(row, req_shares, price, gross, cost_info, cash_after))

    pos_rows = []
    updated_at = now_stamp()
    for tk, pos in sorted(positions_map.items()):
        shares = safe_float(pos.get("shares"))
        if shares <= 1e-12:
            continue
        px = safe_float(pos.get("last_price"))
        pos_rows.append(
            {
                "ticker": tk,
                "shares": float(shares),
                "avg_cost": float(pos.get("avg_cost", 0.0)),
                "last_price": float(px),
                "market_value": float(shares * px),
                "weight": 0.0,
                "updated_at": updated_at,
            }
        )
    new_positions = pd.DataFrame(pos_rows)
    if not new_positions.empty:
        equity = cash_after + float(new_positions["market_value"].sum())
        new_positions["weight"] = new_positions["market_value"] / equity if equity > 0 else 0.0
    executed = pd.DataFrame(executed_rows)
    return new_positions, float(cash_after), executed, float(total_costs), float(turnover_value)


def order_execution_row(row, exec_shares: float, price: float, gross: float, cost_info: Dict[str, float | str], cash_after: float) -> Dict[str, object]:
    side = str(row.side)
    signed = exec_shares if side == "BUY" else -exec_shares
    cost = float(cost_info.get("total_cost", 0.0))
    return {
        "ticker": str(row.ticker).upper(),
        "side": side,
        "shares": float(exec_shares),
        "signed_shares": float(signed),
        "price": float(price),
        "gross_value": float(gross),
        "cost": float(cost),
        "commission": float(cost_info.get("commission", 0.0)),
        "slippage": float(cost_info.get("slippage", 0.0)),
        "regulatory_fees": float(cost_info.get("regulatory_fees", 0.0)),
        "sec_fee": float(cost_info.get("sec_fee", 0.0)),
        "finra_taf": float(cost_info.get("finra_taf", 0.0)),
        "cat_fee": float(cost_info.get("cat_fee", 0.0)),
        "clearing_fee": float(cost_info.get("clearing_fee", 0.0)),
        "exchange_fee": float(cost_info.get("exchange_fee", 0.0)),
        "pass_through_fee": float(cost_info.get("pass_through_fee", 0.0)),
        "fx_fee": float(cost_info.get("fx_fee", 0.0)),
        "market_impact": float(cost_info.get("market_impact", 0.0)),
        "fee_model": str(cost_info.get("fee_model", "")),
        "cash_after": float(cash_after),
        "previous_shares": safe_float(getattr(row, "previous_shares", 0.0)),
        "previous_value": safe_float(getattr(row, "previous_value", 0.0)),
        "target_weight": safe_float(getattr(row, "target_weight", 0.0)),
        "target_value": safe_float(getattr(row, "target_value", 0.0)),
        "unrounded_gross_value": safe_float(getattr(row, "unrounded_gross_value", gross)),
        "rounding_adjustment": safe_float(getattr(row, "rounding_adjustment", 0.0)),
        "order_value_rounding": safe_float(getattr(row, "order_value_rounding", 0.0)),
        "order_value_rounded": bool(getattr(row, "order_value_rounded", False)),
        "broker_min_remaining_position_value": safe_float(getattr(row, "broker_min_remaining_position_value", 0.0)),
        "broker_residual_sell_to_zero": bool(getattr(row, "broker_residual_sell_to_zero", False)),
        "rounding_reason": str(getattr(row, "rounding_reason", "")),
    }


def build_equity_row(
    *,
    rid: str,
    mode: str,
    signal_date: str,
    trade_date: str,
    cash: float,
    positions: pd.DataFrame,
    benchmark: str,
    benchmark_price: float,
    costs: float,
    commission: float = 0.0,
    slippage: float = 0.0,
    regulatory_fees: float = 0.0,
    sec_fee: float = 0.0,
    finra_taf: float = 0.0,
    cat_fee: float = 0.0,
    clearing_fee: float = 0.0,
    exchange_fee: float = 0.0,
    pass_through_fee: float = 0.0,
    fx_fee: float = 0.0,
    market_impact: float = 0.0,
    fee_model: str = "",
    turnover_value: float = 0.0,
    target_exposure: float,
    missing_prices: int,
    paper_dir: Path,
) -> Dict[str, object]:
    positions_value = float(positions["market_value"].sum()) if not positions.empty else 0.0
    total_equity = float(cash) + positions_value
    realized_exposure = positions_value / total_equity if total_equity > 0 else 0.0
    prev = read_csv_if_exists(paper_dir / "paper_equity.csv")
    prev_equity = np.nan
    prev_bench = np.nan
    if not prev.empty:
        prev_equity = safe_float(prev.iloc[-1].get("total_equity", np.nan), np.nan)
        prev_bench = safe_float(prev.iloc[-1].get("benchmark_price", np.nan), np.nan)
    paper_return = total_equity / prev_equity - 1.0 if np.isfinite(prev_equity) and prev_equity > 0 else np.nan
    benchmark_return = benchmark_price / prev_bench - 1.0 if np.isfinite(prev_bench) and prev_bench > 0 and np.isfinite(benchmark_price) else np.nan
    turnover = turnover_value / total_equity if total_equity > 0 else 0.0
    return {
        "run_id": rid,
        "mode": mode,
        "date": trade_date,
        "signal_date": signal_date,
        "cash": float(cash),
        "positions_value": float(positions_value),
        "total_equity": float(total_equity),
        "paper_return": paper_return,
        "benchmark_ticker": benchmark,
        "benchmark_price": benchmark_price,
        "benchmark_return": benchmark_return,
        "costs": float(costs),
        "commission": float(commission),
        "slippage": float(slippage),
        "regulatory_fees": float(regulatory_fees),
        "sec_fee": float(sec_fee),
        "finra_taf": float(finra_taf),
        "cat_fee": float(cat_fee),
        "clearing_fee": float(clearing_fee),
        "exchange_fee": float(exchange_fee),
        "pass_through_fee": float(pass_through_fee),
        "fx_fee": float(fx_fee),
        "market_impact": float(market_impact),
        "fee_model": str(fee_model),
        "turnover_value": float(turnover_value),
        "turnover": float(turnover),
        "target_exposure": float(target_exposure),
        "realized_exposure": float(realized_exposure),
        "n_positions": int((positions["shares"] > 1e-12).sum()) if not positions.empty else 0,
        "missing_prices": int(missing_prices),
    }


def position_hygiene_metrics(positions: pd.DataFrame, residual_weight_floor: float = 0.005) -> Dict[str, float]:
    """Separate real economic positions from tiny residual/dust holdings."""
    floor = max(float(residual_weight_floor or 0.0), 0.0)
    if positions is None or positions.empty or "weight" not in positions.columns:
        return {
            "economic_position_floor": float(floor),
            "n_economic_positions_005": 0.0,
            "n_dust_positions_below_005": 0.0,
            "dust_weight_below_005": 0.0,
            "n_economic_positions_after_min_trade": 0.0,
            "n_dust_positions_after_min_trade": 0.0,
            "dust_weight_after_min_trade": 0.0,
        }
    w = pd.to_numeric(positions["weight"], errors="coerce").fillna(0.0).astype(float)
    live = w[w > 1e-12]
    economic = live[live >= floor - 1e-12]
    dust = live[live < floor - 1e-12]
    return {
        "economic_position_floor": float(floor),
        "n_economic_positions_005": float(len(economic)),
        "n_dust_positions_below_005": float(len(dust)),
        "dust_weight_below_005": float(dust.sum()) if len(dust) else 0.0,
        "n_economic_positions_after_min_trade": float(len(economic)),
        "n_dust_positions_after_min_trade": float(len(dust)),
        "dust_weight_after_min_trade": float(dust.sum()) if len(dust) else 0.0,
    }


def extract_model_diagnostics_from_target(target: pd.DataFrame) -> Dict[str, object]:
    """Carry model-side diagnostic columns from latest_target_portfolio.csv into paper reports."""
    out: Dict[str, object] = {}
    if target is None or target.empty:
        return out
    df = target.copy()
    if "target_weight" in df.columns:
        out["model_target_exposure_from_file"] = float(pd.to_numeric(df["target_weight"], errors="coerce").fillna(0.0).sum())
    for col in [
        "signal_date", "risk_on", "desired_exposure", "regime_target_exposure", "target_exposure",
        "exposure_before_constraints", "exposure_after_position_cap", "exposure_after_issuer_cap",
        "exposure_after_sector_cap", "exposure_after_cluster_cap", "exposure_after_beta_cap",
        "portfolio_exposure", "portfolio_beta", "max_position_weight", "max_issuer_weight", "max_sector_weight",
        "max_correlation_cluster_weight", "gross_exposure_binding", "max_position_binding", "max_issuer_binding",
        "max_sector_binding", "max_cluster_binding", "max_beta_binding", "n_candidates", "n_eligible_candidates",
        "n_selected_candidates", "n_rejected_by_membership", "n_rejected_by_adv", "n_rejected_by_vol",
        "unknown_sector_weight", "unknown_cluster_weight", "unknown_issuer_weight",
        "n_unknown_sector_positions", "n_unknown_cluster_positions", "n_unknown_issuer_positions",
    ]:
        if col in df.columns and df[col].notna().any():
            val = df[col].dropna().iloc[0]
            if isinstance(val, (np.bool_, bool)):
                out[f"model_{col}"] = bool(val)
            else:
                try:
                    f = float(val)
                    out[f"model_{col}"] = f if np.isfinite(f) else str(val)
                except Exception:
                    out[f"model_{col}"] = str(val)
    desired = safe_float(out.get("model_desired_exposure", out.get("model_target_exposure", out.get("model_target_exposure_from_file", 0.0))))
    realized_target = safe_float(out.get("model_target_exposure_from_file", 0.0))
    out["model_cash_gap_vs_desired_exposure"] = max(0.0, desired - realized_target)
    drops = {
        "position_cap": max(0.0, safe_float(out.get("model_exposure_before_constraints", desired)) - safe_float(out.get("model_exposure_after_position_cap", desired))),
        "issuer_cap": max(0.0, safe_float(out.get("model_exposure_after_position_cap", desired)) - safe_float(out.get("model_exposure_after_issuer_cap", desired))),
        "sector_cap": max(0.0, safe_float(out.get("model_exposure_after_issuer_cap", desired)) - safe_float(out.get("model_exposure_after_sector_cap", desired))),
        "cluster_cap": max(0.0, safe_float(out.get("model_exposure_after_sector_cap", desired)) - safe_float(out.get("model_exposure_after_cluster_cap", desired))),
        "beta_cap": max(0.0, safe_float(out.get("model_exposure_after_cluster_cap", desired)) - safe_float(out.get("model_exposure_after_beta_cap", realized_target))),
    }
    if safe_float(out.get("model_cash_gap_vs_desired_exposure", 0.0)) > 1e-8:
        reason, amount = max(drops.items(), key=lambda kv: kv[1])
        out["model_cash_reason"] = reason if amount > 1e-8 else "signal_shortage_or_unattributed_constraints"
    else:
        out["model_cash_reason"] = "target_file_fully_allocated_vs_model_desired"
    for k, v in drops.items():
        out[f"model_cash_due_to_{k}"] = float(v)
    return out


def write_report(
    path: Path,
    *,
    rid: str,
    mode: str,
    target_file: Path,
    signal_date: str,
    trade_date: str,
    cash: float,
    positions: pd.DataFrame,
    orders: pd.DataFrame,
    executed: pd.DataFrame,
    equity_row: Dict[str, object],
    missing: List[str],
    warnings_list: List[str],
    fee_config: FeeConfig,
    fractional: bool,
) -> None:
    lines: List[str] = []
    lines.append("Active Alpha Paper Trading Report")
    lines.append("=================================")
    lines.append("")
    lines.append("Run")
    lines.append("---")
    lines.append(f"run_id: {rid}")
    lines.append(f"mode: {mode}")
    lines.append(f"target_file: {target_file}")
    lines.append(f"signal_date: {signal_date}")
    lines.append(f"trade_date: {trade_date}")
    lines.append(f"fee_model: {fee_config.fee_model}")
    lines.append(f"slippage_bps: {fee_config.slippage_bps}")
    lines.append(f"market_impact_bps: {fee_config.market_impact_bps}")
    lines.append(f"trading212_sec_fee_rate: {fee_config.trading212_sec_fee_rate}")
    lines.append(f"trading212_finra_taf_per_share: {fee_config.trading212_finra_taf_per_share}")
    lines.append(f"trading212_fx_bps: {fee_config.trading212_fx_bps}")
    lines.append(f"fractional_shares: {fractional}")
    lines.append("")
    lines.append("Capital-aware execution policy")
    lines.append("------------------------------")
    lines.append(f"execution_policy_mode: {equity_row.get('execution_policy_mode', 'manual')}")
    lines.append(f"capital_profile: {equity_row.get('capital_profile', '-')}")
    lines.append(f"policy_capital: {safe_float(equity_row.get('policy_capital', 0.0)):.2f}")
    lines.append(f"recommended_rebalance_every: {int(equity_row.get('policy_rebalance_every', 0) or 0)}")
    lines.append(f"recommended_top_k: {int(equity_row.get('policy_top_k', 0) or 0)}")
    lines.append(f"recommended_max_position: {safe_float(equity_row.get('policy_max_position', 0.0)):.6f}")
    lines.append(f"recommended_max_issuer: {safe_float(equity_row.get('policy_max_issuer', 0.0)):.6f}")
    lines.append(f"recommended_risk_on_exposure_floor: {safe_float(equity_row.get('policy_risk_on_exposure_floor', 0.0)):.6f}")
    lines.append(f"recommended_max_turnover: {safe_float(equity_row.get('policy_max_turnover', 0.0)):.6f}")
    lines.append(f"recommended_no_trade_band: {safe_float(equity_row.get('policy_no_trade_band', 0.0)):.6f}")
    lines.append(f"recommended_min_trade_value: {safe_float(equity_row.get('policy_min_trade_value', 0.0)):.2f}")
    lines.append(f"applied_min_trade_value: {safe_float(equity_row.get('policy_applied_min_trade_value', 0.0)):.2f}")
    lines.append(f"residual_weight_floor: {safe_float(equity_row.get('residual_weight_floor', 0.0)):.6f}")
    lines.append(f"residual_sell_min_value: {safe_float(equity_row.get('residual_sell_min_value', 0.0)):.2f}")
    lines.append(f"order_value_rounding: {safe_float(equity_row.get('order_value_rounding', 0.0)):.2f}")
    lines.append(f"broker_min_remaining_position_value: {safe_float(equity_row.get('broker_min_remaining_position_value', 0.0)):.2f}")
    lines.append(f"fractional_shares_recommended: {equity_row.get('policy_fractional_shares_recommended', False)}")
    lines.append(f"policy_reason: {equity_row.get('policy_reason', '')}")
    lines.append("")
    lines.append("Portfolio")
    lines.append("---------")
    lines.append(f"cash: {cash:.2f}")
    lines.append(f"positions_value: {safe_float(equity_row.get('positions_value')):.2f}")
    lines.append(f"total_equity: {safe_float(equity_row.get('total_equity')):.2f}")
    lines.append(f"realized_exposure: {safe_float(equity_row.get('realized_exposure')):.6f}")
    lines.append(f"target_exposure: {safe_float(equity_row.get('target_exposure')):.6f}")
    lines.append(f"n_positions: {int(equity_row.get('n_positions', 0))}")
    lines.append(f"economic_position_floor: {safe_float(equity_row.get('economic_position_floor', 0.0)):.6f}")
    lines.append(f"n_economic_positions_005: {safe_float(equity_row.get('n_economic_positions_005', 0.0)):.0f}")
    lines.append(f"n_dust_positions_below_005: {safe_float(equity_row.get('n_dust_positions_below_005', 0.0)):.0f}")
    lines.append(f"dust_weight_below_005: {safe_float(equity_row.get('dust_weight_below_005', 0.0)):.6f}")
    lines.append("")
    lines.append("Model diagnostics / exposure bridge")
    lines.append("-----------------------------------")
    for _k in [
        "model_risk_on", "model_desired_exposure", "model_regime_target_exposure", "model_target_exposure_from_file",
        "model_exposure_before_constraints", "model_exposure_after_position_cap", "model_exposure_after_issuer_cap",
        "model_exposure_after_sector_cap", "model_exposure_after_cluster_cap", "model_exposure_after_beta_cap",
        "model_portfolio_exposure", "model_portfolio_beta", "model_max_position_weight", "model_max_issuer_weight",
        "model_max_sector_weight", "model_max_correlation_cluster_weight", "model_gross_exposure_binding",
        "model_max_position_binding", "model_max_issuer_binding", "model_max_sector_binding", "model_max_cluster_binding",
        "model_max_beta_binding", "model_cash_gap_vs_desired_exposure", "model_cash_reason",
        "model_cash_due_to_position_cap", "model_cash_due_to_issuer_cap", "model_cash_due_to_sector_cap",
        "model_cash_due_to_cluster_cap", "model_cash_due_to_beta_cap", "model_n_candidates", "model_n_eligible_candidates",
        "model_n_selected_candidates", "model_unknown_sector_weight", "model_unknown_cluster_weight", "model_unknown_issuer_weight",
    ]:
        if _k in equity_row:
            _v = equity_row.get(_k)
            lines.append(f"{_k}: {safe_float(_v):.6f}" if isinstance(_v, (float, int, np.floating, np.integer)) else f"{_k}: {_v}")
    lines.append("")
    lines.append("Trading")
    lines.append("-------")
    lines.append(f"orders_generated: {len(orders)}")
    lines.append(f"orders_executed: {len(executed)}")
    lines.append(f"costs: {safe_float(equity_row.get('costs')):.2f}")
    lines.append(f"commission: {safe_float(equity_row.get('commission')):.2f}")
    lines.append(f"slippage: {safe_float(equity_row.get('slippage')):.2f}")
    lines.append(f"regulatory_fees: {safe_float(equity_row.get('regulatory_fees')):.2f}")
    lines.append(f"fx_fee: {safe_float(equity_row.get('fx_fee')):.2f}")
    lines.append(f"sec_fee: {safe_float(equity_row.get('sec_fee')):.2f}")
    lines.append(f"finra_taf: {safe_float(equity_row.get('finra_taf')):.2f}")
    lines.append(f"cat_fee: {safe_float(equity_row.get('cat_fee')):.2f}")
    lines.append(f"clearing_fee: {safe_float(equity_row.get('clearing_fee')):.2f}")
    lines.append(f"exchange_fee: {safe_float(equity_row.get('exchange_fee')):.2f}")
    lines.append(f"pass_through_fee: {safe_float(equity_row.get('pass_through_fee')):.2f}")
    lines.append(f"market_impact: {safe_float(equity_row.get('market_impact')):.2f}")
    lines.append(f"turnover: {safe_float(equity_row.get('turnover')):.6f}")
    lines.append(f"orders_blocked_by_min_trade_value: {safe_float(equity_row.get('orders_blocked_by_min_trade_value', 0.0)):.0f}")
    lines.append(f"sell_to_zero_orders_below_min_trade: {safe_float(equity_row.get('sell_to_zero_orders_below_min_trade', 0.0)):.0f}")
    lines.append(f"residual_sell_to_zero_orders: {safe_float(equity_row.get('residual_sell_to_zero_orders', 0.0)):.0f}")
    lines.append(f"orders_rounded_to_full_dollar: {safe_float(equity_row.get('orders_rounded_to_full_dollar', 0.0)):.0f}")
    lines.append(f"broker_residual_sell_to_zero_orders: {safe_float(equity_row.get('broker_residual_sell_to_zero_orders', 0.0)):.0f}")
    lines.append("")
    if missing:
        lines.append("Missing Yahoo prices")
        lines.append("--------------------")
        lines.append(", ".join(missing[:100]))
        if len(missing) > 100:
            lines.append(f"... plus {len(missing)-100} more")
        lines.append("")
    if warnings_list:
        lines.append("Warnings")
        lines.append("--------")
        for w in warnings_list:
            lines.append(f"- {w}")
        lines.append("")
    if not executed.empty:
        lines.append("Executed orders, top 25 by gross value")
        lines.append("--------------------------------------")
        view = executed.sort_values("gross_value", ascending=False).head(25)
        for r in view.itertuples(index=False):
            lines.append(f"{r.side:4s} {r.ticker:8s} shares={float(r.shares):,.4f} price={float(r.price):,.2f} gross={float(r.gross_value):,.2f} cost={float(r.cost):,.2f} commission={safe_float(getattr(r, 'commission', 0.0)):.2f} slippage={safe_float(getattr(r, 'slippage', 0.0)):.2f}")
        lines.append("")
    lines.append("Interpretation")
    lines.append("--------------")
    lines.append("This is a paper-trading ledger. It does not place real orders and is not a guarantee of live performance.")
    lines.append("Yahoo Finance prices can be delayed, revised, unavailable, or adjusted. Validate fills against a broker before live trading.")
    path.write_text("\n".join(lines), encoding="utf-8")


def read_last_equity_row(paper_dir: Path) -> Dict[str, object]:
    df = read_csv_if_exists(paper_dir / "paper_equity.csv")
    if df.empty:
        return {}
    return df.iloc[-1].to_dict()


def print_current_equity(args: argparse.Namespace) -> int:
    """Print current paper cash, stored positions value and total equity.

    This is intentionally read-only. It does not create state files, does not
    fetch fresh market prices and does not append audit rows. The value is used
    by Windows batch wrappers to distinguish configured initial/fallback capital
    from the current paper ledger equity.
    """
    paper_dir = Path(args.paper_dir)
    state_path = paper_dir / "paper_state.json"
    state_exists = state_path.exists() and state_path.is_file()

    if state_exists:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            cash = safe_float(state.get("cash", args.capital), args.capital)
        except Exception:
            cash = safe_float(args.capital, 0.0)
    else:
        cash = safe_float(args.capital, 0.0)

    try:
        positions = load_positions(paper_dir)
        positions_value = (
            float(pd.to_numeric(positions["market_value"], errors="coerce").fillna(0.0).sum())
            if not positions.empty and "market_value" in positions.columns
            else 0.0
        )
    except Exception:
        positions_value = 0.0

    total_equity = float(cash) + float(positions_value)

    print(f"PAPER_CASH={cash:.2f}")
    print(f"PAPER_POSITIONS_VALUE={positions_value:.2f}")
    print(f"PAPER_TOTAL_EQUITY={total_equity:.2f}")
    print(f"PAPER_STATE_EXISTS={1 if state_exists else 0}")
    return 0


def rebalance_status(paper_dir: Path, policy: CapitalAwarePolicy) -> Dict[str, object]:
    """Infer whether a rebalance is due from paper_equity.csv.

    This is deliberately simple and auditable: every persisted mark/rebalance row
    counts as one observed paper-trading day after the last rebalance.  It is not
    a broker calendar.  If the user skips days, the dashboard says so indirectly
    by showing fewer recorded mark days.
    """
    every = int(max(1, getattr(policy, "rebalance_every", 10) or 10))
    eq = read_csv_if_exists(paper_dir / "paper_equity.csv")
    if eq.empty or "mode" not in eq.columns:
        return {
            "last_rebalance_date": "-",
            "recorded_mark_days_since_rebalance": 0,
            "rebalance_every": every,
            "days_remaining": every,
            "is_due": True,
            "recommendation": "REBALANCE_DUE_NO_HISTORY",
        }
    modes = eq["mode"].astype(str).str.lower()
    rebalance_idx = list(eq.index[modes == "rebalance"])
    if not rebalance_idx:
        last_date = str(eq.iloc[-1].get("date", "-"))
        return {
            "last_rebalance_date": "-",
            "recorded_mark_days_since_rebalance": len(eq),
            "rebalance_every": every,
            "days_remaining": 0,
            "is_due": True,
            "recommendation": f"REBALANCE_DUE_NO_REBALANCE_FOUND_LAST_DATE_{last_date}",
        }
    last_i = int(rebalance_idx[-1])
    last_date = str(eq.loc[last_i].get("date", "-"))
    after = eq.loc[eq.index > last_i].copy()
    if "date" in after.columns:
        recorded_days = int(after["date"].astype(str).nunique())
    else:
        recorded_days = int(len(after))
    due = recorded_days >= every
    return {
        "last_rebalance_date": last_date,
        "recorded_mark_days_since_rebalance": recorded_days,
        "rebalance_every": every,
        "days_remaining": max(0, every - recorded_days),
        "is_due": bool(due),
        "recommendation": "REBALANCE_DUE" if due else "MARK_TO_MARKET_ONLY",
    }


def write_next_rebalance_file(paper_dir: Path, policy: CapitalAwarePolicy) -> Dict[str, object]:
    status = rebalance_status(paper_dir, policy)
    lines = [
        "Active Alpha Paper Trading - Next Rebalance",
        "===========================================",
        "",
        f"policy_profile: {policy.profile}",
        f"rebalance_every_recorded_trading_days: {status['rebalance_every']}",
        f"last_rebalance_date: {status['last_rebalance_date']}",
        f"recorded_mark_days_since_rebalance: {status['recorded_mark_days_since_rebalance']}",
        f"days_remaining_until_due: {status['days_remaining']}",
        f"is_due: {status['is_due']}",
        f"recommendation: {status['recommendation']}",
        "",
        "Operational rule",
        "----------------",
        "- Wenn recommendation = MARK_TO_MARKET_ONLY: nur run_paper_mark_to_market.bat ausfuehren.",
        "- Wenn recommendation = REBALANCE_DUE: run_paper_trading.bat ausfuehren, Reset = Nein.",
        "- Zaehler basiert auf gespeicherten Paper-Equity-Zeilen, nicht auf einem Boersenkalender.",
    ]
    path = paper_dir / "next_rebalance_due.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return status


def write_action_sheet(paper_dir: Path, orders: pd.DataFrame, *, mode: str, warnings_list: List[str]) -> Path:
    cols = [
        "sequence", "action", "ticker", "shares", "estimated_price", "estimated_gross_value",
        "unrounded_gross_value", "rounding_adjustment", "rounding_reason",
        "estimated_cost", "target_weight", "previous_shares", "previous_value", "cash_after",
        "live_trading_note",
    ]
    rows: List[Dict[str, object]] = []
    if not orders.empty:
        work = orders.copy()
        if "side" in work.columns:
            work["_priority"] = work["side"].astype(str).str.upper().map({"SELL": 1, "BUY": 2}).fillna(9)
        else:
            work["_priority"] = 9
        if "gross_value" in work.columns:
            work["_gross_abs"] = pd.to_numeric(work["gross_value"], errors="coerce").fillna(0.0).abs()
        else:
            work["_gross_abs"] = 0.0
        work.sort_values(["_priority", "_gross_abs"], ascending=[True, False], inplace=True)
        for i, r in enumerate(work.itertuples(index=False), start=1):
            side = str(getattr(r, "side", "")).upper()
            note = "SELL zuerst ausfuehren; Brokerkurs pruefen." if side == "SELL" else "BUY nach Verkaeufen ausfuehren; Brokerkurs pruefen."
            reason = str(getattr(r, "rounding_reason", ""))
            if reason in {"BROKER_MIN_REMAINING_POSITION_SELL_TO_ZERO", "BROKER_MIN_POSITION_SWEEP_SELL_TO_ZERO"}:
                note += " Restposition waere unter Broker-Minimum; vollstaendig verkaufen."
            elif bool(getattr(r, "order_value_rounded", False)):
                note += " Orderwert wurde auf volle USD gerundet."
            rows.append({
                "sequence": i,
                "action": side,
                "ticker": str(getattr(r, "ticker", "")),
                "shares": safe_float(getattr(r, "shares", 0.0)),
                "estimated_price": safe_float(getattr(r, "price", 0.0)),
                "estimated_gross_value": safe_float(getattr(r, "gross_value", 0.0)),
                "unrounded_gross_value": safe_float(getattr(r, "unrounded_gross_value", getattr(r, "gross_value", 0.0))),
                "rounding_adjustment": safe_float(getattr(r, "rounding_adjustment", 0.0)),
                "rounding_reason": str(getattr(r, "rounding_reason", "")),
                "estimated_cost": safe_float(getattr(r, "cost", 0.0)),
                "target_weight": safe_float(getattr(r, "target_weight", 0.0)),
                "previous_shares": safe_float(getattr(r, "previous_shares", 0.0)),
                "previous_value": safe_float(getattr(r, "previous_value", 0.0)),
                "cash_after": safe_float(getattr(r, "cash_after", 0.0)),
                "live_trading_note": note,
            })
    if not rows:
        rows.append({
            "sequence": 0,
            "action": "NO_ACTION",
            "ticker": "",
            "shares": 0.0,
            "estimated_price": 0.0,
            "estimated_gross_value": 0.0,
            "unrounded_gross_value": 0.0,
            "rounding_adjustment": 0.0,
            "rounding_reason": "",
            "estimated_cost": 0.0,
            "target_weight": 0.0,
            "previous_shares": 0.0,
            "previous_value": 0.0,
            "cash_after": 0.0,
            "live_trading_note": "Keine Kauf-/Verkaufsorders. Bei mode=mark nur Depotbewertung; bei mode=rebalance keine relevante Zielabweichung.",
        })
    out = pd.DataFrame(rows, columns=cols)
    path = paper_dir / "paper_action_sheet.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False)
    return path


def write_paper_dashboard(
    paper_dir: Path,
    *,
    mode: str,
    equity_row: Dict[str, object],
    policy: CapitalAwarePolicy,
    orders: pd.DataFrame,
    warnings_list: List[str],
    next_status: Dict[str, object],
) -> Path:
    total_equity = safe_float(equity_row.get("total_equity", np.nan), np.nan)
    cash = safe_float(equity_row.get("cash", np.nan), np.nan)
    positions_value = safe_float(equity_row.get("positions_value", np.nan), np.nan)
    realized_exposure = safe_float(equity_row.get("realized_exposure", 0.0), 0.0)
    target_exposure = safe_float(equity_row.get("target_exposure", 0.0), 0.0)
    n_positions = int(safe_float(equity_row.get("n_positions", 0), 0))
    missing_prices = int(safe_float(equity_row.get("missing_prices", 0), 0))
    n_orders = 0 if orders is None or orders.empty else len(orders)
    if warnings_list or missing_prices > 0:
        traffic = "ROT" if missing_prices > 0 else "GELB"
    else:
        traffic = "GRUEN"
    if mode == "rebalance":
        today_action = "REBALANCE AUSGEFUEHRT: paper_action_sheet.csv und paper_report.txt pruefen."
    elif bool(next_status.get("is_due", False)):
        today_action = "REBALANCE FAELLIG: run_paper_trading.bat ausfuehren, Reset = Nein."
    else:
        today_action = "NUR MARK-TO-MARKET: bis zur Faelligkeit keine Rebalance-Orders erzeugen."
    lines = [
        "Active Alpha Paper Trading - Dashboard",
        "======================================",
        "",
        f"status: {traffic}",
        f"today_action: {today_action}",
        f"last_mode: {mode}",
        f"last_date: {equity_row.get('date', '-')}",
        "",
        "Portfolio",
        "---------",
        f"total_equity: {total_equity:.2f}" if np.isfinite(total_equity) else "total_equity: -",
        f"cash: {cash:.2f}" if np.isfinite(cash) else "cash: -",
        f"positions_value: {positions_value:.2f}" if np.isfinite(positions_value) else "positions_value: -",
        f"realized_exposure: {realized_exposure:.2%}",
        f"target_exposure: {target_exposure:.2%}",
        f"n_positions: {n_positions}",
        "",
        "Trading",
        "-------",
        f"orders_in_last_action_sheet: {n_orders}",
        f"missing_prices: {missing_prices}",
        f"costs_last_run: {safe_float(equity_row.get('costs', 0.0)):.2f}",
        f"turnover_last_run: {safe_float(equity_row.get('turnover', 0.0)):.2%}",
        "",
        "Rebalance schedule",
        "------------------",
        f"policy_profile: {policy.profile}",
        f"rebalance_every_recorded_trading_days: {next_status.get('rebalance_every', policy.rebalance_every)}",
        f"last_rebalance_date: {next_status.get('last_rebalance_date', '-')}",
        f"recorded_mark_days_since_rebalance: {next_status.get('recorded_mark_days_since_rebalance', 0)}",
        f"days_remaining_until_due: {next_status.get('days_remaining', 0)}",
        f"recommendation: {next_status.get('recommendation', '-')}",
        "",
        "Files to inspect",
        "----------------",
        "paper_report.txt",
        "paper_action_sheet.csv",
        "paper_positions.csv",
        "paper_equity.csv",
        "next_rebalance_due.txt",
        "paper_cashflows.csv",
    ]
    if warnings_list:
        lines += ["", "Warnings", "--------"]
        lines += [f"- {w}" for w in warnings_list[:20]]
        if len(warnings_list) > 20:
            lines.append(f"- ... plus {len(warnings_list) - 20} weitere Warnungen")
    path = paper_dir / "paper_dashboard.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_cashflow_report(
    path: Path,
    *,
    rid: str,
    cashflow_type: str,
    amount: float,
    cash_before: float,
    cash_after: float,
    note: str,
    equity_row: Dict[str, object],
) -> None:
    lines = [
        "Active Alpha Paper Trading Cashflow Report",
        "==========================================",
        "",
        f"run_id: {rid}",
        "mode: cashflow",
        f"cashflow_type: {cashflow_type}",
        f"amount: {amount:.2f}",
        f"cash_before: {cash_before:.2f}",
        f"cash_after: {cash_after:.2f}",
        f"note: {note}",
        "",
        "Portfolio after cashflow",
        "------------------------",
        f"cash: {safe_float(equity_row.get('cash', cash_after)):.2f}",
        f"positions_value: {safe_float(equity_row.get('positions_value', 0.0)):.2f}",
        f"total_equity: {safe_float(equity_row.get('total_equity', 0.0)):.2f}",
        f"realized_exposure: {safe_float(equity_row.get('realized_exposure', 0.0)):.6f}",
        "",
        "Operational rule",
        "----------------",
        "Nach einer Einzahlung/Auszahlung sollte am naechsten geplanten Rebalance-Tag run_paper_trading.bat ausgefuehrt werden.",
        "Bei Auszahlungen, die Cash uebersteigen, wird die Buchung abgelehnt; keine manuellen Zwangsverkaeufe im Paper-Ledger.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def run_cashflow(args: argparse.Namespace) -> int:
    paper_dir = Path(args.paper_dir)
    paper_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id()
    if args.amount is None or not np.isfinite(float(args.amount)) or float(args.amount) <= 0:
        raise ValueError("--amount must be a positive number for cashflow mode")
    cashflow_type = str(args.cashflow_type or "deposit").lower().strip()
    if cashflow_type == "withdrawal":
        cashflow_type = "withdraw"
    if cashflow_type not in {"deposit", "withdraw"}:
        raise ValueError("--cashflow-type must be deposit or withdraw")
    state = load_state(paper_dir, args.capital, reset=False)
    cash_before = safe_float(state.get("cash", args.capital), args.capital)
    signed_amount = float(args.amount) if cashflow_type == "deposit" else -float(args.amount)
    if cashflow_type == "withdraw" and abs(signed_amount) > cash_before + 1e-8:
        raise ValueError(f"Withdrawal {abs(signed_amount):.2f} exceeds available paper cash {cash_before:.2f}. Run a rebalance instead of forcing manual sells.")
    cash_after = cash_before + signed_amount
    positions = load_positions(paper_dir)
    positions_value = float(positions["market_value"].sum()) if not positions.empty and "market_value" in positions.columns else 0.0
    total_equity = cash_after + positions_value
    if not positions.empty and total_equity > 0:
        positions = positions.copy()
        positions["weight"] = positions["market_value"] / total_equity
        save_positions(paper_dir, positions)
    if args.execute and not args.dry_run:
        state["cash"] = float(cash_after)
        state["last_run_id"] = rid
        state["last_update"] = now_stamp()
        save_state(paper_dir, state)
    flow = pd.DataFrame([{
        "run_id": rid,
        "date": now_stamp(),
        "type": cashflow_type,
        "amount": float(signed_amount),
        "currency": "USD",
        "cash_before": float(cash_before),
        "cash_after": float(cash_after),
        "note": str(args.note or ""),
        "source": "paper_trading_engine",
        "executed": bool(args.execute and not args.dry_run),
    }])
    if args.execute and not args.dry_run:
        append_csv(paper_dir / "paper_cashflows.csv", flow)
    equity_row = build_equity_row(
        rid=rid,
        mode="cashflow",
        signal_date="-",
        trade_date=pd.Timestamp.now().date().isoformat(),
        cash=cash_after,
        positions=positions,
        benchmark=args.benchmark.upper(),
        benchmark_price=np.nan,
        costs=0.0,
        fee_model="cashflow",
        turnover_value=0.0,
        target_exposure=0.0,
        missing_prices=0,
        paper_dir=paper_dir,
    )
    policy = choose_capital_aware_execution_policy(max(total_equity, 1.0), fee_model="trading212_us", policy=args.trading212_policy)
    equity_row.update(policy_as_dict(policy, mode="cashflow"))
    equity_row["cashflow_type"] = cashflow_type
    equity_row["cashflow_amount"] = float(signed_amount)
    if args.execute and not args.dry_run:
        append_csv(paper_dir / "paper_equity.csv", pd.DataFrame([equity_row]))
    next_status = write_next_rebalance_file(paper_dir, policy)
    write_action_sheet(paper_dir, pd.DataFrame(), mode="cashflow", warnings_list=[])
    write_paper_dashboard(paper_dir, mode="cashflow", equity_row=equity_row, policy=policy, orders=pd.DataFrame(), warnings_list=[], next_status=next_status)
    write_cashflow_report(
        paper_dir / "paper_report.txt",
        rid=rid,
        cashflow_type=cashflow_type,
        amount=float(signed_amount),
        cash_before=cash_before,
        cash_after=cash_after,
        note=str(args.note or ""),
        equity_row=equity_row,
    )
    print("[OK] Cashflow gebucht." if args.execute and not args.dry_run else "[WARN] Dry run: Cashflow nicht gebucht.")
    print(f"[OK] Cash vorher: {cash_before:.2f} USD")
    print(f"[OK] Cash nachher: {cash_after:.2f} USD")
    print(f"[OK] Report: {paper_dir / 'paper_report.txt'}")
    print(f"[OK] Cashflows: {paper_dir / 'paper_cashflows.csv'}")
    print(f"[OK] Dashboard: {paper_dir / 'paper_dashboard.txt'}")
    return 0


def run_status(args: argparse.Namespace) -> int:
    paper_dir = Path(args.paper_dir)
    state = load_state(paper_dir, args.capital, reset=False)
    cash = safe_float(state.get("cash", args.capital), args.capital)
    positions = load_positions(paper_dir)
    positions_value = float(positions["market_value"].sum()) if not positions.empty and "market_value" in positions.columns else 0.0
    total_equity = cash + positions_value
    equity_row = read_last_equity_row(paper_dir)
    if not equity_row:
        equity_row = {
            "run_id": "-",
            "mode": "status",
            "date": pd.Timestamp.now().date().isoformat(),
            "cash": cash,
            "positions_value": positions_value,
            "total_equity": total_equity,
            "realized_exposure": positions_value / total_equity if total_equity > 0 else 0.0,
            "target_exposure": 0.0,
            "n_positions": int((positions["shares"] > 1e-12).sum()) if not positions.empty and "shares" in positions.columns else 0,
            "costs": 0.0,
            "turnover": 0.0,
            "missing_prices": 0,
        }
    policy = choose_capital_aware_execution_policy(max(safe_float(equity_row.get("total_equity", total_equity), total_equity), 1.0), fee_model="trading212_us", policy=args.trading212_policy)
    next_status = write_next_rebalance_file(paper_dir, policy)
    orders = read_csv_if_exists(paper_dir / "paper_orders.csv")
    write_action_sheet(paper_dir, orders if not orders.empty else pd.DataFrame(), mode="status", warnings_list=[])
    dash_path = write_paper_dashboard(paper_dir, mode="status", equity_row=equity_row, policy=policy, orders=orders, warnings_list=[], next_status=next_status)
    print(f"[OK] Dashboard: {dash_path}")
    print(f"[OK] Next rebalance: {paper_dir / 'next_rebalance_due.txt'}")
    return 0


def run_engine(args: argparse.Namespace) -> int:
    target_file = Path(args.target_file)
    paper_dir = Path(args.paper_dir)
    rid = run_id()
    total_stages = 8 if args.mode == "rebalance" else 6
    st = DashboardState(
        total_stages=total_stages,
        target_file=str(target_file),
        paper_dir=str(paper_dir),
        benchmark=args.benchmark.upper(),
        trade_date=now_stamp(),
    )
    warnings_list: List[str] = []
    fee_config = fee_config_from_args(args)
    st.fee_model = fee_config.label
    policy = choose_capital_aware_execution_policy(args.capital, fee_model="trading212_us", policy=args.trading212_policy)
    policy_mode = "capital_curve" if bool(getattr(args, "capital_curve_policy", False)) else "manual"
    if bool(getattr(args, "capital_curve_policy", False)):
        args.min_trade_value = float(policy.min_trade_value)
    st.policy_mode = policy_mode
    st.capital_profile = policy.profile
    st.policy_rebalance_every = policy.rebalance_every
    st.policy_top_k = policy.top_k
    st.policy_max_position = policy.max_position
    st.policy_max_issuer = policy.max_issuer
    st.policy_risk_on_exposure_floor = policy.risk_on_exposure_floor
    st.policy_max_turnover = policy.max_turnover
    st.policy_no_trade_band = policy.no_trade_band
    st.policy_min_trade_value = float(getattr(args, "min_trade_value", policy.min_trade_value))
    st.policy_fractional_recommended = policy.fractional_shares_recommended
    st.policy_reason = policy.reason

    with Dashboard(st, plain=args.plain_progress) as dash:
        dash.update(stage=1, phase="Zielportfolio", step="Lade latest_target_portfolio.csv ...", fee_model=fee_config.label)
        target = pd.DataFrame()
        if args.mode == "rebalance":
            target, target_warnings = load_target_portfolio(target_file, args.max_gross_exposure)
            warnings_list.extend(target_warnings)
            target_model_diag = extract_model_diagnostics_from_target(target)
            signal_date = str(target["signal_date"].iloc[0]) if "signal_date" in target.columns and len(target) else "-"
            target_exposure = float(target["target_weight"].sum()) if len(target) else 0.0
            if target.empty:
                warnings_list.append("Target portfolio is empty; no rebalance orders can be generated.")
            elif target_exposure < 0.50:
                warnings_list.append(f"Target exposure is low ({target_exposure:.1%}); check beta/risk caps and latest_target_portfolio.csv.")
        else:
            target_model_diag = {}
            signal_date = "-"
            target_exposure = 0.0
        dash.update(signal_date=signal_date, target_exposure=target_exposure, tickers=len(target))

        dash.update(stage=2, phase="Paper State", step="Lade virtuelle Positionen und Cash ...")
        state = load_state(paper_dir, args.capital, reset=args.reset)
        cash = safe_float(state.get("cash", args.capital), args.capital)
        positions = load_positions(paper_dir)
        dash.update(cash=cash, n_positions=len(positions))

        dash.update(stage=3, phase="Yahoo Finance Daten", step="Bestimme benötigte Symbole ...")
        needed = set([args.benchmark.upper()])
        if args.mode == "rebalance" and not target.empty:
            needed |= set(target["ticker"].astype(str).str.upper())
        if not positions.empty:
            needed |= set(positions["ticker"].astype(str).str.upper())
        raw_prices, prices, price_dates, missing = yahoo_download_prices(
            needed,
            period_days=args.price_lookback_days,
            interval=args.price_interval,
            dashboard=dash,
        )
        warnings_list.extend([f"Missing Yahoo price: {tk}" for tk in missing])
        bench_px = prices.get(args.benchmark.upper(), np.nan)
        trade_date = max(price_dates.values()) if price_dates else now_stamp()
        dash.update(stage=4, trade_date=trade_date, prices=len(prices), missing_prices=len(missing), benchmark_price=bench_px)

        # Use last known prices as fallback for existing positions only.
        if not positions.empty:
            for r in positions.itertuples(index=False):
                tk = str(r.ticker).upper()
                if tk not in prices and safe_float(getattr(r, "last_price", 0.0)) > 0:
                    prices[tk] = safe_float(getattr(r, "last_price"))
                    warnings_list.append(f"Using previous last_price fallback for held ticker {tk}.")
        positions = mark_positions(positions, prices)
        positions_value = float(positions["market_value"].sum()) if not positions.empty else 0.0
        equity = cash + positions_value
        if not positions.empty and equity > 0:
            positions["weight"] = positions["market_value"] / equity
        dash.update(
            phase="Mark-to-Market",
            step="Bewerte bestehende virtuelle Positionen ...",
            cash=cash,
            positions_value=positions_value,
            equity=equity,
            realized_exposure=(positions_value / equity if equity > 0 else 0.0),
            n_positions=len(positions),
        )

        # Recompute the Trading-212 capital policy on actual marked equity, not only on
        # the user-entered starting capital.  This keeps paper-trading execution aligned
        # as the virtual account grows or shrinks.  Signal generation still uses the
        # batch-file capital input, so the report records the applied min-trade value.
        if bool(getattr(args, "capital_curve_policy", False)) and equity > 0:
            policy = choose_capital_aware_execution_policy(equity, fee_model="trading212_us", policy=args.trading212_policy)
            args.min_trade_value = float(policy.min_trade_value)
            st.capital_profile = policy.profile
            st.policy_rebalance_every = policy.rebalance_every
            st.policy_top_k = policy.top_k
            st.policy_max_position = policy.max_position
            st.policy_max_issuer = policy.max_issuer
            st.policy_risk_on_exposure_floor = policy.risk_on_exposure_floor
            st.policy_max_turnover = policy.max_turnover
            st.policy_no_trade_band = policy.no_trade_band
            st.policy_min_trade_value = float(args.min_trade_value)
            st.policy_fractional_recommended = policy.fractional_shares_recommended
            st.policy_reason = policy.reason
            dash.update(
                capital_profile=policy.profile,
                policy_rebalance_every=policy.rebalance_every,
                policy_top_k=policy.top_k,
                policy_max_position=policy.max_position,
                policy_max_issuer=policy.max_issuer,
                policy_risk_on_exposure_floor=policy.risk_on_exposure_floor,
                policy_max_turnover=policy.max_turnover,
                policy_no_trade_band=policy.no_trade_band,
                policy_min_trade_value=float(args.min_trade_value),
            )

        orders = pd.DataFrame()
        executed = pd.DataFrame()
        total_costs = 0.0
        total_commission = 0.0
        total_slippage = 0.0
        total_regulatory = 0.0
        total_sec_fee = 0.0
        total_finra_taf = 0.0
        total_cat_fee = 0.0
        total_clearing_fee = 0.0
        total_exchange_fee = 0.0
        total_pass_through_fee = 0.0
        total_fx_fee = 0.0
        total_market_impact = 0.0
        turnover_value = 0.0
        diag: Dict[str, float] = {}
        if args.mode == "rebalance":
            dash.update(stage=5, phase="Order-Generierung", step="Übersetze Zielgewichte in virtuelle Orders ...")
            orders, diag = generate_orders(
                target,
                positions,
                prices,
                cash,
                fee_config=fee_config,
                fractional=args.fractional,
                min_trade_value=args.min_trade_value,
                max_gross_exposure=args.max_gross_exposure,
                residual_weight_floor=args.residual_weight_floor,
                residual_sell_min_value=args.residual_sell_min_value,
                allow_residual_sell_to_zero=not args.no_residual_sell_to_zero,
                order_value_rounding=args.order_value_rounding,
                broker_min_remaining_position_value=args.broker_min_remaining_position_value,
            )
            orders.insert(0, "run_id", rid)
            orders.insert(1, "signal_date", signal_date)
            orders.insert(2, "trade_date", trade_date)
            orders.insert(3, "status", "PLANNED")
            dash.update(n_orders=len(orders), target_exposure=diag.get("target_exposure", target_exposure))

            paper_dir.mkdir(parents=True, exist_ok=True)
            orders.to_csv(paper_dir / "paper_orders.csv", index=False)
            dash.update(stage=6, last_file=str(paper_dir / "paper_orders.csv"))

            if args.execute and not args.dry_run:
                dash.update(phase="Virtuelle Ausführung", step="Buche virtuelle Fills, Verkäufe vor Käufen ...")
                new_positions, new_cash, executed, total_costs, turnover_value = apply_orders(
                    orders,
                    positions,
                    cash,
                    fee_config=fee_config,
                    fractional=args.fractional,
                )
                total_commission = float(executed["commission"].sum()) if not executed.empty and "commission" in executed.columns else 0.0
                total_slippage = float(executed["slippage"].sum()) if not executed.empty and "slippage" in executed.columns else 0.0
                total_regulatory = float(executed["regulatory_fees"].sum()) if not executed.empty and "regulatory_fees" in executed.columns else 0.0
                total_sec_fee = float(executed["sec_fee"].sum()) if not executed.empty and "sec_fee" in executed.columns else 0.0
                total_finra_taf = float(executed["finra_taf"].sum()) if not executed.empty and "finra_taf" in executed.columns else 0.0
                total_cat_fee = float(executed["cat_fee"].sum()) if not executed.empty and "cat_fee" in executed.columns else 0.0
                total_clearing_fee = float(executed["clearing_fee"].sum()) if not executed.empty and "clearing_fee" in executed.columns else 0.0
                total_exchange_fee = float(executed["exchange_fee"].sum()) if not executed.empty and "exchange_fee" in executed.columns else 0.0
                total_pass_through_fee = float(executed["pass_through_fee"].sum()) if not executed.empty and "pass_through_fee" in executed.columns else 0.0
                total_fx_fee = float(executed["fx_fee"].sum()) if not executed.empty and "fx_fee" in executed.columns else 0.0
                total_market_impact = float(executed["market_impact"].sum()) if not executed.empty and "market_impact" in executed.columns else 0.0
                if not executed.empty:
                    executed.insert(0, "run_id", rid)
                    executed.insert(1, "signal_date", signal_date)
                    executed.insert(2, "trade_date", trade_date)
                    executed.insert(3, "source", "paper_trading_engine")
                positions = mark_positions(new_positions, prices)
                cash = new_cash
                positions_value = float(positions["market_value"].sum()) if not positions.empty else 0.0
                equity = cash + positions_value
                if not positions.empty and equity > 0:
                    positions["weight"] = positions["market_value"] / equity
                dash.update(
                    n_orders=len(executed),
                    cash=cash,
                    positions_value=positions_value,
                    equity=equity,
                    realized_exposure=(positions_value / equity if equity > 0 else 0.0),
                    costs=total_costs,
                    turnover=(turnover_value / equity if equity > 0 else 0.0),
                    n_positions=len(positions),
                )
            else:
                warnings_list.append("Dry run: orders were generated but not executed into paper state.")
                dash.update(warning="Dry run: Paper State nicht verändert.")
        else:
            dash.update(stage=5, phase="Mark-to-Market", step="Keine Rebalance-Orders; nur Bewertung.")

        dash.update(stage=total_stages - 1, phase="Persistenz", step="Schreibe Paper-Trading-Dateien ...")
        paper_dir.mkdir(parents=True, exist_ok=True)
        if args.execute and not args.dry_run:
            state["cash"] = float(cash)
            state["last_run_id"] = rid
            state["last_update"] = now_stamp()
            save_state(paper_dir, state)
            save_positions(paper_dir, positions)
            if not executed.empty:
                append_csv(paper_dir / "paper_trades.csv", executed)

        equity_row = build_equity_row(
            rid=rid,
            mode=args.mode,
            signal_date=signal_date,
            trade_date=trade_date,
            cash=cash,
            positions=positions,
            benchmark=args.benchmark.upper(),
            benchmark_price=bench_px,
            costs=total_costs,
            commission=total_commission,
            slippage=total_slippage,
            regulatory_fees=total_regulatory,
            sec_fee=total_sec_fee,
            finra_taf=total_finra_taf,
            cat_fee=total_cat_fee,
            clearing_fee=total_clearing_fee,
            exchange_fee=total_exchange_fee,
            pass_through_fee=total_pass_through_fee,
            fx_fee=total_fx_fee,
            market_impact=total_market_impact,
            fee_model=fee_config.label,
            turnover_value=turnover_value,
            target_exposure=target_exposure,
            missing_prices=len(missing),
            paper_dir=paper_dir,
        )
        equity_row.update(policy_as_dict(policy, mode=policy_mode))
        if 'target_model_diag' in locals() and isinstance(target_model_diag, dict):
            equity_row.update(target_model_diag)
            try:
                pd.DataFrame([target_model_diag]).to_csv(paper_dir / "paper_model_diagnostics.csv", index=False)
            except Exception:
                pass
        equity_row["policy_applied_min_trade_value"] = float(getattr(args, "min_trade_value", 0.0))
        equity_row["residual_weight_floor"] = float(getattr(args, "residual_weight_floor", 0.0))
        equity_row["residual_sell_min_value"] = float(getattr(args, "residual_sell_min_value", 0.0))
        equity_row["order_value_rounding"] = float(getattr(args, "order_value_rounding", 0.0))
        equity_row["broker_min_remaining_position_value"] = float(getattr(args, "broker_min_remaining_position_value", 0.0))
        equity_row["orders_blocked_by_min_trade_value"] = float(diag.get("orders_blocked_by_min_trade_value", 0.0)) if isinstance(diag, dict) else 0.0
        equity_row["sell_to_zero_orders_below_min_trade"] = float(diag.get("sell_to_zero_orders_below_min_trade", 0.0)) if isinstance(diag, dict) else 0.0
        equity_row["residual_sell_to_zero_orders"] = float(diag.get("residual_sell_to_zero_orders", 0.0)) if isinstance(diag, dict) else 0.0
        equity_row["orders_rounded_to_full_dollar"] = float(diag.get("orders_rounded_to_full_dollar", 0.0)) if isinstance(diag, dict) else 0.0
        equity_row["broker_residual_sell_to_zero_orders"] = float(diag.get("broker_residual_sell_to_zero_orders", 0.0)) if isinstance(diag, dict) else 0.0
        for _k, _v in position_hygiene_metrics(positions, float(getattr(args, "residual_weight_floor", 0.005))).items():
            equity_row[_k] = float(_v)
        if args.execute and not args.dry_run:
            append_csv(paper_dir / "paper_equity.csv", pd.DataFrame([equity_row]))
        write_report(
            paper_dir / "paper_report.txt",
            rid=rid,
            mode=args.mode,
            target_file=target_file,
            signal_date=signal_date,
            trade_date=trade_date,
            cash=cash,
            positions=positions,
            orders=orders,
            executed=executed,
            equity_row=equity_row,
            missing=missing,
            warnings_list=warnings_list,
            fee_config=fee_config,
            fractional=args.fractional,
        )
        action_sheet_path = write_action_sheet(paper_dir, orders, mode=args.mode, warnings_list=warnings_list)
        next_status = write_next_rebalance_file(paper_dir, policy)
        dashboard_path = write_paper_dashboard(
            paper_dir,
            mode=args.mode,
            equity_row=equity_row,
            policy=policy,
            orders=orders,
            warnings_list=warnings_list,
            next_status=next_status,
        )
        dash.update(
            stage=total_stages,
            phase="Fertig",
            step="Paper-Trading-Lauf abgeschlossen.",
            cash=safe_float(equity_row.get("cash"), cash),
            positions_value=safe_float(equity_row.get("positions_value"), 0.0),
            equity=safe_float(equity_row.get("total_equity"), 0.0),
            realized_exposure=safe_float(equity_row.get("realized_exposure"), 0.0),
            target_exposure=target_exposure,
            costs=total_costs,
            turnover=safe_float(equity_row.get("turnover"), 0.0),
            n_positions=int(equity_row.get("n_positions", 0)),
            last_file=str(paper_dir / "paper_report.txt"),
            warning="; ".join(warnings_list[:2]) if warnings_list else "",
        )

    print("")
    print("[OK] Paper-Trading abgeschlossen.")
    print(f"[OK] Report: {paper_dir / 'paper_report.txt'}")
    print(f"[OK] Dashboard: {paper_dir / 'paper_dashboard.txt'}")
    print(f"[OK] Action Sheet: {paper_dir / 'paper_action_sheet.csv'}")
    print(f"[OK] Next Rebalance: {paper_dir / 'next_rebalance_due.txt'}")
    print(f"[OK] Orders: {paper_dir / 'paper_orders.csv'}")
    if args.execute and not args.dry_run:
        print(f"[OK] Positions: {paper_dir / 'paper_positions.csv'}")
        print(f"[OK] Equity: {paper_dir / 'paper_equity.csv'}")
    else:
        print("[WARN] Dry run: paper_state wurde nicht verändert.")
    return 0


def self_test() -> int:
    tmp = Path("/tmp/active_alpha_paper_selftest")
    if tmp.exists():
        for p in tmp.glob("*"):
            p.unlink()
    tmp.mkdir(parents=True, exist_ok=True)
    target = pd.DataFrame(
        {
            "signal_date": ["2026-01-02", "2026-01-02", "2026-01-02"],
            "ticker": ["AAA", "BBB", "CCC"],
            "target_weight": [0.40, 0.30, 0.20],
        }
    )
    target_file = tmp / "latest_target_portfolio.csv"
    target.to_csv(target_file, index=False)
    state = load_state(tmp, 100000.0, reset=True)
    positions = load_positions(tmp)
    prices = {"AAA": 100.0, "BBB": 50.0, "CCC": 25.0, "SPY": 500.0}
    loaded_target, warnings_list = load_target_portfolio(target_file, 1.0)
    orders, diag = generate_orders(
        loaded_target,
        positions,
        prices,
        cash=100000.0,
        fee_config=FeeConfig(fee_model="trading212_us"),
        fractional=False,
        min_trade_value=0.0,
        max_gross_exposure=1.0,
    )
    assert len(orders) == 3, orders
    new_positions, new_cash, executed, total_costs, turnover_value = apply_orders(
        orders,
        positions,
        100000.0,
        fee_config=FeeConfig(fee_model="trading212_us"),
        fractional=False,
    )
    equity = new_cash + float(new_positions["market_value"].sum())
    exposure = float(new_positions["market_value"].sum()) / equity
    assert equity > 0
    assert exposure <= 1.000001
    assert new_cash >= -1e-6
    assert total_costs > 0
    t212 = estimate_trade_cost(10, 100, "SELL", FeeConfig(fee_model="trading212_us", slippage_bps=2.0, trading212_fx_bps=15.0))
    assert abs(float(t212["commission"])) < 1e-12 and t212["sec_fee"] > 0 and t212["finra_taf"] > 0 and t212["fx_fee"] > 0
    # Sell-down test.
    target2 = pd.DataFrame({"ticker": ["AAA"], "target_weight": [0.10]})
    orders2, _ = generate_orders(
        target2,
        new_positions,
        prices,
        cash=new_cash,
        fee_config=FeeConfig(fee_model="trading212_us"),
        fractional=False,
        min_trade_value=0.0,
        max_gross_exposure=1.0,
    )
    assert (orders2["side"] == "SELL").any()
    # Residual sell-to-zero must bypass min_trade_value when the holding is below the configured weight floor.
    residual_positions = pd.DataFrame({
        "ticker": ["DDD"], "shares": [1.0], "avg_cost": [2.0], "last_price": [2.0], "market_value": [2.0], "weight": [0.002], "updated_at": [now_stamp()]
    })
    residual_target = pd.DataFrame({"ticker": ["AAA"], "target_weight": [0.0]})
    residual_orders, residual_diag = generate_orders(
        residual_target, residual_positions, {"DDD": 2.0, "AAA": 100.0}, cash=998.0,
        fee_config=FeeConfig(fee_model="trading212_us"), fractional=True, min_trade_value=25.0, max_gross_exposure=1.0,
        residual_weight_floor=0.005, residual_sell_min_value=0.01, allow_residual_sell_to_zero=True,
    )
    assert len(residual_orders) == 1 and bool(residual_orders["residual_sell_to_zero"].iloc[0])
    assert residual_diag["sell_to_zero_orders_below_min_trade"] == 1

    # Broker minimum residual sweep test: a stale sub-USD holding must be
    # liquidated even if target drift alone would generate no trade.
    stale_positions = pd.DataFrame([
        {"ticker": "LITE", "shares": 0.00075, "avg_cost": 900.0, "last_price": 900.0, "market_value": 0.675, "weight": 0.00675, "updated_at": now_stamp()}
    ])
    stale_target = pd.DataFrame({"ticker": ["LITE"], "target_weight": [0.00675]})
    stale_orders, stale_diag = generate_orders(
        stale_target,
        stale_positions,
        {"LITE": 900.0},
        cash=99.325,
        fee_config=FeeConfig(fee_model="trading212_us", slippage_bps=0.0, trading212_fx_bps=0.0),
        fractional=True,
        min_trade_value=1.0,
        max_gross_exposure=1.0,
        broker_min_remaining_position_value=1.0,
    )
    assert len(stale_orders) == 1 and str(stale_orders.iloc[0]["side"]) == "SELL", stale_orders
    assert bool(stale_orders.iloc[0]["broker_residual_sell_to_zero"]), stale_orders
    assert abs(float(stale_orders.iloc[0]["shares"]) - 0.00075) < 1e-12, stale_orders

    print("Self-test passed: paper trading order generation, cash handling, residual sell-to-zero and exposure accounting are valid.")
    return 0


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Active Alpha Paper Trading Engine")
    p.add_argument("--mode", choices=["rebalance", "mark", "cashflow", "status"], default="rebalance", help="rebalance applies target weights; mark updates paper equity; cashflow books deposits/withdrawals; status writes dashboard only.")
    p.add_argument("--target-file", default="model_output/latest_target_portfolio.csv", help="Path to latest_target_portfolio.csv from active_alpha_model.py")
    p.add_argument("--paper-dir", default="paper_output", help="Directory for paper state, trades, positions and reports")
    p.add_argument("--benchmark", default="SPY")
    p.add_argument("--capital", type=float, default=100000.0, help="Initial paper capital if no paper_state.json exists")
    p.add_argument("--cashflow-type", choices=["deposit", "withdraw", "withdrawal"], default="deposit", help="For --mode cashflow: deposit or withdraw paper cash")
    p.add_argument("--amount", type=float, default=0.0, help="For --mode cashflow: positive USD amount")
    p.add_argument("--note", default="", help="For --mode cashflow: audit note written to paper_cashflows.csv")
    p.add_argument("--fee-model", choices=["trading212_us"], default="trading212_us", help="Virtual fee model. Only Trading 212 US is supported.")
    p.add_argument("--slippage-bps", type=float, default=0.0, help="Additional slippage/spread buffer in basis points")
    p.add_argument("--market-impact-bps", type=float, default=0.0, help="Optional market-impact cost in bps on trade value")
    p.add_argument("--trading212-sec-fee-rate", type=float, default=0.0000278, help="Trading 212 US sell-side SEC Transaction Fee rate. Official Trading 212 help currently states $0.0000278 of sell order value / 0.00278%%.")
    p.add_argument("--trading212-finra-taf-per-share", type=float, default=0.000195, help="Trading 212 US sell-side FINRA fee per covered stock/ETF share sold.")
    p.add_argument("--trading212-fx-bps", type=float, default=15.0, help="Trading 212 FX fee in bps. Default 15 bps models the official 0.15%% FX fee when instrument currency differs from account/base currency. Use 0 only when there is no FX conversion.")
    p.add_argument("--min-trade-value", type=float, default=25.0, help="Ignore orders below this USD value")
    p.add_argument("--residual-weight-floor", type=float, default=0.005, help="Allow sell-to-zero below min-trade-value when current weight is below this floor.")
    p.add_argument("--residual-sell-min-value", type=float, default=0.01, help="Minimum USD value for residual sell-to-zero min-trade exceptions.")
    p.add_argument("--order-value-rounding", type=float, default=1.0, help="Round non-liquidating BUY/SELL order gross values to this USD increment. Default 1.0 = full-dollar order values; 0 disables.")
    p.add_argument("--broker-min-remaining-position-value", type=float, default=1.0, help="If a SELL would leave a positive residual below this USD value, sell the full remaining position.")
    p.add_argument("--no-residual-sell-to-zero", action="store_true", help="Disable residual sell-to-zero exemption below min-trade-value.")
    p.add_argument("--capital-curve-policy", action="store_true", help="Use the Trading-212 capital function; applies policy min_trade_value inside the paper engine.")
    p.add_argument("--trading212-policy", choices=["conservative", "balanced", "active", "threshold"], default="balanced", help="Trading-212 execution policy label used for paper diagnostics and min-trade value.")
    p.add_argument("--print-policy", action="store_true", help="Print capital-aware execution policy as KEY=VALUE lines and exit.")
    p.add_argument("--print-current-equity", action="store_true", help="Print current paper cash, positions value and total equity as KEY=VALUE lines and exit.")
    p.add_argument("--max-gross-exposure", type=float, default=1.0, help="Maximum target long exposure")
    p.add_argument("--price-lookback-days", type=int, default=10, help="Yahoo daily lookback window for latest adjusted close")
    p.add_argument("--price-interval", default="1d", help="Yahoo interval, usually 1d. Intraday intervals are possible but slower and may be delayed.")
    p.add_argument("--fractional", action="store_true", help="Allow fractional shares. Default uses whole shares.")
    p.add_argument("--execute", action="store_true", help="Actually update the virtual paper state. Without this, this is a dry run.")
    p.add_argument("--dry-run", action="store_true", help="Generate orders but do not update paper state")
    p.add_argument("--reset", action="store_true", help="Reset paper state in paper-dir before this run")
    p.add_argument("--plain-progress", action="store_true", help="Use simple text progress instead of Rich dashboard")
    p.add_argument("--self-test", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if getattr(args, "print_current_equity", False):
        return print_current_equity(args)
    if getattr(args, "print_policy", False):
        policy = choose_capital_aware_execution_policy(args.capital, fee_model="trading212_us", policy=args.trading212_policy)
        print(f"POLICY_PROFILE={policy.profile}")
        print(f"POLICY_REBALANCE_EVERY={policy.rebalance_every}")
        print(f"POLICY_TOP_K={policy.top_k}")
        print(f"POLICY_MAX_POSITION={policy.max_position}")
        print(f"POLICY_MAX_ISSUER={policy.max_issuer}")
        print(f"POLICY_RISK_ON_EXPOSURE_FLOOR={policy.risk_on_exposure_floor}")
        print(f"POLICY_MAX_TURNOVER={policy.max_turnover}")
        print(f"POLICY_NO_TRADE_BAND={policy.no_trade_band}")
        print(f"POLICY_MIN_TRADE_VALUE={policy.min_trade_value}")
        print(f"POLICY_COST_BUDGET={policy.max_annual_cost_budget}")
        print(f"POLICY_CONTINUOUS_REBALANCE_EVERY={policy.continuous_rebalance_every}")
        print(f"POLICY_CONTINUOUS_TOP_K={policy.continuous_top_k}")
        print(f"POLICY_CONTINUOUS_MAX_POSITION={policy.continuous_max_position}")
        print(f"POLICY_FRACTIONAL_RECOMMENDED={1 if policy.fractional_shares_recommended else 0}")
        print(f"POLICY_REASON={policy.reason}")
        return 0
    if args.self_test:
        return self_test()
    if args.mode == "status":
        try:
            return run_status(args)
        except Exception as e:
            print(f"\n[ERROR] Status-Lauf fehlgeschlagen: {e}")
            return 1
    if args.mode in {"mark", "cashflow"} and not args.execute and not args.dry_run:
        # Mark-to-market and cashflow are normally meant to persist an audit row.
        args.execute = True
    if not args.execute:
        args.dry_run = True
    try:
        if args.mode == "cashflow":
            return run_cashflow(args)
        return run_engine(args)
    except KeyboardInterrupt:
        print("\n[ERROR] Abbruch durch Nutzer.")
        return 130
    except Exception as e:
        print(f"\n[ERROR] Paper-Trading-Lauf fehlgeschlagen: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
