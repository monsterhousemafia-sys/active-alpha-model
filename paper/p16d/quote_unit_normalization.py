"""Quote unit normalization — GBp/pence to major currency units."""
from __future__ import annotations

from typing import Any, Dict, Tuple

PENCE_EXCHANGES = {"LSE", "LON", "XLON"}


def normalize_quote_price(
    *,
    raw_price: float,
    exchange: str,
    quote_currency: str,
    instrument_type: str = "EQUITY",
) -> Tuple[float, Dict[str, Any]]:
    """Return normalized price in quote_currency major units and metadata."""
    meta: Dict[str, Any] = {
        "raw_price": raw_price,
        "raw_price_unit": quote_currency,
        "quote_currency": quote_currency,
        "normalization_factor": 1.0,
        "normalized_quote_price": raw_price,
    }
    ex = (exchange or "").upper()
    qc = quote_currency.upper()

    if ex in PENCE_EXCHANGES and qc == "GBP" and raw_price > 50:
        meta["raw_price_unit"] = "GBp"
        meta["normalization_factor"] = 0.01
        meta["normalized_quote_price"] = round(raw_price * 0.01, 6)
        meta["normalization_note"] = "LSE_pence_to_GBP_major_unit"
    elif qc == "GBp":
        meta["quote_currency"] = "GBP"
        meta["raw_price_unit"] = "GBp"
        meta["normalization_factor"] = 0.01
        meta["normalized_quote_price"] = round(raw_price * 0.01, 6)

    return float(meta["normalized_quote_price"]), meta
