"""Live executable quote engine — freshness-gated prices for cockpit calculations."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from aa_safe_io import atomic_write_json
from paper.p16d.instrument_identity import (
    CHAMPION_EXECUTABLE_FILL,
    EXECUTABLE_FILL,
    INSTRUMENT_DEFS,
    build_identity_bindings,
)

DEFAULT_MAX_AGE_SECONDS = 120
DEFAULT_AUTO_REFRESH_SECONDS = 60
SNAPSHOT_REL = Path("paper/p16d/live_quote_snapshot.json")
PILOT_GAP_TARGETS_REL = Path("paper/config/pilot_gap_targets_eur.json")

_DEFAULT_GAP_TARGETS_EUR: Dict[str, float] = {
    "OXY": 88.51,
    "WDC": 75.96,
    "STX": 62.86,
    "INTC": 41.95,
    "MU": 38.45,
    "CIEN": 37.85,
}

logger = logging.getLogger(__name__)


def load_pilot_gap_targets(root: Optional[Path] = None) -> Dict[str, float]:
    """Load EUR allocation targets from config; fall back to embedded defaults."""
    path = (Path(root) if root else Path(".")) / PILOT_GAP_TARGETS_REL
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("targets_eur")
            if isinstance(raw, dict) and raw:
                return {str(k).upper(): float(v) for k, v in raw.items()}
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            logger.warning("pilot gap targets config unreadable — using defaults", exc_info=True)
    return dict(_DEFAULT_GAP_TARGETS_EUR)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def max_quote_age_seconds() -> int:
    raw = os.environ.get("AA_LIVE_QUOTE_MAX_AGE_S", str(DEFAULT_MAX_AGE_SECONDS)).strip()
    try:
        return max(15, int(raw))
    except ValueError:
        return DEFAULT_MAX_AGE_SECONDS


def auto_refresh_interval_seconds() -> int:
    raw = os.environ.get("AA_LIVE_QUOTE_REFRESH_INTERVAL_S", str(DEFAULT_AUTO_REFRESH_SECONDS)).strip()
    try:
        return max(15, int(raw))
    except ValueError:
        return DEFAULT_AUTO_REFRESH_SECONDS


def snapshot_path(root: Path) -> Path:
    return Path(root) / SNAPSHOT_REL


def _parse_utc(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def age_seconds_since(ts: str) -> Optional[float]:
    dt = _parse_utc(ts)
    if dt is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds())


def classify_freshness(snapshot: Dict[str, Any], *, max_age_s: Optional[int] = None) -> Dict[str, Any]:
    max_age = max_age_s if max_age_s is not None else int(snapshot.get("max_age_seconds") or max_quote_age_seconds())
    generated = str(snapshot.get("generated_at_utc") or "")
    age = age_seconds_since(generated)
    prices = snapshot.get("executable_prices_eur") or {}
    gate = str(snapshot.get("data_quality_gate") or "")
    fx_gate = str(snapshot.get("fx_runtime_gate") or "")

    if not prices:
        status = "MISSING"
        calc_allowed = False
        reason = "Keine ausführbaren Live-Preise — Internet prüfen und Aktualisieren."
    elif age is None:
        status = "STALE"
        calc_allowed = False
        reason = "Preis-Zeitstempel ungültig — erneut abrufen."
    elif age > max_age:
        status = "STALE"
        calc_allowed = False
        reason = f"Preise älter als {max_age}s ({int(age)}s) — Live-Aktualisierung erforderlich."
    elif gate and "PASS" not in gate and "PARTIAL" not in gate:
        status = "DEGRADED"
        calc_allowed = len(prices) >= 4
        reason = f"Datenqualitäts-Gate: {gate}"
    else:
        cov = snapshot.get("champion_quote_coverage") or {}
        if cov and not cov.get("coverage_ok"):
            status = "STALE"
            calc_allowed = False
            missing = cov.get("missing_symbols") or []
            miss = ", ".join(str(s) for s in missing[:5])
            reason = (
                f"Champion-Kurse unvollständig "
                f"({cov.get('covered_count')}/{cov.get('required_count')}) — fehlend: {miss}"
            )
        else:
            status = "FRESH"
            calc_allowed = True
            reason = "Live-Preise aktuell — Berechnung freigegeben."

    return {
        "status": status,
        "calculation_allowed": calc_allowed,
        "reason": reason,
        "age_seconds": round(age, 1) if age is not None else None,
        "max_age_seconds": max_age,
        "executable_symbol_count": len(prices),
        "fx_runtime_gate": fx_gate,
        "data_quality_gate": gate,
        "generated_at_utc": generated,
    }


def load_live_quote_snapshot(root: Path) -> Optional[Dict[str, Any]]:
    path = snapshot_path(root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    doc.setdefault("freshness", classify_freshness(doc))
    return doc


def _quotes_from_batch(batch: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for conv in batch.get("instrument_conversions") or []:
        sym = conv.get("user_reference_symbol")
        if not sym:
            continue
        out[str(sym)] = {
            "price_eur": conv.get("converted_price_eur"),
            "raw_price": conv.get("raw_price"),
            "quote_currency": conv.get("quote_currency"),
            "market_event_time_utc": conv.get("market_event_time_utc") or conv.get("valuation_timestamp_utc"),
            "data_quality_gate": conv.get("data_quality_gate"),
            "conversion_valid": conv.get("conversion_valid"),
        }
    return out


def refresh_live_quotes(root: Path, *, force: bool = False, owner: str = "") -> Dict[str, Any]:
    """Fetch live quotes via yfinance + FX; always writes snapshot when online."""
    root = Path(root)
    if not force:
        cached = load_live_quote_snapshot(root)
        if cached:
            fresh = classify_freshness(cached)
            if fresh["status"] == "FRESH" and fresh.get("calculation_allowed"):
                cached["freshness"] = fresh
                cached["refresh_skipped"] = True
                return cached

    from analytics.r3_live_quote_access_gate import (
        access_denied_snapshot,
        check_live_quote_refresh_allowed,
    )

    gate = check_live_quote_refresh_allowed(root, owner=owner, operation="refresh")
    if not gate.get("allowed"):
        return access_denied_snapshot(root, gate=gate)

    from aa_refresh_guard import end_quote_refresh, try_begin_quote_refresh

    if not try_begin_quote_refresh():
        stale = load_live_quote_snapshot(root)
        if stale:
            stale = dict(stale)
            stale["refresh_skipped"] = True
            stale["refresh_concurrent"] = True
            stale.setdefault("freshness", classify_freshness(stale))
            return stale
        return _synthetic_snapshot(root) if os.environ.get("AA_OFFLINE_COCKPIT_TEST") else {
            "generated_at_utc": _utc_now(),
            "provider": "READONLY_YFINANCE",
            "executable_prices_eur": {},
            "quotes_by_symbol": {},
            "refresh_skipped": True,
            "refresh_concurrent": True,
            "freshness": classify_freshness({"generated_at_utc": "1970-01-01T00:00:00+00:00"}),
        }

    try:
        return _refresh_live_quotes_impl(root)
    finally:
        end_quote_refresh()


def _yahoo_valid_by_symbol(batch: Dict[str, Any]) -> Dict[str, bool]:
    valid: Dict[str, bool] = {}
    for conv in batch.get("instrument_conversions") or []:
        sym = str(conv.get("user_reference_symbol") or "").upper()
        if sym:
            valid[sym] = bool(conv.get("conversion_valid"))
    return valid


def _merge_champion_quote_chain(root: Path, batch: Dict[str, Any]) -> Dict[str, Any]:
    """T212 held positions first, then validated Yahoo for remaining champion symbols."""
    from integrations.trading212.t212_instrument_quotes import (
        PRICE_SOURCE_T212_HELD,
        champion_quote_coverage,
        fetch_held_position_prices_eur,
        merge_t212_yahoo_prices,
    )

    from paper.p16d.quote_plausibility import load_anchor_prices_for_sanitize

    yahoo_raw = dict(batch.get("executable_prices_eur") or {})
    yahoo_raw.update({k: v for k, v in (batch.get("prices_eur") or {}).items() if k not in yahoo_raw})
    anchor_eur = load_anchor_prices_for_sanitize(root, CHAMPION_EXECUTABLE_FILL)
    t212_held = fetch_held_position_prices_eur(root, symbols=CHAMPION_EXECUTABLE_FILL)
    t212_sources = {s: PRICE_SOURCE_T212_HELD for s in t212_held}
    merged, sources, audit = merge_t212_yahoo_prices(
        champion_symbols=sorted(CHAMPION_EXECUTABLE_FILL),
        t212_prices=t212_held,
        t212_sources=t212_sources,
        yahoo_prices=yahoo_raw,
        yahoo_valid=_yahoo_valid_by_symbol(batch),
        anchor_prices_eur=anchor_eur,
    )
    coverage = champion_quote_coverage(merged)
    provider = "T212_FIRST_YAHOO_VALIDATED"
    if t212_held and coverage.get("coverage_ok"):
        provider = "T212_PLUS_YAHOO_VALIDATED"
    elif t212_held and not coverage.get("coverage_ok"):
        provider = "T212_PARTIAL_YAHOO_VALIDATED"
    elif coverage.get("coverage_ok"):
        provider = "YAHOO_VALIDATED_ONLY"
    return {
        "executable_prices_eur": merged,
        "price_source_by_symbol": sources,
        "quote_merge_audit": audit,
        "champion_quote_coverage": coverage,
        "t212_held_prices_eur": t212_held,
        "provider": provider,
    }


def _refresh_live_quotes_impl(root: Path) -> Dict[str, Any]:
    from paper.p16d.forward_collect import collect_post_baseline_batch

    root = Path(root)
    identity = build_identity_bindings(root)
    batch = collect_post_baseline_batch(root, identity)
    now = _utc_now()
    chain = _merge_champion_quote_chain(root, batch)
    exec_prices = dict(chain.get("executable_prices_eur") or {})
    from paper.p16d.quote_plausibility import load_anchor_prices_for_sanitize, sanitize_executable_prices

    anchor_eur = load_anchor_prices_for_sanitize(root, CHAMPION_EXECUTABLE_FILL)
    sanitized = sanitize_executable_prices(
        exec_prices,
        price_source_by_symbol=chain.get("price_source_by_symbol"),
        for_orders=True,
        anchor_prices_eur=anchor_eur,
    )
    exec_prices = sanitized["executable_prices_eur"]
    snapshot = {
        "generated_at_utc": now,
        "provider": chain.get("provider") or batch.get("provider", "READONLY_YFINANCE"),
        "max_age_seconds": max_quote_age_seconds(),
        "auto_refresh_seconds": auto_refresh_interval_seconds(),
        "executable_prices_eur": exec_prices,
        "price_source_by_symbol": chain.get("price_source_by_symbol") or {},
        "champion_quote_coverage": chain.get("champion_quote_coverage"),
        "quote_merge_audit": chain.get("quote_merge_audit"),
        "t212_held_prices_eur": chain.get("t212_held_prices_eur"),
        "quotes_by_symbol": _quotes_from_batch(batch),
        "fx_runtime_gate": batch.get("fx_runtime_gate"),
        "data_quality_gate": batch.get("data_quality_gate"),
        "incident_count": batch.get("incident_count", 0),
        "valid_instrument_observations": batch.get("valid_instrument_observations", 0),
        "forward_batch_generated_at_utc": batch.get("generated_at_utc"),
        "refresh_skipped": False,
        "price_sanitization": sanitized,
    }
    cov = chain.get("champion_quote_coverage") or {}
    if not cov.get("coverage_ok"):
        snapshot["data_quality_gate"] = "PARTIAL_CHAMPION_QUOTES"
    elif sanitized.get("had_adjustments") or sanitized.get("had_blocks"):
        snapshot["data_quality_gate"] = "PARTIAL_PRICE_SANITIZED"
    snapshot["freshness"] = classify_freshness(snapshot)
    atomic_write_json(snapshot_path(root), snapshot)
    manifest = root / "paper/p16d/forward_batch_manifest.json"
    if manifest.is_file():
        try:
            existing = json.loads(manifest.read_text(encoding="utf-8"))
            existing.update(
                {
                    "executable_prices_eur": exec_prices,
                    "prices_eur": exec_prices,
                    "live_quote_snapshot_utc": now,
                }
            )
            atomic_write_json(manifest, existing)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("forward_batch_manifest update failed", exc_info=True)
            snapshot.setdefault("manifest_update_error", str(exc)[:120])
    return snapshot


def ensure_live_quotes_fresh_bounded(
    root: Path,
    *,
    force: bool = False,
    timeout_s: float = 45.0,
    owner: str = "",
) -> Dict[str, Any]:
    """Like ensure_live_quotes_fresh but never blocks longer than timeout_s."""
    from aa_refresh_guard import run_with_timeout

    if os.environ.get("AA_OFFLINE_COCKPIT_TEST", "").strip() == "1":
        return _synthetic_snapshot(root)
    cached = load_live_quote_snapshot(root)
    if not force and cached:
        fresh = classify_freshness(cached)
        cached["freshness"] = fresh
        if fresh["status"] == "FRESH" and fresh.get("calculation_allowed"):
            return cached
    result = run_with_timeout(
        lambda: refresh_live_quotes(root, force=True, owner=owner),
        timeout_s=timeout_s,
        default=None,
    )
    if result is not None:
        return result
    if cached:
        stale = dict(cached)
        stale["refresh_skipped"] = True
        stale["refresh_timed_out"] = True
        stale["freshness"] = classify_freshness(stale)
        return stale
    return refresh_live_quotes(root, force=False, owner=owner)


def _synthetic_snapshot(root: Path) -> Dict[str, Any]:
    """Deterministic quotes for CI/smoke — never used in production EXE."""
    now = _utc_now()
    prices = {sym: 70.0 + idx for idx, sym in enumerate(sorted(CHAMPION_EXECUTABLE_FILL))}
    sources = {sym: "OFFLINE_TEST_SYNTHETIC" for sym in prices}
    quotes = {
        sym: {
            "price_eur": px,
            "raw_price": px * 1.08,
            "quote_currency": "USD",
            "market_event_time_utc": now,
            "data_quality_gate": "PASS",
            "conversion_valid": True,
        }
        for sym, px in prices.items()
    }
    snap = {
        "generated_at_utc": now,
        "provider": "OFFLINE_TEST_SYNTHETIC",
        "max_age_seconds": max_quote_age_seconds(),
        "auto_refresh_seconds": auto_refresh_interval_seconds(),
        "executable_prices_eur": prices,
        "price_source_by_symbol": sources,
        "champion_quote_coverage": {
            "required_count": len(CHAMPION_EXECUTABLE_FILL),
            "covered_count": len(prices),
            "missing_symbols": [],
            "coverage_ok": True,
            "coverage_ratio": 1.0,
        },
        "quotes_by_symbol": quotes,
        "fx_runtime_gate": "FX_PASS",
        "data_quality_gate": "PASS_FOR_VALIDATED_FORWARD_PERFORMANCE",
        "incident_count": 0,
        "valid_instrument_observations": len(prices),
        "synthetic_offline_test": True,
    }
    snap["freshness"] = classify_freshness(snap)
    atomic_write_json(snapshot_path(root), snap)
    return snap


def ensure_live_quotes_fresh(root: Path, *, force: bool = False, owner: str = "") -> Dict[str, Any]:
    """Return fresh snapshot; fetch when missing or stale."""
    root = Path(root)
    if os.environ.get("AA_OFFLINE_COCKPIT_TEST", "").strip() == "1":
        return _synthetic_snapshot(root)
    if not force:
        cached = load_live_quote_snapshot(root)
        if cached:
            fresh = classify_freshness(cached)
            cached["freshness"] = fresh
            if fresh["status"] == "FRESH" and fresh.get("calculation_allowed"):
                return cached
    return refresh_live_quotes(root, force=True, owner=owner)


def merge_snapshot_into_state(state: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    """Inject live prices into cockpit state remediation block."""
    state["market_prices"] = snapshot
    fresh = snapshot.get("freshness") or classify_freshness(snapshot)
    state["market_price_freshness"] = fresh
    remediation = state.get("remediation") or {}
    if not isinstance(remediation, dict):
        remediation = {}
    batch = dict(remediation.get("forward_batch") or {})
    batch["executable_prices_eur"] = snapshot.get("executable_prices_eur") or {}
    batch["data_quality_gate"] = snapshot.get("data_quality_gate") or batch.get("data_quality_gate")
    batch["fx_runtime_gate"] = snapshot.get("fx_runtime_gate") or batch.get("fx_runtime_gate")
    batch["live_quote_snapshot_utc"] = snapshot.get("generated_at_utc")
    batch["live_quote_freshness"] = fresh.get("status")
    remediation["forward_batch"] = batch
    state["remediation"] = remediation


def price_for_symbol(snapshot: Dict[str, Any], symbol: str) -> Optional[float]:
    sym = str(symbol or "").upper()
    prices = snapshot.get("executable_prices_eur") or {}
    if sym in prices:
        try:
            return float(prices[sym])
        except (TypeError, ValueError):
            return None
    detail = (snapshot.get("quotes_by_symbol") or {}).get(sym) or {}
    px = detail.get("price_eur")
    try:
        return float(px) if px is not None else None
    except (TypeError, ValueError):
        return None


def build_pilot_gap_plan(
    *,
    prices_eur: Dict[str, float],
    broker_positions: List[Dict[str, Any]],
    targets_eur: Optional[Dict[str, float]] = None,
    root: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Gap vs P16C-style targets using live EUR prices (planning only)."""
    if targets_eur is None:
        targets_eur = load_pilot_gap_targets(root)
    held: Dict[str, float] = {}
    for pos in broker_positions or []:
        ticker = str(pos.get("ticker") or pos.get("symbol") or "").upper()
        for sym in EXECUTABLE_FILL:
            if sym in ticker or ticker.startswith(sym):
                val = pos.get("currentValue") or pos.get("market_value_eur")
                try:
                    held[sym] = float(val)
                except (TypeError, ValueError):
                    pass
                break

    rows: List[Dict[str, Any]] = []
    for sym in sorted(EXECUTABLE_FILL):
        target = float(targets_eur.get(sym, 0))
        current = float(held.get(sym, 0))
        px = float(prices_eur.get(sym, 0) or 0)
        gap = round(target - current, 2)
        shares = round(gap / px, 4) if px > 0 and gap > 0 else 0.0
        action = "HALTEN"
        if gap > 1.0:
            action = "NACHKAUF_PLANEN"
        elif gap < -1.0:
            action = "ÜBERGEWICHTET_PRÜFEN"
        rows.append(
            {
                "symbol": sym,
                "target_eur": target,
                "current_eur": round(current, 2),
                "gap_eur": gap,
                "live_price_eur": round(px, 4) if px else None,
                "estimated_shares_if_buy_gap": shares,
                "action_hint": action,
            }
        )
    return rows


def require_fresh_for_calculation(snapshot: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
    if not snapshot:
        return False, "Keine Live-Preisdaten — bitte Marktdaten aktualisieren (F5)."
    fresh = snapshot.get("freshness") or classify_freshness(snapshot)
    if not fresh.get("calculation_allowed"):
        return False, str(fresh.get("reason") or "Preise nicht aktuell genug für Berechnung.")
    return True, "OK"
