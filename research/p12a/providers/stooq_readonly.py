"""Read-only Stooq daily close provider — second source for Stufe B cross-check."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stooq_us_symbol(us_ticker: str) -> str:
    """Map US equity ticker to Stooq symbol (e.g. SPY -> spy.us)."""
    sym = str(us_ticker or "").strip().lower()
    if not sym:
        return ""
    if sym.endswith(".us"):
        return sym
    return f"{sym}.us"


class ReadOnlyStooqProvider:
    """Fetch last daily close from Stooq CSV endpoint — no API key."""

    def provider_name(self) -> str:
        return "READONLY_STOOQ"

    def fetch_last_close(
        self,
        symbol: str,
        *,
        timeout_s: float = 12.0,
    ) -> Optional[Dict[str, Any]]:
        stooq_sym = stooq_us_symbol(symbol)
        if not stooq_sym:
            return None
        url = f"https://stooq.com/q/d/l/?s={stooq_sym}&i=d"
        try:
            req = Request(url, headers={"User-Agent": "ActiveAlpha/1.0 (price-crosscheck-readonly)"})
            with urlopen(req, timeout=max(float(timeout_s), 1.0)) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except (URLError, OSError, TimeoutError, ValueError):
            return None

        if not raw.strip():
            return None
        try:
            reader = csv.DictReader(io.StringIO(raw))
            rows = [row for row in reader if row.get("Close")]
            if not rows:
                return None
            last = rows[-1]
            close = float(str(last.get("Close") or "").replace(",", "."))
            if close <= 0:
                return None
            date_raw = str(last.get("Date") or "").strip()
            as_of = date_raw[:10] if date_raw else None
            return {
                "symbol": str(symbol).upper(),
                "stooq_symbol": stooq_sym,
                "close": close,
                "as_of": as_of,
                "fetched_at_utc": _utc_now(),
                "source": self.provider_name(),
            }
        except (TypeError, ValueError, KeyError):
            return None
