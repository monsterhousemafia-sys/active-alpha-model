"""Normalize Trading 212 position payloads for GUI tables."""
from __future__ import annotations

from typing import Any, Dict, List


def _pick_float(doc: Dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        if key in doc and doc[key] is not None:
            try:
                return float(doc[key])
            except (TypeError, ValueError):
                continue
    return None


def _pick_symbol(doc: Dict[str, Any]) -> str:
    for key in ("ticker", "symbol", "instrument", "name"):
        val = doc.get(key)
        if val:
            text = str(val).strip()
            if text:
                return text.split("_")[0] if "_" in text else text
    instrument = doc.get("instrument")
    if isinstance(instrument, dict):
        for key in ("ticker", "symbol", "name", "isin"):
            val = instrument.get(key)
            if val:
                return str(val).split("_")[0]
    return "?"


def normalize_positions_payload(positions: Any) -> List[Dict[str, Any]]:
    if isinstance(positions, dict):
        items = positions.get("items") or positions.get("positions") or positions.get("data")
        if items is None and any(k in positions for k in ("ticker", "quantity", "symbol")):
            items = [positions]
    elif isinstance(positions, list):
        items = positions
    else:
        items = []

    rows: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        qty = _pick_float(raw, ("quantity", "qty", "units", "size"))
        value = _pick_float(
            raw,
            (
                "value",
                "currentValue",
                "marketValue",
                "total",
            ),
        )
        if value is None:
            wi = raw.get("walletImpact")
            if isinstance(wi, dict):
                value = _pick_float(wi, ("currentValue", "totalCost"))
        price = _pick_float(raw, ("currentPrice", "price", "averagePrice", "avgPrice"))
        if value is None and qty is not None and price is not None:
            value = qty * price
        rows.append(
            {
                "symbol": _pick_symbol(raw),
                "quantity": qty,
                "value_eur": value,
                "status": str(raw.get("status") or "READONLY"),
            }
        )
    return rows


def position_table_rows(positions: Any) -> List[List[str]]:
    out: List[List[str]] = []
    for row in normalize_positions_payload(positions):
        qty = row["quantity"]
        qty_txt = f"{qty:.6f}".rstrip("0").rstrip(".") if qty is not None else "—"
        val = row["value_eur"]
        val_txt = f"{val:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".") if val is not None else "—"
        out.append([row["symbol"], qty_txt, val_txt, row["status"]])
    return out
