"""Fictive daily OHLCV for offline training — swap to internet via AA_PRICE_DATA_SOURCE=internet."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from aa_config import BacktestConfig
from aa_dashboard import RunDashboard

FICTIVE_ALIASES = frozenset({"fictive", "mock", "synthetic", "simulated", "offline"})
INTERNET_ALIASES = frozenset({"internet", "live", "yfinance", "online", "real"})


def resolve_price_data_source(
    cfg: Optional[BacktestConfig] = None,
    env: Optional[Mapping[str, str]] = None,
) -> str:
    merged = dict(os.environ)
    if env:
        merged.update({str(k): str(v) for k, v in env.items()})
    raw = str(merged.get("AA_PRICE_DATA_SOURCE", "internet") or "internet").strip().lower()
    if raw in FICTIVE_ALIASES:
        return "fictive"
    if raw in INTERNET_ALIASES:
        return "internet"
    if raw in {"auto", "dynamic", "adaptive"}:
        from aa_adaptive_runtime import probe_internet_prices

        return "internet" if probe_internet_prices() else "fictive"
    return raw


def is_fictive_price_source(
    cfg: Optional[BacktestConfig] = None,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    return resolve_price_data_source(cfg, env) == "fictive"


def _ticker_seed(ticker: str, global_seed: int) -> int:
    digest = hashlib.sha256(f"{global_seed}|{ticker.upper()}".encode("utf-8")).hexdigest()
    return int(digest[:8], 16)


def _last_market_date(today: Optional[date] = None) -> date:
    from aa_data_freshness import last_expected_market_date

    return last_expected_market_date(today=today)


def generate_fictive_ohlcv(
    ticker: str,
    start: str,
    *,
    end: Optional[date] = None,
    global_seed: int = 42,
    benchmark_returns: Optional[pd.Series] = None,
) -> pd.DataFrame:
    """Generate reproducible daily OHLCV through the latest US market session."""
    end_dt = end or _last_market_date()
    dates = pd.bdate_range(start=start, end=end_dt)
    if len(dates) < 260:
        raise ValueError(f"Not enough business days for {ticker}: {len(dates)}")

    seed = _ticker_seed(ticker, global_seed)
    rng = np.random.default_rng(seed)
    n = len(dates)

    base = 20.0 + (seed % 5000) / 10.0
    idio_vol = 0.008 + (seed % 97) / 4000.0
    beta = 0.6 + (seed % 80) / 100.0
    drift = 0.00015 + (seed % 37) / 100000.0

    if benchmark_returns is not None and len(benchmark_returns) >= n:
        mkt = benchmark_returns.reindex(dates).fillna(0.0).to_numpy()
    else:
        mkt = rng.normal(0.0002, 0.010, n)

    idio = rng.normal(drift, idio_vol, n)
    daily_ret = beta * mkt + idio
    close = base * np.cumprod(1.0 + daily_ret)

    intraday = rng.uniform(0.001, 0.015, n)
    open_ = close * (1.0 - intraday * rng.uniform(0.2, 0.8, n))
    high = np.maximum(open_, close) * (1.0 + intraday)
    low = np.minimum(open_, close) * (1.0 - intraday)
    volume = rng.integers(500_000, 8_000_000, n).astype(float)

    return pd.DataFrame(
        {"Open": open_, "High": high, "Low": low, "Close": close, "Volume": volume},
        index=pd.DatetimeIndex(dates),
    )


def _resolve_out_dir(env: Mapping[str, str]) -> Path:
    rel = str(env.get("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212") or "model_output_sp500_pit_t212")
    path = Path(rel)
    return path if path.is_absolute() else Path.cwd() / path


def _read_panel_close(out_dir: Path, ticker: str) -> Optional[float]:
    panel_path = out_dir / "price_cache" / "ohlcv_panel.parquet"
    if not panel_path.is_file():
        return None
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
        sub = panel[panel["ticker"].astype(str).str.upper() == ticker.upper()]
        if sub.empty:
            return None
        sub = sub.sort_values("date")
        val = pd.to_numeric(sub["Close"].iloc[-1], errors="coerce")
        return float(val) if pd.notna(val) else None
    except Exception:
        return None


def fetch_fictive_last_prices_usd(
    tickers: List[str],
    *,
    env: Optional[Mapping[str, str]] = None,
) -> Dict[str, float]:
    env = dict(os.environ if env is None else env)
    out_dir = _resolve_out_dir(env)
    out: Dict[str, float] = {}
    for tk in tickers:
        if not tk or str(tk).upper() in {"CASH", "BARGELD"}:
            continue
        px = _read_panel_close(out_dir, str(tk))
        if px is not None and px > 0:
            out[str(tk).upper()] = px
    return out


def download_fictive_data(
    tickers: List[str],
    start: str,
    dashboard: Optional[RunDashboard] = None,
    *,
    cfg: Optional[BacktestConfig] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, pd.DataFrame]:
    """Build fictive OHLCV panel through today and persist to price cache."""
    from aa_features import (
        _load_price_cache,
        _save_price_cache,
        resolve_price_cache_dir,
    )

    cache_dir = resolve_price_cache_dir(cfg) if cfg is not None else Path(out_dir or "model_output") / "price_cache"
    ttl_hours = int(getattr(cfg, "price_cache_ttl_hours", 24) or 24) if cfg is not None else 24
    global_seed = int(getattr(cfg, "random_seed", 42) or 42) if cfg is not None else int(
        os.environ.get("AA_RANDOM_SEED", "42") or 42
    )
    benchmark = str(getattr(cfg, "benchmark", "SPY") if cfg is not None else os.environ.get("AA_BENCHMARK", "SPY"))

    if cfg is not None and bool(getattr(cfg, "skip_download_if_cached", False)):
        cached = _load_price_cache(cache_dir, tickers, start, ttl_hours)
        if cached is not None:
            meta_path = cache_dir / "price_cache_meta.json"
            if meta_path.is_file():
                try:
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    if str(meta.get("data_source", "")).lower() == "fictive":
                        if dashboard is not None:
                            dashboard.ok(f"Fiktiver Preis-Cache geladen: {len(cached)} Ticker")
                        else:
                            print(f"Loaded fictive price cache: {len(cached)} tickers")
                        return cached
                except Exception:
                    pass

    end = _last_market_date()
    if dashboard is not None:
        dashboard.start_phase(
            "Fiktive Tagesdaten",
            total=1,
            step=f"{len(tickers)} Ticker simuliert bis {end.isoformat()}",
        )
    else:
        print(f"Generating fictive daily data for {len(tickers)} tickers through {end} …")

    bench_df = generate_fictive_ohlcv(benchmark, start, end=end, global_seed=global_seed)
    bench_ret = bench_df["Close"].pct_change().fillna(0.0)

    data: Dict[str, pd.DataFrame] = {}
    for tk in tickers:
        if tk == benchmark:
            data[tk] = bench_df
            continue
        df = generate_fictive_ohlcv(
            tk,
            start,
            end=end,
            global_seed=global_seed,
            benchmark_returns=bench_ret,
        )
        if df["Close"].notna().sum() > 250:
            data[tk] = df

    missing = [tk for tk in tickers if tk not in data]
    if missing:
        msg = f"fictive data missing for {len(missing)} tickers: {missing[:8]}"
        if dashboard is not None:
            dashboard.warn(msg)
        else:
            print(f"Warning: {msg}")

    if cfg is not None and bool(getattr(cfg, "write_price_cache", True)):
        _save_price_cache(cache_dir, tickers, start, data)
        meta_path = cache_dir / "price_cache_meta.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["data_source"] = "fictive"
                meta["fictive_through"] = end.isoformat()
                meta["fictive_seed"] = global_seed
                meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
            except Exception:
                pass
        if dashboard is not None:
            dashboard.ok(f"Fiktiver Preis-Cache gespeichert: {cache_dir}")
        else:
            print(f"Fictive price cache saved: {cache_dir}")

    if dashboard is not None:
        dashboard.advance_phase(1, step=f"{len(data)} fiktive Reihen erzeugt")
        dashboard.finish_phase()
    return data


def seed_fictive_daily_cache(
    root: Path,
    env: Mapping[str, str],
    tickers: List[str],
    *,
    start: Optional[str] = None,
    force: bool = False,
) -> Dict[str, object]:
    """Explicit helper for live sync / training prep with fictive tagesaktuelle bars."""
    from aa_config import BacktestConfig, parse_args
    from aa_config_env import build_backtest_argv
    import sys

    root = Path(root)
    old = dict(os.environ)
    old_argv = sys.argv
    try:
        os.environ.update(dict(env))
        if force:
            os.environ["AA_SKIP_DOWNLOAD_IF_CACHED"] = "0"
        sys.argv = build_backtest_argv(dict(env))
        cfg = BacktestConfig.from_args(parse_args())
        out_rel = str(env.get("AA_BACKTEST_OUT_DIR", "") or "").strip()
        if out_rel:
            cfg.out_dir = out_rel
        cfg.skip_download_if_cached = not force
        cfg.write_price_cache = True
        start_date = start or str(cfg.start)
        data = download_fictive_data(
            list(tickers),
            start_date,
            cfg=cfg,
            out_dir=root / str(env.get("AA_BACKTEST_OUT_DIR", "model_output_sp500_pit_t212")),
        )
        latest = _last_market_date().isoformat()
        return {
            "ok": bool(data),
            "tickers_loaded": len(data),
            "price_latest": latest,
            "data_source": "fictive",
        }
    finally:
        os.environ.clear()
        os.environ.update(old)
        sys.argv = old_argv
