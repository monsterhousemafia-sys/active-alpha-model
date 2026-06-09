"""Verified benchmark daily returns for backtest reporting and alpha evaluation."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


def _annual_returns(series: pd.Series) -> pd.Series:
    if series.empty:
        return pd.Series(dtype=float)
    s = series.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    idx = pd.DatetimeIndex(s.index)
    grouped = (1.0 + s).groupby(idx.year).prod() - 1.0
    return grouped.astype(float)


def _series_from_price_panel(out_dir: Path, ticker: str) -> pd.Series:
    panel_path = Path(out_dir) / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return pd.Series(dtype=float)
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        try:
            panel = pd.read_parquet(panel_path)
        except Exception:
            return pd.Series(dtype=float)
    if panel.empty:
        return pd.Series(dtype=float)
    tk = str(ticker or "SPY").upper().strip()
    sub = panel[panel["ticker"].astype(str).str.upper() == tk].copy()
    if sub.empty:
        return pd.Series(dtype=float)
    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub = sub.dropna(subset=["date"]).sort_values("date")
    close = pd.to_numeric(sub["Close"], errors="coerce")
    close.index = pd.DatetimeIndex(sub["date"])
    close = close[~close.index.duplicated(keep="last")].dropna()
    rets = close.pct_change().dropna()
    rets.name = "benchmark_return"
    return rets.astype(float)


def _series_from_returns_matrix(returns: pd.DataFrame, ticker: str) -> pd.Series:
    tk = str(ticker or "SPY").upper().strip()
    if tk not in returns.columns:
        return pd.Series(dtype=float)
    s = pd.to_numeric(returns[tk], errors="coerce").dropna()
    s.name = "benchmark_return"
    return s.astype(float)


def fetch_yfinance_benchmark_total_return(
    start: str = "2012-01-01",
    ticker: str = "SPY",
) -> pd.Series:
    """Independent SPY total-return proxy (yfinance auto_adjust=True Close pct_change)."""
    import yfinance as yf

    raw = yf.download(ticker, start=start, auto_adjust=True, progress=False)
    if raw.empty:
        return pd.Series(dtype=float)
    close = raw["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    close.index = pd.to_datetime(close.index)
    rets = close.pct_change().dropna()
    rets.name = "benchmark_return"
    return rets.astype(float)


def _benchmark_mismatch_vs_reference(candidate: pd.Series, reference: pd.Series) -> Tuple[bool, float]:
    if candidate.empty or reference.empty:
        return True, float("nan")
    common = candidate.index.intersection(reference.index)
    if len(common) < 252:
        return True, float("nan")
    cand_ann = _annual_returns(candidate.reindex(common))
    ref_ann = _annual_returns(reference.reindex(common))
    years = cand_ann.index.intersection(ref_ann.index)
    if len(years) == 0:
        return True, float("nan")
    diffs = (cand_ann.reindex(years) - ref_ann.reindex(years)).abs()
    max_diff_pp = float(diffs.max() * 100.0) if not diffs.empty else float("nan")
    corr = float(candidate.reindex(common).corr(reference.reindex(common)))
    mismatch = (max_diff_pp > 5.0) or (corr < 0.95)
    return mismatch, max_diff_pp


def load_verified_benchmark_returns(
    *,
    out_dir: Path,
    returns: pd.DataFrame,
    benchmark: str,
    strategy_index: pd.Index,
    start: str = "2012-01-01",
) -> tuple[pd.Series, str, bool]:
    """Return (aligned_benchmark_returns, source_label, verified_ok)."""
    out_dir = Path(out_dir)
    bench_tk = str(benchmark or "SPY").upper().strip()
    panel = _series_from_price_panel(out_dir, bench_tk)
    matrix = _series_from_returns_matrix(returns, bench_tk)
    reference = fetch_yfinance_benchmark_total_return(start=start, ticker=bench_tk)

    chosen = matrix
    source = "returns_matrix"
    verified_ok = False

    for candidate, label in ((panel, "price_panel"), (matrix, "returns_matrix")):
        if candidate.empty:
            continue
        mismatch, _ = _benchmark_mismatch_vs_reference(candidate, reference)
        if not mismatch:
            chosen = candidate
            source = label
            verified_ok = True
            break

    if not verified_ok and not reference.empty:
        chosen = reference
        source = "yfinance_total_return_verified"
        verified_ok = True

    if chosen.empty:
        empty = pd.Series(0.0, index=strategy_index, name="benchmark_return")
        return empty, "missing", False

    aligned = chosen.reindex(strategy_index).fillna(0.0)
    aligned.name = "benchmark_return"
    return aligned, source, verified_ok


def benchmark_reference_fingerprint(start: str = "2012-01-01", ticker: str = "SPY") -> str:
    ref = fetch_yfinance_benchmark_total_return(start=start, ticker=ticker)
    if ref.empty:
        return ""
    payload = ref.sort_index().to_csv().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
