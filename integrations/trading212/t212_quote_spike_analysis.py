"""Phase 0 — analyze T212 API payloads for usable live price fields."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set, Tuple

# Keys that may carry a tradable price (case-insensitive substring match on path tail).
_PRICE_KEY_RE = re.compile(
    r"(^price$|price$|last|ltp|bid|ask|quote|rate|nav|close|open|high|low|"
    r"currentprice|averageprice|limitprice|filledvalue)",
    re.I,
)

CHAMPION_SYMBOLS = (
    "STX",
    "WDC",
    "SNDK",
    "INTC",
    "CIEN",
    "GOOGL",
    "GOOG",
    "AMD",
    "CAT",
    "ON",
    "MU",
    "VRT",
    "TXN",
    "OXY",
)

CHAMPION_T212_TICKERS = tuple(f"{s}_US_EQ" for s in CHAMPION_SYMBOLS if s != "OXY") + ("OXY_US_EQ",)


def _iter_paths(obj: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(obj, dict):
        for key, val in obj.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, val
            yield from _iter_paths(val, path)
    elif isinstance(obj, list) and obj and len(obj) <= 50:
        for i, item in enumerate(obj[:3]):
            yield from _iter_paths(item, f"{prefix}[{i}]")


def discover_price_fields(payload: Any) -> List[Dict[str, Any]]:
    """Return unique JSON paths whose keys look price-related, with sample values."""
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for path, val in _iter_paths(payload):
        leaf = path.split(".")[-1].split("[")[0]
        if not _PRICE_KEY_RE.search(leaf):
            continue
        if isinstance(val, (dict, list)):
            continue
        if path in seen:
            continue
        seen.add(path)
        try:
            sample = float(val)
        except (TypeError, ValueError):
            sample = str(val)[:80]
        out.append({"path": path, "sample": sample})
    out.sort(key=lambda x: x["path"])
    return out


def _normalize_instruments_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        for key in ("items", "instruments", "data", "content"):
            items = raw.get(key)
            if isinstance(items, list):
                return [x for x in items if isinstance(x, dict)]
    return []


def filter_instruments_by_tickers(
    instruments: List[Dict[str, Any]],
    tickers: Iterable[str],
) -> List[Dict[str, Any]]:
    want = {str(t).upper() for t in tickers}
    matched: List[Dict[str, Any]] = []
    for row in instruments:
        t = str(row.get("ticker") or "").upper()
        if t in want:
            matched.append(row)
    return matched


def filter_positions_list(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        if any(k in raw for k in ("ticker", "quantity", "currentPrice")):
            return [raw]
        items = raw.get("items") or raw.get("positions")
        if isinstance(items, list):
            return [x for x in items if isinstance(x, dict)]
    return []


def summarize_positions_for_pricing(positions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for pos in positions:
        inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
        ticker = str(inst.get("ticker") or pos.get("ticker") or "")
        sym = ticker.split("_")[0] if ticker else "?"
        wi = pos.get("walletImpact") if isinstance(pos.get("walletImpact"), dict) else {}
        rows.append(
            {
                "ticker": ticker,
                "symbol": sym,
                "quantity": pos.get("quantity"),
                "currentPrice": pos.get("currentPrice"),
                "averagePricePaid": pos.get("averagePricePaid"),
                "walletImpact_currency": wi.get("currency"),
                "walletImpact_currentValue_eur": wi.get("currentValue"),
                "walletImpact_totalCost_eur": wi.get("totalCost"),
                "implied_eur_per_share": (
                    round(float(wi["currentValue"]) / float(pos["quantity"]), 4)
                    if wi.get("currentValue") is not None
                    and pos.get("quantity")
                    and float(pos["quantity"]) > 0
                    else None
                ),
            }
        )
    return rows


def analyze_position_price_units(rows: List[Dict[str, Any]]) -> List[str]:
    """Human-readable warnings when currentPrice disagrees with EUR wallet impact."""
    warnings: List[str] = []
    for row in rows:
        sym = row.get("symbol")
        cp = row.get("currentPrice")
        implied = row.get("implied_eur_per_share")
        if cp is None or implied is None:
            continue
        try:
            cp_f = float(cp)
            imp_f = float(implied)
        except (TypeError, ValueError):
            continue
        if cp_f <= 0 or imp_f <= 0:
            continue
        ratio = cp_f / imp_f
        if ratio > 1.8 or ratio < 0.55:
            warnings.append(
                f"{sym}: currentPrice={cp_f} vs EUR/share≈{imp_f} (ratio {ratio:.2f}) — "
                "für Sizing walletImpact.currentValue/quantity nutzen, nicht currentPrice roh."
            )
    return warnings


def recommend_quote_strategy(
    *,
    instruments_price_fields: List[Dict[str, Any]],
    instruments_champion_rows: List[Dict[str, Any]],
    positions_summary: List[Dict[str, Any]],
    instruments_fetch_ok: bool,
    positions_fetch_ok: bool,
) -> Dict[str, Any]:
    """Build decision payload for docs/T212_QUOTE_SOURCE_DECISION.md."""
    inst_has_ltp = any(
        "last" in f["path"].lower() or "ltp" in f["path"].lower() or "price" in f["path"].lower()
        for f in instruments_price_fields
    )
    champion_inst_rows = len(instruments_champion_rows)
    held = len(positions_summary)

    primary = "T212_POSITIONS_CURRENT_PRICE_FOR_HELD"
    pre_buy = "REQUIRES_SPIKE_OR_FALLBACK"
    notes: List[str] = []

    if instruments_fetch_ok and inst_has_ltp and champion_inst_rows > 0:
        pre_buy = "T212_METADATA_INSTRUMENTS"
        notes.append("Instrument-Metadaten enthalten preisähnliche Felder für Champion-Ticker.")
    elif instruments_fetch_ok and champion_inst_rows > 0:
        pre_buy = "T212_METADATA_NO_PRICE_USE_YAHOO_VALIDATED"
        notes.append(
            "Instrument-Metadaten für Champion-Ticker vorhanden, aber kein klares Live-Preisfeld — Felder in Sample prüfen."
        )
    else:
        pre_buy = "YAHOO_WITH_STRICT_GATE_AND_T212_POSITIONS_HELD"
        notes.append("Pre-buy: Yahoo nur mit Validierung; gehaltene Titel über positions.currentPrice.")

    if held > 0:
        notes.append(
            f"{held} offene Position(en): EUR/Stück = walletImpact.currentValue / quantity (nicht currentPrice direkt)."
        )
        unit_warnings = analyze_position_price_units(positions_summary)
        notes.extend(unit_warnings[:5])
    if champion_inst_rows >= len(CHAMPION_T212_TICKERS):
        notes.append(
            "metadata/instruments: nur Ticker/ISIN/Währung — alle 13 Champion-Ticker verifiziert, kein Live-Preis."
        )
    elif champion_inst_rows > 0:
        notes.append(
            f"metadata/instruments: {champion_inst_rows}/{len(CHAMPION_T212_TICKERS)} Champion-Ticker im Sample."
        )
    else:
        notes.append(
            "metadata/instruments: Champion-Ticker noch nicht verifiziert (429/Cache) — erneut nach 50s Rate-Limit."
        )
    notes.append(
        "Offizielle Public API v0 dokumentiert kein REST /equity/quote; Stop-Orders referenzieren LTP intern."
    )
    notes.append("metadata/instruments Rate-Limit: 1 req / 50s — Cache Pflicht.")

    return {
        "primary_for_held_positions": primary,
        "primary_for_pre_buy_champion": pre_buy,
        "instruments_usable_for_live_quote": inst_has_ltp and champion_inst_rows > 0,
        "positions_usable_for_live_quote": held > 0,
        "notes_de": notes,
        "official_rest_quote_endpoint": False,
        "websocket_bid_ask_optional_phase": 4,
    }
