"""Read-only Yahoo chart API daily close — fallback reference for Stufe B."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReadOnlyYahooChartProvider:
    """Fetch last daily close via query1.finance.yahoo.com chart API."""

    def provider_name(self) -> str:
        return "READONLY_YAHOO_CHART"

    def fetch_last_close(
        self,
        symbol: str,
        *,
        timeout_s: float = 12.0,
    ) -> Optional[Dict[str, Any]]:
        sym = str(symbol or "").strip().upper()
        if not sym:
            return None
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}"
            f"?interval=1d&range=5d"
        )
        try:
            req = Request(
                url,
                headers={
                    "User-Agent": "ActiveAlpha/1.0 (price-crosscheck-readonly)",
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=max(float(timeout_s), 1.0)) as resp:
                payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        except (URLError, OSError, TimeoutError, ValueError, json.JSONDecodeError):
            return None

        try:
            result = (payload.get("chart") or {}).get("result") or []
            if not result:
                return None
            block = result[0]
            timestamps = block.get("timestamp") or []
            quotes = ((block.get("indicators") or {}).get("quote") or [{}])[0]
            closes = quotes.get("close") or []
            if not timestamps or not closes:
                return None
            close_val: Optional[float] = None
            ts_val: Optional[int] = None
            for ts, close in zip(timestamps, closes):
                if close is None:
                    continue
                try:
                    close_val = float(close)
                    ts_val = int(ts)
                except (TypeError, ValueError):
                    continue
            if close_val is None or close_val <= 0 or ts_val is None:
                return None
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
            return {
                "symbol": sym,
                "close": close_val,
                "as_of": dt.date().isoformat(),
                "fetched_at_utc": _utc_now(),
                "source": self.provider_name(),
            }
        except (TypeError, ValueError, KeyError, IndexError):
            return None
