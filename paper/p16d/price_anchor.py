"""OHLCV-panel anchor prices for live-quote plausibility (EUR)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional

_PANEL_REL = Path("model_output_sp500_pit_t212/price_cache/ohlcv_panel.parquet")


def _resolve_out_dir(root: Path) -> Path:
    root = Path(root)
    primary = root / _PANEL_REL.parent.parent
    if (root / _PANEL_REL).is_file():
        return primary
    alt = root / "model_output" / "price_cache" / "ohlcv_panel.parquet"
    if alt.is_file():
        return root / "model_output"
    return primary


def load_panel_anchor_eur(
    root: Path,
    symbols: Optional[Iterable[str]] = None,
    *,
    band_pct: float = 0.40,
) -> Dict[str, Any]:
    """
    Latest non-NaN panel close per symbol, converted to EUR.

    Returns anchor_eur map plus optional band bounds for sanitize_price_eur.
    """
    root = Path(root)
    panel_path = root / _PANEL_REL
    if not panel_path.is_file():
        alt = root / "model_output" / "price_cache" / "ohlcv_panel.parquet"
        panel_path = alt if alt.is_file() else panel_path
    if not panel_path.is_file():
        return {"anchor_eur": {}, "as_of": {}, "fx_usd_to_eur": None}

    try:
        import pandas as pd
    except ImportError:
        return {"anchor_eur": {}, "as_of": {}, "fx_usd_to_eur": None}

    want = {str(s).upper().strip() for s in (symbols or []) if str(s).strip()}
    try:
        panel = pd.read_parquet(panel_path, columns=["date", "ticker", "Close"])
    except Exception:
        return {"anchor_eur": {}, "as_of": {}, "fx_usd_to_eur": None}

    panel["date"] = pd.to_datetime(panel["date"], errors="coerce")
    panel["ticker"] = panel["ticker"].astype(str).str.upper()
    panel = panel.dropna(subset=["Close"])
    if panel.empty:
        return {"anchor_eur": {}, "as_of": {}, "fx_usd_to_eur": None}

    fx_rate: Optional[float] = None
    try:
        from paper.p16d.multi_currency_fx_feed import fetch_multi_currency_fx

        fx_obs = fetch_multi_currency_fx(root)
        fx_rate = float(fx_obs.get("usd_to_eur_rate") or 0) or None
    except Exception:
        pass
    if fx_rate is None or fx_rate <= 0:
        fx_rate = 0.866  # read-only observation fallback only for band math

    anchor_eur: Dict[str, float] = {}
    as_of: Dict[str, str] = {}
    for sym, grp in panel.groupby("ticker"):
        if want and sym not in want:
            continue
        row = grp.sort_values("date").iloc[-1]
        close_usd = float(row["Close"])
        anchor_eur[sym] = round(close_usd * fx_rate, 4)
        dt = row["date"]
        as_of[sym] = str(dt.date()) if hasattr(dt, "date") else str(dt)

    band = max(float(band_pct), 0.05)
    bounds: Dict[str, Dict[str, float]] = {}
    for sym, px in anchor_eur.items():
        bounds[sym] = {
            "floor_eur": round(px * (1.0 - band), 4),
            "cap_eur": round(px * (1.0 + band), 4),
        }

    return {
        "anchor_eur": anchor_eur,
        "bounds_eur": bounds,
        "as_of": as_of,
        "fx_usd_to_eur": fx_rate,
        "band_pct": band,
        "panel_path": str(panel_path),
    }
