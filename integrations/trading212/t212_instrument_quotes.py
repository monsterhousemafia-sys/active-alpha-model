"""T212-first EUR quotes: held positions, then validated Yahoo fallback."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from aa_safe_io import atomic_write_json

from integrations.trading212.t212_quote_spike_analysis import (
    CHAMPION_SYMBOLS,
    filter_instruments_by_tickers,
    filter_positions_list,
    _normalize_instruments_list,
)

INSTRUMENTS_CACHE_REL = Path("evidence/t212_instruments_metadata_cache.json")
POSITIONS_CACHE_REL = Path("evidence/t212_positions_quote_cache.json")
CHAMPION_VERIFIED_REL = Path("evidence/t212_champion_instruments_verified.json")

INSTRUMENTS_CACHE_TTL_S = 55
POSITIONS_CACHE_TTL_S = 2

PRICE_SOURCE_T212_HELD = "T212"
PRICE_SOURCE_YAHOO_VALIDATED = "YAHOO_VALIDATED"
PRICE_SOURCE_YAHOO_BLOCKED = "YAHOO_BLOCKED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _cache_age_s(doc: Dict[str, Any]) -> Optional[float]:
    ts = str(doc.get("generated_at_utc") or doc.get("cached_at_utc") or "")
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None


def symbol_to_t212_ticker(symbol: str) -> str:
    sym = str(symbol or "").upper().strip()
    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE

    meta = MAPPING_TABLE.get(sym) or {}
    tid = str(meta.get("provider_instrument_id") or "").strip()
    if tid:
        return tid
    return f"{sym}_US_EQ"


def t212_ticker_to_symbol(ticker: str) -> str:
    t = str(ticker or "").upper().strip()
    if t.endswith("_US_EQ"):
        return t[: -len("_US_EQ")]
    if "_" in t:
        return t.split("_", 1)[0]
    return t


def champion_t212_tickers() -> Tuple[str, ...]:
    return tuple(symbol_to_t212_ticker(s) for s in CHAMPION_SYMBOLS)


def _load_credentials(root: Path) -> Tuple[Any, str]:
    from integrations.trading212.t212_auth_profile_model import (
        PROFILE_CONFIRMED_EXECUTION,
        PROFILE_MONITORING_READONLY,
    )
    from integrations.trading212.t212_credentials_loader import T212Credentials
    from integrations.trading212.t212_dual_profile_credential_store import get_profile_credentials
    from integrations.trading212.t212_execution_dpapi_store import load_execution_credentials
    from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials

    root = Path(root)
    for label, loader in (
        ("CONFIRMED_EXECUTION", lambda: load_execution_credentials(root) or get_profile_credentials(PROFILE_CONFIRMED_EXECUTION)),
        ("MONITORING_READONLY", lambda: get_profile_credentials(PROFILE_MONITORING_READONLY) or load_profile_credentials(PROFILE_MONITORING_READONLY)),
    ):
        creds = loader()
        if creds and creds.configured:
            return creds, label
    import os

    key = os.environ.get("T212_API_KEY", "").strip()
    sec = os.environ.get("T212_API_SECRET", "").strip()
    if key and sec:
        return T212Credentials(api_key=key, api_secret=sec), "ENV"
    return None, "NONE"


def _eur_per_share_from_position(pos: Dict[str, Any]) -> Optional[float]:
    wi = pos.get("walletImpact") if isinstance(pos.get("walletImpact"), dict) else {}
    qty = pos.get("quantity")
    cur_val = wi.get("currentValue")
    if cur_val is None or qty is None:
        return None
    try:
        q = float(qty)
        v = float(cur_val)
    except (TypeError, ValueError):
        return None
    if q <= 0 or v <= 0:
        return None
    if str(wi.get("currency") or "").upper() not in ("EUR", ""):
        return None
    return round(v / q, 4)


def fetch_held_position_prices_eur(
    root: Path,
    *,
    symbols: Optional[Iterable[str]] = None,
    force: bool = False,
) -> Dict[str, float]:
    """EUR/share from T212 positions (walletImpact), cached briefly."""
    root = Path(root)
    want = {str(s).upper() for s in (symbols or CHAMPION_SYMBOLS)}
    cache_path = root / POSITIONS_CACHE_REL
    if not force and cache_path.is_file():
        try:
            doc = json.loads(cache_path.read_text(encoding="utf-8"))
            if (_cache_age_s(doc) or 999) <= POSITIONS_CACHE_TTL_S:
                prices = doc.get("prices_eur_by_symbol") or {}
                return {k: float(v) for k, v in prices.items() if k in want and v}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    creds, profile = _load_credentials(root)
    prices: Dict[str, float] = {}
    status = "SKIPPED"
    err = ""
    if creds:
        try:
            from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient

            raw = T212LiveReadOnlyClient(creds).get("/equity/positions")
            for pos in filter_positions_list(raw):
                inst = pos.get("instrument") if isinstance(pos.get("instrument"), dict) else {}
                sym = t212_ticker_to_symbol(str(inst.get("ticker") or ""))
                if sym not in want:
                    continue
                px = _eur_per_share_from_position(pos)
                if px and px > 0:
                    prices[sym] = px
            status = "OK"
        except Exception as exc:
            status = "ERROR"
            err = str(exc)[:200]

    atomic_write_json(
        cache_path,
        {
            "generated_at_utc": _utc_now(),
            "credential_profile": profile,
            "fetch_status": status,
            "fetch_error": err or None,
            "prices_eur_by_symbol": prices,
        },
    )
    return prices


def load_champion_instrument_rows(root: Path) -> List[Dict[str, Any]]:
    """Champion metadata rows from verified cache or instruments cache."""
    root = Path(root)
    for rel in (CHAMPION_VERIFIED_REL, INSTRUMENTS_CACHE_REL, Path("evidence/t212_instruments_sample.json")):
        path = root / rel
        if not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        rows = doc.get("champion_instruments")
        if isinstance(rows, list) and rows:
            return [x for x in rows if isinstance(x, dict)]
        all_rows = _normalize_instruments_list(doc)
        if all_rows:
            return filter_instruments_by_tickers(all_rows, champion_t212_tickers())
    return []


def verify_champion_instruments(root: Path, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    found = {t212_ticker_to_symbol(str(r.get("ticker") or "")) for r in rows}
    missing = [s for s in CHAMPION_SYMBOLS if s not in found]
    return {
        "matched": len(found & set(CHAMPION_SYMBOLS)),
        "required": len(CHAMPION_SYMBOLS),
        "missing_symbols": missing,
        "ok": not missing,
    }


def fetch_quotes_for_tickers(
    root: Path,
    t212_tickers: Iterable[str],
    *,
    force_positions: bool = False,
) -> Dict[str, Any]:
    """
    Best-effort EUR prices for champion symbols.

    Returns dict with prices_eur_by_symbol, price_source_by_symbol, held_from_t212, verification.
    """
    root = Path(root)
    tickers = [str(t).upper() for t in t212_tickers]
    symbols = [t212_ticker_to_symbol(t) for t in tickers]
    sym_set = set(symbols)

    held = fetch_held_position_prices_eur(root, symbols=sym_set, force=force_positions)
    prices: Dict[str, float] = dict(held)
    sources: Dict[str, str] = {s: PRICE_SOURCE_T212_HELD for s in held}

    rows = load_champion_instrument_rows(root)
    verification = verify_champion_instruments(root, rows)

    return {
        "generated_at_utc": _utc_now(),
        "prices_eur_by_symbol": prices,
        "price_source_by_symbol": sources,
        "held_symbols": sorted(held.keys()),
        "instrument_verification": verification,
        "metadata_rows": len(rows),
    }


def merge_t212_yahoo_prices(
    *,
    champion_symbols: Iterable[str],
    t212_prices: Dict[str, float],
    t212_sources: Dict[str, str],
    yahoo_prices: Dict[str, float],
    yahoo_valid: Optional[Dict[str, bool]] = None,
    anchor_prices_eur: Optional[Dict[str, float]] = None,
) -> Tuple[Dict[str, float], Dict[str, str], Dict[str, Any]]:
    """Apply T212-first chain; Yahoo only when validated and not blocked."""
    from paper.p16d.quote_plausibility import sanitize_price_eur

    out: Dict[str, float] = {}
    sources: Dict[str, str] = {}
    audit: Dict[str, Any] = {"blocked": {}, "used": {}}

    for sym in champion_symbols:
        s = str(sym).upper()
        if s in t212_prices and t212_prices[s] > 0:
            px, _, reason = sanitize_price_eur(s, t212_prices[s], source=PRICE_SOURCE_T212_HELD)
            if px and px > 0:
                out[s] = px
                sources[s] = t212_sources.get(s, PRICE_SOURCE_T212_HELD)
                audit["used"][s] = reason
            continue

        raw = yahoo_prices.get(s)
        valid = (yahoo_valid or {}).get(s, True)
        if not valid or raw is None:
            audit["blocked"][s] = "YAHOO_MISSING_OR_INVALID"
            continue
        px, changed, reason = sanitize_price_eur(
            s,
            float(raw),
            source=PRICE_SOURCE_YAHOO_VALIDATED,
            for_orders=True,
            anchor_prices_eur=anchor_prices_eur,
        )
        if px and px > 0:
            out[s] = px
            sources[s] = PRICE_SOURCE_YAHOO_VALIDATED
            audit["used"][s] = reason
        else:
            audit["blocked"][s] = reason or "YAHOO_BLOCKED"

    return out, sources, audit


def champion_quote_coverage(
    prices: Dict[str, float],
    *,
    required_symbols: Iterable[str] = CHAMPION_SYMBOLS,
) -> Dict[str, Any]:
    req = [str(s).upper() for s in required_symbols]
    have = [s for s in req if s in prices and float(prices[s]) > 0]
    missing = [s for s in req if s not in have]
    n = len(req)
    return {
        "required_count": n,
        "covered_count": len(have),
        "missing_symbols": missing,
        "coverage_ok": len(have) == n and n > 0,
        "coverage_ratio": round(len(have) / n, 4) if n else 0.0,
    }
