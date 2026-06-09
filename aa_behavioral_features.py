"""P6 behavioral intraday features — research-only, no champion impact."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

FEATURE_GROUPS: Dict[str, List[str]] = {
    "attention": ["relative_volume", "volume_shock"],
    "continuation": ["close_vs_vwap", "relative_intraday_return_vs_spy"],
    "liquidity_stress": ["spread_bps", "intraday_realized_volatility"],
}
OPTIONAL_FEATURES = ["high_to_close_reversal"]
ALL_FEATURE_NAMES = [name for group in FEATURE_GROUPS.values() for name in group] + OPTIONAL_FEATURES

# US RTH close marker (UTC) for session-complete checks on full-day feeds.
SESSION_CLOSE_UTC = pd.Timestamp("21:00:00").time()


@dataclass
class FeatureFinalizeResult:
    status: str  # FINALIZED | SESSION_INCOMPLETE | QUALITY_BLOCKED
    session_date: str
    features: Dict[str, float] = field(default_factory=dict)
    signal_available_date: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _session_key(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%d")


def _bars_through(bars: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    if bars is None or bars.empty:
        return pd.DataFrame()
    as_of = pd.Timestamp(as_of).tz_convert("UTC")
    idx = pd.to_datetime(bars.index, utc=True)
    return bars.loc[idx <= as_of].copy()


def _vwap(frame: pd.DataFrame) -> float:
    if frame.empty:
        return float("nan")
    vol = pd.to_numeric(frame.get("volume"), errors="coerce").fillna(0.0)
    if vol.sum() <= 0:
        return float("nan")
    tp = (
        pd.to_numeric(frame.get("high"), errors="coerce")
        + pd.to_numeric(frame.get("low"), errors="coerce")
        + pd.to_numeric(frame.get("close"), errors="coerce")
    ) / 3.0
    return float((tp * vol).sum() / vol.sum())


def _intraday_return(frame: pd.DataFrame) -> float:
    if frame.empty:
        return float("nan")
    open_px = float(pd.to_numeric(frame["open"].iloc[0], errors="coerce"))
    close_px = float(pd.to_numeric(frame["close"].iloc[-1], errors="coerce"))
    if open_px <= 0:
        return float("nan")
    return close_px / open_px - 1.0


def is_session_complete(bars: pd.DataFrame, session_date: str) -> bool:
    """True when RTH session for session_date appears closed (no lookahead)."""
    if bars is None or bars.empty:
        return False
    idx = pd.to_datetime(bars.index, utc=True)
    day = bars.loc[idx.normalize() == pd.Timestamp(session_date, tz="UTC")]
    if day.empty:
        return False
    last_ts = pd.Timestamp(day.index.max()).tz_convert("UTC")
    # Fixture sessions (short replay days) complete when all bars share one calendar day
    # and the last bar is the dataset max for that day.
    day_max = pd.Timestamp(idx[idx.normalize() == pd.Timestamp(session_date, tz="UTC")].max()).tz_convert("UTC")
    if last_ts == day_max and last_ts.time() >= pd.Timestamp("14:55:00").time():
        return True
    return last_ts.time() >= SESSION_CLOSE_UTC


def next_trading_day(session_date: str) -> str:
    start = pd.Timestamp(session_date, tz="UTC")
    nxt = start + pd.tseries.offsets.BDay(1)
    return nxt.strftime("%Y-%m-%d")


def latest_quote_at(quotes: pd.DataFrame, as_of: pd.Timestamp) -> Dict[str, float]:
    if quotes is None or quotes.empty:
        return {}
    frame = quotes.copy()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="coerce")
        frame = frame.sort_values("timestamp")
        frame = frame[frame["timestamp"] <= pd.Timestamp(as_of).tz_convert("UTC")]
        if frame.empty:
            return {}
        row = frame.iloc[-1]
    else:
        row = frame.iloc[-1]
    return {
        "bid": float(pd.to_numeric(row.get("bid"), errors="coerce")),
        "ask": float(pd.to_numeric(row.get("ask"), errors="coerce")),
        "last": float(pd.to_numeric(row.get("last"), errors="coerce")),
    }


def compute_point_features(
    bars: pd.DataFrame,
    spy_bars: pd.DataFrame,
    *,
    as_of: pd.Timestamp,
    quote: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Compute features using only data available at or before as_of (no lookahead)."""
    visible = _bars_through(bars, as_of)
    spy_visible = _bars_through(spy_bars, as_of)
    out: Dict[str, float] = {}
    if visible.empty:
        return out

    vol = pd.to_numeric(visible.get("volume"), errors="coerce").fillna(0.0)
    cum_vol = float(vol.sum())
    mean_vol = float(vol.mean()) if len(vol) else float("nan")
    out["relative_volume"] = cum_vol / mean_vol if mean_vol and mean_vol > 0 else float("nan")
    if len(vol) >= 2 and vol.std(ddof=0) > 0:
        out["volume_shock"] = float((vol.iloc[-1] - vol.mean()) / vol.std(ddof=0))
    else:
        out["volume_shock"] = 0.0

    vwap = _vwap(visible)
    close_px = float(pd.to_numeric(visible["close"].iloc[-1], errors="coerce"))
    out["close_vs_vwap"] = close_px / vwap - 1.0 if vwap and vwap > 0 else float("nan")

    ticker_ret = _intraday_return(visible)
    spy_ret = _intraday_return(spy_visible) if not spy_visible.empty else float("nan")
    out["relative_intraday_return_vs_spy"] = (
        ticker_ret - spy_ret if ticker_ret == ticker_ret and spy_ret == spy_ret else float("nan")
    )

    rets = pd.to_numeric(visible["close"], errors="coerce").pct_change().dropna()
    out["intraday_realized_volatility"] = float(rets.std(ddof=0) * np.sqrt(len(rets))) if len(rets) else float("nan")

    q = quote or {}
    bid = q.get("bid", float("nan"))
    ask = q.get("ask", float("nan"))
    if bid == bid and ask == ask and bid > 0 and ask >= bid:
        mid = (bid + ask) / 2.0
        out["spread_bps"] = (ask - bid) / mid * 10000.0 if mid > 0 else float("nan")
    else:
        out["spread_bps"] = float("nan")

    high = float(pd.to_numeric(visible["high"], errors="coerce").max())
    low = float(pd.to_numeric(visible["low"], errors="coerce").min())
    if high > low:
        out["high_to_close_reversal"] = (high - close_px) / (high - low)
    else:
        out["high_to_close_reversal"] = float("nan")
    return out


def finalize_session_features(
    bars: pd.DataFrame,
    spy_bars: pd.DataFrame,
    *,
    session_date: str,
    quote: Optional[Dict[str, float]] = None,
) -> FeatureFinalizeResult:
    """Finalize EOD features only after session close; signal earliest next trading day."""
    if not is_session_complete(bars, session_date):
        return FeatureFinalizeResult(
            status="SESSION_INCOMPLETE",
            session_date=session_date,
            errors=["session not complete — features not finalized"],
        )
    idx = pd.to_datetime(bars.index, utc=True)
    day = bars.loc[idx.normalize() == pd.Timestamp(session_date, tz="UTC")]
    as_of = pd.Timestamp(day.index.max()).tz_convert("UTC")
    features = compute_point_features(bars, spy_bars, as_of=as_of, quote=quote)
    return FeatureFinalizeResult(
        status="FINALIZED",
        session_date=session_date,
        features=features,
        signal_available_date=next_trading_day(session_date),
    )


def build_feature_table(
    provider,
    tickers: Sequence[str],
    *,
    session_date: Optional[str] = None,
) -> Tuple[pd.DataFrame, List[str]]:
    """Deterministic feature rows for all tickers on one session date."""
    tickers = [str(t).upper() for t in tickers]
    if "SPY" not in tickers:
        tickers = ["SPY", *tickers]
    spy_bars = provider.get_historical_bars("SPY")
    if spy_bars.empty:
        return pd.DataFrame(), ["missing SPY bar data"]
    if session_date is None:
        session_date = _session_key(pd.Timestamp(spy_bars.index.max()))
    errors: List[str] = []
    rows: List[Dict[str, Any]] = []
    for ticker in tickers:
        if ticker == "SPY":
            bars = spy_bars
        else:
            bars = provider.get_historical_bars(ticker)
        if bars.empty:
            errors.append(f"{ticker}: empty bar series")
            continue
        quotes_path = getattr(provider, "quotes_dir", None)
        quote: Dict[str, float] = {}
        if quotes_path is not None:
            qfile = quotes_path / f"{ticker}.csv"
            if qfile.is_file():
                raw = pd.read_csv(qfile)
                quote = latest_quote_at(raw, pd.Timestamp(bars.index.max()))
        final = finalize_session_features(bars, spy_bars, session_date=session_date, quote=quote)
        if final.status != "FINALIZED":
            errors.append(f"{ticker}: {final.status}")
            continue
        row: Dict[str, Any] = {
            "ticker": ticker,
            "session_date": session_date,
            "signal_available_date": final.signal_available_date,
            "computed_at_utc": _utc_now(),
        }
        row.update(final.features)
        rows.append(row)
    if not rows:
        return pd.DataFrame(), errors
    return pd.DataFrame(rows), errors


def select_feature_groups(groups: Sequence[str]) -> List[str]:
    names: List[str] = []
    for group in groups:
        names.extend(FEATURE_GROUPS.get(str(group), []))
    return names
