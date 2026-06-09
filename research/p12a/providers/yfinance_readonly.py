"""Read-only yfinance quote provider for P16d forward batch / live quotes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

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

    def _last_price(self, symbol: str) -> tuple[float | None, float | None, str | None]:
        try:
            import yfinance as yf
        except ImportError:
            return None, None, None

        ticker = yf.Ticker(symbol)
        last: float | None = None
        bid: float | None = None
        ts: str | None = None

        try:
            fi = getattr(ticker, "fast_info", None)
            if fi is not None:
                for key in ("last_price", "regularMarketPrice", "lastPrice"):
                    val = fi.get(key) if hasattr(fi, "get") else getattr(fi, key, None)
                    if val is not None:
                        try:
                            last = float(val)
                            break
                        except (TypeError, ValueError):
                            pass
        except Exception:
            pass

        if last is None:
            try:
                hist = ticker.history(period="5d", interval="1d")
                if not hist.empty:
                    last = float(hist.iloc[-1]["Close"])
                    idx = hist.index[-1]
                    if hasattr(idx, "to_pydatetime"):
                        dt = idx.to_pydatetime()
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        ts = dt.replace(microsecond=0).isoformat()
            except Exception:
                pass

        if last is not None and last > 0:
            return last, bid, ts
        return None, None, None
