"""Read-only yfinance quote provider for P16d forward batch / live quotes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReadOnlyYFinanceProvider:
    """Fetch last/bid quotes via yfinance — no broker connectivity."""

    def provider_name(self) -> str:
        return "READONLY_YFINANCE"

    def fetch_quotes(self, tickers: List[str]) -> pd.DataFrame:
        rows: List[Dict[str, Any]] = []
        now = _utc_now()
        for raw in tickers:
            sym = str(raw or "").strip().upper()
            if not sym:
                continue
            price, bid, ts = self._last_price(sym)
            if price is None and bid is None:
                continue
            rows.append(
                {
                    "ticker": sym,
                    "last": price,
                    "bid": bid,
                    "timestamp": ts or now,
                    "market_event_time_utc": ts or now,
                }
            )
        return pd.DataFrame(rows)

    def _history_close(self, ticker: Any) -> Tuple[float | None, str | None]:
        try:
            hist = ticker.history(period="5d", interval="1d")
            if hist.empty:
                return None, None
            valid = hist.dropna(subset=["Close"])
            if valid.empty:
                return None, None
            close = float(valid.iloc[-1]["Close"])
            idx = valid.index[-1]
            ts: Optional[str] = None
            if hasattr(idx, "to_pydatetime"):
                dt = idx.to_pydatetime()
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.replace(microsecond=0).isoformat()
            return close, ts
        except Exception:
            return None, None

    def _fast_last(self, ticker: Any) -> Tuple[float | None, str | None]:
        try:
            fi = getattr(ticker, "fast_info", None)
            if fi is None:
                return None, None
            for key in ("regularMarketPrice", "last_price", "lastPrice"):
                val = fi.get(key) if hasattr(fi, "get") else getattr(fi, key, None)
                if val is not None:
                    return float(val), _utc_now()
        except Exception:
            pass
        return None, None

    def _last_price(self, symbol: str) -> tuple[float | None, float | None, str | None]:
        try:
            import yfinance as yf
        except ImportError:
            return None, None, None

        ticker = yf.Ticker(symbol)
        fast_last, fast_ts = self._fast_last(ticker)
        hist_close, hist_ts = self._history_close(ticker)

        last: float | None = fast_last
        ts: str | None = fast_ts

        if last is not None and hist_close is not None and hist_close > 0:
            ratio = last / hist_close
            if ratio > 1.5 or ratio < 0.67:
                last = hist_close
                ts = hist_ts
        elif last is None and hist_close is not None:
            last = hist_close
            ts = hist_ts

        if last is not None and last > 0:
            return last, None, ts
        return None, None, None
