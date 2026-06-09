"""R3 technische Order-Vorbereitung — T212, Live-Kurse, Order-Zeilen."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_safe_io import atomic_write_json

_EVIDENCE_REL = Path("evidence/r3_freigabe_latest.json")

FREIGABE_GOVERNANCE_NOTE_DE = (
    "Ehrlich: Gewinn „vollständig erwirtschaften“ ohne jeden Klick geht nur mit externer "
    "Freigabe für auto_execute_real_money. Aktuell: System bereitet 24/7 alles vor — du "
    "bestätigst das Paket einmal in R3, danach läuft der Kreislauf weiter."
)


def freigabe_governance_note_de() -> str:
    """Ehrliche Governance-Einordnung — kein Auto-Echtgeld ohne externe Freigabe."""
    return FREIGABE_GOVERNANCE_NOTE_DE


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def package_ready(root: Path, *, refresh_orders: bool = False) -> Dict[str, Any]:
    """Paket technisch ausführbar: aktiv + BUY-Zeilen + Notional > 0."""
    root = Path(root)
    if refresh_orders:
        try:
            from analytics.r3_stock_orders import refresh_stock_order_evidence

            refresh_stock_order_evidence(root, persist=True)
        except Exception:
            pass
    orders = _load_json(root / "evidence/r3_stock_orders_latest.json")
    pkg = orders.get("initial_package") or {}
    buys = [r for r in (orders.get("stocks") or []) if str(r.get("side") or "").upper() == "BUY"]
    notional = round(sum(float(r.get("notional_eur") or 0) for r in buys), 2)
    t212_ok = True
    trust_msg = ""
    try:
        from integrations.trading212.t212_trust_gate import assess_t212_trust_from_root

        trust = assess_t212_trust_from_root(root, persist=False)
        t212_ok = bool(trust.get("orders_allowed"))
        trust_msg = str(trust.get("message_de") or "")
    except Exception:
        t212_ok = False
        trust_msg = "T212 Trust Gate nicht erreichbar"

    ready = bool(pkg.get("active")) and bool(buys) and notional > 0 and t212_ok
    headline = (
        f"Paket bereit — {notional:.0f} € · {len(buys)} Zeilen"
        if ready
        else (trust_msg if not t212_ok else "Kein aktives Paket")
    )
    return {
        "ready": ready,
        "package_ready": ready,
        "freigabe_ready": ready,
        "initial_package": pkg,
        "buy_count": len(buys),
        "notional_eur": notional,
        "headline_de": headline,
        "governance_note_de": freigabe_governance_note_de(),
    }


def refresh_order_surface(root: Path) -> Dict[str, Any]:
    root = Path(root)
    from analytics.r3_trading_functions import build_r3_trading_functions
    from analytics.r3_stock_orders import refresh_stock_order_evidence

    build_r3_trading_functions(root, persist=True)
    return refresh_stock_order_evidence(root)


def _persist_prep(root: Path, *, prep_steps: List[Dict[str, Any]], status: Dict[str, Any]) -> Dict[str, Any]:
    ready = bool(status.get("ready"))
    doc: Dict[str, Any] = {
        "schema_version": 3,
        "updated_at_utc": _utc_now(),
        "package_ready": ready,
        "freigabe_ready": ready,
        "headline_de": status.get("headline_de"),
        "governance_note_de": status.get("governance_note_de") or freigabe_governance_note_de(),
        "buy_count": status.get("buy_count") or 0,
        "notional_eur": status.get("notional_eur") or 0,
        "initial_package": status.get("initial_package") or {},
        "prep_steps": prep_steps,
        "evidence_ref": str(_EVIDENCE_REL).replace("\\", "/"),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def auto_prepare_freigabe_for_desktop(root: Path) -> Dict[str, Any]:
    """T212-Bond, Live-Kurse, Order-Oberfläche — vor Submit/desktop."""
    root = Path(root)
    prep_steps: List[Dict[str, Any]] = []

    try:
        from analytics.r3_t212_api_bond import sync_r3_t212_api_bond

        bond = sync_r3_t212_api_bond(root, force=False, persist=True)
        prep_steps.append(
            {
                "step": "t212_bond",
                "ok": bool(bond.get("bonded")) and bool(bond.get("connected")),
                "headline_de": str(bond.get("confirmation_de") or "")[:120],
            }
        )
    except Exception as exc:
        prep_steps.append({"step": "t212_bond", "ok": False, "error": str(exc)[:80]})

    try:
        from analytics.live_trading_operations import sync_broker_and_quotes

        sync = sync_broker_and_quotes(root, force_quotes=False, force_sync=False)
        snap = sync.get("quote_snapshot") or {}
        prep_steps.append(
            {
                "step": "live_quotes",
                "ok": bool(snap.get("executable_prices_eur") or snap.get("quotes_by_symbol")),
            }
        )
    except Exception as exc:
        prep_steps.append({"step": "live_quotes", "ok": False, "error": str(exc)[:80]})

    try:
        refresh_order_surface(root)
        prep_steps.append({"step": "order_surface", "ok": True})
    except Exception as exc:
        prep_steps.append({"step": "order_surface", "ok": False, "error": str(exc)[:80]})

    status = package_ready(root, refresh_orders=True)
    doc = _persist_prep(root, prep_steps=prep_steps, status=status)
    doc["auto_prepared"] = True
    doc["auto_bootstrap"] = prep_steps
    return doc


def prepare_freigabe(root: Path, *, warm_32b: bool = True) -> Dict[str, Any]:
    """CLI — gleicher technischer Pfad wie /desktop (warm_32b ignoriert)."""
    del warm_32b
    return auto_prepare_freigabe_for_desktop(root)


def refresh_freigabe_evidence(root: Path) -> Dict[str, Any]:
    root = Path(root)
    existing = _load_json(root / _EVIDENCE_REL)
    status = package_ready(root, refresh_orders=True)
    return _persist_prep(root, prep_steps=list(existing.get("prep_steps") or []), status=status)


def load_freigabe(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _EVIDENCE_REL)
    return doc if doc else refresh_freigabe_evidence(root)
