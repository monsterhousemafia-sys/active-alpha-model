"""Live-Cockpit-Daten für Preview Command Center — ersetzt Dashboard-Anzeige im Browser."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional


def _traffic_class(traffic: str) -> str:
    t = str(traffic or "").upper()
    if t == "GRUEN":
        return "ok"
    if t == "ROT":
        return "fail"
    return "warn"


def preview_actions() -> List[Dict[str, Any]]:
    """Operator-Aktionen im Hub (Orders nur über Order-Desk / GUI-Bestätigung)."""
    return [
        {
            "id": "refresh-snap",
            "label_de": "Konto aktualisieren",
            "detail_de": "T212-Cache + Snapshot ohne Orders",
            "tier": "primary",
        },
        {
            "id": "daily-mark",
            "label_de": "① Täglicher Markt",
            "detail_de": "Sync + Sektoren + Zähler (kein ML)",
            "tier": "primary",
        },
        {
            "id": "signal",
            "label_de": "③ Signal aktualisieren",
            "detail_de": "Profil daily_alpha_h1 / EOD",
            "tier": "secondary",
        },
        {
            "id": "plan-orders",
            "label_de": "Orders planen",
            "detail_de": "Champion-Portfolio berechnen — noch nicht senden",
            "tier": "secondary",
        },
        {
            "id": "order-desk",
            "label_de": "Order-Desk öffnen",
            "detail_de": "Qt-Fenster für Rebalance & T212-Bestätigung",
            "tier": "accent",
        },
        {
            "id": "trading-day",
            "label_de": "Trading-Day",
            "detail_de": "Tages-Orchestrator (Mark + Evidence)",
            "tier": "secondary",
        },
        {
            "id": "learn",
            "label_de": "Lernen",
            "detail_de": "Post-Order-Learning + Report",
            "tier": "secondary",
        },
        {
            "id": "circle",
            "label_de": "Kreis-Score",
            "detail_de": "Closed-Loop neu berechnen",
            "tier": "secondary",
        },
        {
            "id": "refresh-preview",
            "label_de": "Preview neu",
            "detail_de": "Alle 21 Checks + HTML",
            "tier": "secondary",
        },
        {
            "id": "share-preview",
            "label_de": "Preview teilen",
            "detail_de": "Join-Link für andere Rechner (zentrale Leistung)",
            "tier": "accent",
        },
    ]


def build_preview_cockpit(root: Path, *, snap: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    snap = dict(snap or {})
    if not snap:
        try:
            from ui.live_trading_dashboard.gui_preview_harness import _load_snap_for_gui

            snap = _load_snap_for_gui(root, None, allow_refresh=False)
        except Exception:
            snap = {}

    broker = snap.get("broker") or {}
    status = snap.get("rebalance_status") or {}
    guard = snap.get("guard") or {}
    learning = snap.get("public_learning") or {}
    dw = snap.get("day_warnings") or {}
    po = snap.get("portfolio_orders") or {}
    deferred = snap.get("deferred") or {}
    readiness = snap.get("trading_readiness") or {}
    sector = snap.get("sector_status") or {}

    cash = broker.get("cash_eur")
    try:
        cash_fmt = f"{float(cash):,.2f} €" if cash is not None else "—"
    except (TypeError, ValueError):
        cash_fmt = "—"

    traffic = str(snap.get("traffic") or "—")
    stale = {}
    try:
        from analytics.preview_freshness import preview_stale_status

        stale = preview_stale_status(root)
    except Exception:
        stale = {}
    return {
        "schema_version": 1,
        "preview_stale": bool(stale.get("stale")),
        "preview_stale_de": str(stale.get("reason_de") or ""),
        "traffic": traffic,
        "traffic_class": _traffic_class(traffic),
        "today_action_de": str(snap.get("today_action_de") or "—")[:300],
        "cash_eur": cash,
        "cash_de": cash_fmt,
        "n_positions": int(snap.get("n_positions") or 0),
        "live_enabled": bool(snap.get("live_enabled")),
        "orders_allowed": bool(readiness.get("orders_allowed")),
        "rebalance": {
            "is_due": bool(status.get("is_due")),
            "days_remaining": status.get("days_remaining"),
            "recorded_days": status.get("recorded_trading_days_since_rebalance"),
            "every_days": status.get("rebalance_every_trading_days"),
            "summary_de": str(status.get("summary_de") or "—")[:240],
            "recommendation": str(status.get("recommendation") or "—"),
        },
        "learning": {
            "grade": str(learning.get("grade") or "—"),
            "score": learning.get("score"),
            "stage_de": str(learning.get("stage_de") or "—")[:120],
        },
        "warnings": {
            "headline_de": str(dw.get("headline_de") or "—")[:200],
            "critical_count": int(dw.get("critical_count") or 0),
            "must_resolve": bool(dw.get("must_resolve_before_trading")),
        },
        "portfolio_orders": {
            "summary_de": str(po.get("summary_de") or "—")[:300],
            "order_count": int(po.get("order_count") or 0),
            "has_orders": bool(po.get("has_orders")),
            "lines_de": list(po.get("lines_de") or [])[:12],
        },
        "deferred_de": str(deferred.get("status_de") or "—")[:160],
        "sector_de": str(sector.get("summary_de") or "—")[:160],
        "guard_ok": bool(guard.get("champion_ok")) and bool(guard.get("signals_ok")),
        "actions": preview_actions(),
        "hub_note_de": "Orders an T212 nur im Order-Desk mit GUI-Bestätigung.",
    }
