"""Sanitize EUR prices — T212 trusted; Yahoo anchored to OHLCV panel."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

# Emergency static caps when no panel anchor exists (EUR).
_SANE_EUR_CAP: Dict[str, float] = {
    "INTC": 160.0,
    "MU": 1100.0,
    "STX": 950.0,
    "WDC": 600.0,
    "SNDK": 2000.0,
    "CIEN": 500.0,
    "OXY": 110.0,
    "GOOGL": 400.0,
    "GOOG": 400.0,
    "AMD": 550.0,
    "CAT": 1100.0,
    "ON": 140.0,
    "VRT": 400.0,
    "TXN": 280.0,
}
_DEFAULT_CAP = 250.0
_MIN_EUR = 3.0
_ANCHOR_BAND_PCT = 0.40

_T212_SOURCES = frozenset({"T212", "T212_HELD", "T212_POSITION"})


def _anchor_bounds(
    symbol: str,
    anchor_prices_eur: Optional[Mapping[str, float]],
    *,
    band_pct: float = _ANCHOR_BAND_PCT,
) -> Optional[Tuple[float, float]]:
    if not anchor_prices_eur:
        return None
    anchor = anchor_prices_eur.get(symbol)
    if anchor is None:
        return None
    try:
        px = float(anchor)
    except (TypeError, ValueError):
        return None
    if px <= 0:
        return None
    band = max(float(band_pct), 0.05)
    return round(px * (1.0 - band), 4), round(px * (1.0 + band), 4)


def sanitize_price_eur(
    symbol: str,
    price_eur: float | None,
    *,
    source: str = "YAHOO",
    for_orders: bool = False,
    anchor_prices_eur: Optional[Mapping[str, float]] = None,
    anchor_band_pct: float = _ANCHOR_BAND_PCT,
) -> Tuple[float | None, bool, str]:
    """
    Return (price_eur, was_adjusted, reason).

    T212-held prices: no cap shrink (trust walletImpact EUR/share).
    Yahoo: panel-anchored band when available; else static cap fallback.
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

    bounds = _anchor_bounds(sym, anchor_prices_eur, band_pct=anchor_band_pct)
    if bounds is not None:
        floor_eur, cap_eur = bounds
        if floor_eur <= px <= cap_eur:
            return round(px, 4), False, "OK"
        if for_orders:
            reason = "ABOVE_ANCHOR_BLOCKED" if px > cap_eur else "BELOW_ANCHOR_BLOCKED"
            return None, True, reason
        adjusted = round(cap_eur, 4) if px > cap_eur else round(floor_eur, 4)
        reason = "ABOVE_ANCHOR" if px > cap_eur else "BELOW_ANCHOR"
        return adjusted, True, reason

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
    anchor_prices_eur: Optional[Mapping[str, float]] = None,
    anchor_band_pct: float = _ANCHOR_BAND_PCT,
) -> Dict[str, Any]:
    """Return sanitized map + audit metadata for snapshot."""
    out: Dict[str, float] = {}
    adjustments: Dict[str, Any] = {}
    blocked: Dict[str, str] = {}
    sources = price_source_by_symbol or {}
    for sym, raw in (prices or {}).items():
        key = str(sym).upper()
        src = sources.get(key, "YAHOO")
        adj, changed, reason = sanitize_price_eur(
            key,
            raw,
            source=src,
            for_orders=for_orders,
            anchor_prices_eur=anchor_prices_eur,
            anchor_band_pct=anchor_band_pct,
        )
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
        "anchor_used": bool(anchor_prices_eur),
    }


def load_anchor_prices_for_sanitize(root: Path, symbols: Optional[Iterable[str]] = None) -> Dict[str, float]:
    """Convenience: panel anchor EUR map for live quote sanitization."""
    from paper.p16d.price_anchor import load_panel_anchor_eur

    doc = load_panel_anchor_eur(root, symbols)
    return dict(doc.get("anchor_eur") or {})
