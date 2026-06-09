"""Intraday market data provider abstraction (P5 — replay only by default)."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Union

import pandas as pd

BarFrame = pd.DataFrame
QuoteFrame = pd.DataFrame


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class MarketDataProvider(ABC):
    """Provider-neutral market data interface."""

    @abstractmethod
    def provider_name(self) -> str:
        ...

    @abstractmethod
    def get_historical_bars(
        self,
        ticker: str,
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        interval: str = "5m",
        session: str = "RTH",
    ) -> BarFrame:
        ...

    @abstractmethod
    def get_latest_quotes(self, tickers: Sequence[str]) -> QuoteFrame:
        ...

    @abstractmethod
    def stream_bars(
        self,
        tickers: Sequence[str],
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        interval: str = "5m",
    ) -> Iterator[BarFrame]:
        ...

    @abstractmethod
    def get_market_calendar(self, *, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
        ...


def default_replay_root(root: Path) -> Path:
    return Path(root) / "market_data" / "replay"


def _normalize_bars(frame: pd.DataFrame, *, ticker: str) -> BarFrame:
    if frame.empty:
        return frame
    out = frame.copy()
    if "timestamp" in out.columns:
        out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="coerce")
        out = out.set_index("timestamp")
    elif not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    else:
        out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = out.sort_index()
    out["ticker"] = ticker
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "session" not in out.columns:
        out["session"] = "RTH"
    return out


class ReplayMarketDataProvider(MarketDataProvider):
    """Local deterministic replay from CSV/Parquet under market_data/replay/."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.bars_dir = self.root / "bars_5m"
        self.quotes_dir = self.root / "quotes"

    def provider_name(self) -> str:
        return "REPLAY"

    def _bars_path(self, ticker: str) -> Path:
        for ext in (".csv", ".parquet"):
            path = self.bars_dir / f"{ticker.upper()}{ext}"
            if path.is_file():
                return path
        return self.bars_dir / f"{ticker.upper()}.csv"

    def _load_bars(self, ticker: str) -> BarFrame:
        path = self._bars_path(ticker)
        if not path.is_file():
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "session", "ticker"])
        if path.suffix.lower() == ".parquet":
            raw = pd.read_parquet(path)
        else:
            raw = pd.read_csv(path)
        return _normalize_bars(raw, ticker=ticker.upper())

    def get_historical_bars(
        self,
        ticker: str,
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        interval: str = "5m",
        session: str = "RTH",
    ) -> BarFrame:
        _ = interval  # v1 fixed at 5m source files
        bars = self._load_bars(ticker)
        if bars.empty:
            return bars
        if session:
            bars = bars[bars["session"].astype(str).str.upper() == session.upper()]
        if start is not None:
            bars = bars[bars.index >= pd.Timestamp(start, tz="UTC")]
        if end is not None:
            bars = bars[bars.index <= pd.Timestamp(end, tz="UTC")]
        return bars

    def get_latest_quotes(self, tickers: Sequence[str]) -> QuoteFrame:
        rows: List[Dict[str, Any]] = []
        for ticker in tickers:
            path = self.quotes_dir / f"{ticker.upper()}.csv"
            if not path.is_file():
                continue
            raw = pd.read_csv(path)
            if raw.empty:
                continue
            raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
            rec = raw.sort_values("timestamp").iloc[-1].to_dict()
            rec["ticker"] = ticker.upper()
            rows.append(rec)
        if not rows:
            return pd.DataFrame(columns=["ticker", "timestamp", "bid", "ask", "last"])
        return pd.DataFrame(rows)

    def stream_bars(
        self,
        tickers: Sequence[str],
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
        interval: str = "5m",
    ) -> Iterator[BarFrame]:
        for ticker in tickers:
            yield self.get_historical_bars(ticker, start=start, end=end, interval=interval)

    def get_market_calendar(self, *, start: pd.Timestamp, end: pd.Timestamp) -> pd.DatetimeIndex:
        idx = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), freq="B", tz="UTC")
        return idx


def ensure_sample_replay_data(root: Path) -> Path:
    """Create minimal deterministic replay fixtures if missing (no external API)."""
    replay = default_replay_root(root)
    bars_dir = replay / "bars_5m"
    quotes_dir = replay / "quotes"
    bars_dir.mkdir(parents=True, exist_ok=True)
    quotes_dir.mkdir(parents=True, exist_ok=True)
    meta_path = replay / "replay_manifest.json"
    if meta_path.is_file():
        return replay

    idx = pd.date_range("2020-01-02 14:30:00", periods=6, freq="5min", tz="UTC")
    base = pd.DataFrame(
        {
            "timestamp": idx,
            "open": [100.0, 100.1, 100.2, 100.15, 100.25, 100.3],
            "high": [100.2, 100.3, 100.35, 100.3, 100.4, 100.45],
            "low": [99.9, 100.0, 100.1, 100.05, 100.15, 100.2],
            "close": [100.1, 100.2, 100.15, 100.25, 100.3, 100.35],
            "volume": [1000, 1100, 900, 950, 1050, 980],
            "session": ["RTH"] * 6,
        }
    )
    for ticker in ("SPY", "AAPL"):
        base.assign(ticker=ticker).drop(columns=["ticker"]).to_csv(bars_dir / f"{ticker}.csv", index=False)
    quote_ts = idx[-1]
    pd.DataFrame(
        [
            {"timestamp": quote_ts, "bid": 100.34, "ask": 100.36, "last": 100.35},
        ]
    ).to_csv(quotes_dir / "SPY.csv", index=False)
    pd.DataFrame(
        [
            {"timestamp": quote_ts, "bid": 150.0, "ask": 150.02, "last": 150.01},
        ]
    ).to_csv(quotes_dir / "AAPL.csv", index=False)
    meta_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "interval": "5m",
                "tickers": ["SPY", "AAPL"],
                "created_at_utc": _utc_now(),
                "source": "local_replay_fixture",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return replay
