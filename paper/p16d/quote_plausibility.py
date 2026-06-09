"""Sanitize EUR prices — T212 trusted; Yahoo fail-closed for orders."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Conservative upper bounds (EUR) for US pilot symbols — yfinance can return wrong tickers.
_SANE_EUR_CAP: Dict[str, float] = {
    "INTC": 140.0,
    "MU": 280.0,
    "STX": 220.0,
    "WDC": 220.0,
    "CIEN": 220.0,
    "OXY": 95.0,
    "GOOGL": 350.0,
    "GOOG": 350.0,
    "AMD": 350.0,
    "CAT": 350.0,
    "ON": 120.0,
    "VRT": 200.0,
    "TXN": 250.0,
}
_DEFAULT_CAP = 200.0
_MIN_EUR = 3.0

_T212_SOURCES = frozenset({"T212", "T212_HELD", "T212_POSITION"})


def sanitize_price_eur(
    symbol: str,
    price_eur: float | None,
    *,
    source: str = "YAHOO",
    for_orders: bool = False,
) -> Tuple[float | None, bool, str]:
    """
    Return (price_eur, was_adjusted, reason).

    T212-held prices: no cap shrink (trust walletImpact EUR/share).
    Yahoo + for_orders: block out-of-band prices instead of 85% cap fake limits.
    Yahoo planning (for_orders=False): legacy 85% cap for backward-compatible UI batch.
    """
    sym = str(symbol or "").upper().strip()
    if price_eur is None:
        return None, False, "MISSING"
    try:
        px = float(price_eur)
    except (TypeError, ValueError):
        return None, False, "INVALID"
    if px <= 0:
        return None, False, "NON_POSITIVE"

    src_u = str(source or "YAHOO").upper()
    if src_u in _T212_SOURCES:
        if px < _MIN_EUR:
            return None, True, "T212_BELOW_FLOOR"
        return round(px, 4), False, "OK"

    cap = float(_SANE_EUR_CAP.get(sym, _DEFAULT_CAP))
    if _MIN_EUR <= px <= cap:
        return round(px, 4), False, "OK"

    if for_orders:
        reason = "ABOVE_CAP_BLOCKED" if px > cap else "BELOW_FLOOR_BLOCKED"
        return None, True, reason

    adjusted = round(cap * 0.85, 2) if px > cap else round(_MIN_EUR, 2)
    reason = "ABOVE_CAP" if px > cap else "BELOW_FLOOR"
    return adjusted, True, reason


def sanitize_executable_prices(
    prices: Dict[str, float],
    *,
    price_source_by_symbol: Optional[Dict[str, str]] = None,
    for_orders: bool = False,
) -> Dict[str, Any]:
    """Return sanitized map + audit metadata for snapshot."""
    out: Dict[str, float] = {}
    adjustments: Dict[str, Any] = {}
    blocked: Dict[str, str] = {}
    sources = price_source_by_symbol or {}
    for sym, raw in (prices or {}).items():
        key = str(sym).upper()
        src = sources.get(key, "YAHOO")
        adj, changed, reason = sanitize_price_eur(key, raw, source=src, for_orders=for_orders)
        if adj is not None:
            out[key] = adj
        elif for_orders and changed:
            blocked[key] = reason
        if changed and adj is not None:
            adjustments[key] = {
                "raw_price_eur": raw,
                "sanitized_price_eur": adj,
                "reason": reason,
                "source": src,
            }
    return {
        "executable_prices_eur": out,
        "adjustments": adjustments,
        "blocked_symbols": blocked,
        "had_adjustments": bool(adjustments),
        "had_blocks": bool(blocked),
    }
