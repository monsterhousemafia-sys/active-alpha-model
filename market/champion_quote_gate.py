"""Fail-closed champion quote coverage before live rebalance waves."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS
from integrations.trading212.t212_instrument_quotes import champion_quote_coverage


def symbols_from_orders(orders: Iterable[Mapping[str, Any]]) -> List[str]:
    """Unique BUY symbols from a planned rebalance wave."""
    out: List[str] = []
    seen: set[str] = set()
    for row in orders or []:
        if str(row.get("side") or "BUY").upper() != "BUY":
            continue
        sym = str(row.get("symbol") or "").upper().strip()
        if sym and sym not in seen:
            seen.add(sym)
            out.append(sym)
    return sorted(out)


def coverage_label_de(coverage: Mapping[str, Any]) -> str:
    covered = int(coverage.get("covered_count") or 0)
    required = int(coverage.get("required_count") or 0)
    if required <= 0:
        return "0/0 Kurse"
    if coverage.get("coverage_ok"):
        return f"{covered}/{required} Kurse OK"
    return f"{covered}/{required} Kurse"


def coverage_block_message_de(coverage: Mapping[str, Any]) -> str:
    covered = int(coverage.get("covered_count") or 0)
    required = int(coverage.get("required_count") or 0)
    missing = coverage.get("missing_symbols") or []
    if coverage.get("coverage_ok"):
        return f"{covered}/{required} Live-Kurse verfügbar — Ausführung freigegeben."
    miss = ", ".join(str(s) for s in missing[:8])
    extra = f" (+{len(missing) - 8})" if len(missing) > 8 else ""
    return (
        f"Nur {covered}/{required} Live-Kurse für geplante Käufe — Rebalance blockiert. "
        f"Fehlend: {miss}{extra}. Bitte «Aktualisieren» (F5) oder US-Session warten."
    )


def require_champion_quote_coverage(
    root: Path,
    *,
    symbols: Optional[Iterable[str]] = None,
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    refresh_if_stale: bool = True,
) -> Dict[str, Any]:
    """
    Require executable EUR prices for every symbol in `symbols` (default: all 13 champion).

    Returns ok, coverage, quote_coverage_label_de, message_de, blocks.
    """
    root = Path(root)
    snap: Dict[str, Any]
    if quote_snapshot is not None:
        snap = dict(quote_snapshot)
    elif refresh_if_stale:
        from market.live_quote_engine import ensure_live_quotes_fresh_bounded

        snap = ensure_live_quotes_fresh_bounded(root, force=True, timeout_s=45.0)
    else:
        from market.live_quote_engine import load_live_quote_snapshot

        snap = load_live_quote_snapshot(root) or {}

    prices = snap.get("executable_prices_eur") or {}
    req = [str(s).upper() for s in (symbols if symbols is not None else CHAMPION_SYMBOLS)]
    req = [s for s in req if s]
    if not req:
        cov = {
            "required_count": 0,
            "covered_count": 0,
            "missing_symbols": [],
            "coverage_ok": True,
            "coverage_ratio": 1.0,
        }
        return {
            "ok": True,
            "coverage": cov,
            "quote_coverage_label_de": "0/0 Kurse OK",
            "message_de": "Keine Käufe geplant — Kurs-Gate entfällt.",
            "blocks": [],
            "quote_snapshot_utc": snap.get("generated_at_utc"),
            "price_source_by_symbol": snap.get("price_source_by_symbol") or {},
        }

    cov = champion_quote_coverage(prices, required_symbols=req)
    ok = bool(cov.get("coverage_ok"))
    label = coverage_label_de(cov)
    msg = coverage_block_message_de(cov) if not ok else label
    blocks: List[Dict[str, str]] = []
    if not ok:
        blocks.append({"code": "QUOTE_COVERAGE_INCOMPLETE", "message_de": msg})

    return {
        "ok": ok,
        "coverage": cov,
        "quote_coverage_label_de": label,
        "message_de": msg,
        "blocks": blocks,
        "quote_snapshot_utc": snap.get("generated_at_utc"),
        "price_source_by_symbol": {s: (snap.get("price_source_by_symbol") or {}).get(s) for s in req},
    }
