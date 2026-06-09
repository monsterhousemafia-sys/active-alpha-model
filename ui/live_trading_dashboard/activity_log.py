"""Dashboard activity log — visible trace of automatic and user-triggered work."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ui.interactive_cockpit.services.activity_audit_service import load_recent_activities, log_activity


def _local_time_hm() -> str:
    return datetime.now().astimezone().strftime("%H:%M:%S")


def log_dashboard_activity(
    root: Path,
    *,
    category: str,
    action: str,
    result: str,
    status: str = "ERFOLGREICH",
    source: str = "AUTO",
    details: Optional[Dict[str, Any]] = None,
    user_action_required: bool = False,
) -> Dict[str, Any]:
    return log_activity(
        root,
        category=category,
        action=action,
        result=result,
        status=status,
        source=source,
        details=details,
        user_action_required=user_action_required,
    )


def format_activity_line(entry: Dict[str, Any]) -> str:
    ts = str(entry.get("timestamp_utc") or "")
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        clock = dt.astimezone().strftime("%H:%M:%S")
    except ValueError:
        clock = _local_time_hm()
    src = str(entry.get("source") or "AUTO")
    cat = str(entry.get("category") or "")
    act = str(entry.get("action") or "")
    res = str(entry.get("result") or "")
    st = str(entry.get("status") or "")
    mark = {"ERFOLGREICH": "✓", "FEHLGESCHLAGEN": "✗", "LAUFEND": "…", "INFO": "·"}.get(st, "·")
    return f"{clock} {mark} [{src}] {cat}: {act} — {res}"[:240]


def summarize_refresh(snap: Dict[str, Any]) -> str:
    broker = snap.get("broker") or {}
    status = snap.get("rebalance_status") or {}
    qc = snap.get("quote_coverage") or {}
    dw = snap.get("day_warnings") or {}
    cash = broker.get("cash_eur")
    cash_s = f"{float(cash):,.2f} €" if cash is not None else "Konto —"
    cov = qc.get("quote_coverage_label_de") or qc.get("coverage_ratio") or "—"
    rec = status.get("recommendation") or "—"
    traffic = snap.get("traffic") or "—"
    crit = int(dw.get("critical_count") or 0)
    parts = [f"Traffic {traffic}", f"T212 {cash_s}", f"Kurse {cov}", f"Plan {rec}"]
    if crit:
        parts.append(f"{crit} kritisch")
    if snap.get("error"):
        parts.append(str(snap.get("error"))[:80])
    return " · ".join(parts)


def load_dashboard_lines(root: Path, *, limit: int = 40) -> List[str]:
    entries = load_recent_activities(root, limit=limit)
    dashboard_cats = {
        "Active Alpha",
        "Dashboard",
        "Auto-Refresh",
        "Evolution",
        "EOD",
        "Lernen",
        "System",
        "T212",
        "Signal",
        "Rebalance",
        "Markt",
        "Champion",
    }
    lines: List[str] = []
    for entry in entries:
        if entry.get("category") in dashboard_cats or entry.get("source") in (
            "AUTO",
            "CURSOR",
            "USER",
            "SYSTEM",
        ):
            lines.append(format_activity_line(entry))
    return lines[:limit]


def planned_auto_actions_de(root: Path, snap: Dict[str, Any]) -> List[str]:
    """Human-readable next automatic steps."""
    import json
    from pathlib import Path as P

    try:
        from analytics.trading_day_cockpit import load_trading_day_cockpit_doc

        doc = load_trading_day_cockpit_doc(root)
        if doc:
            lines = list(doc.get("cockpit_lines_de") or [])
            nxt = doc.get("next_step_de")
            if nxt:
                lines.append(f"→ {nxt}")
            if lines:
                return lines
    except Exception:
        pass

    from analytics.pilot_day_trading_policy import effective_full_refresh_ms, effective_quote_refresh_seconds

    lines: List[str] = []
    full_min = max(1, int(effective_full_refresh_ms(root) / 60_000))
    quote_s = effective_quote_refresh_seconds(root)
    lines.append(f"Auto-Refresh alle {full_min} Min (Kurse alle {quote_s} s in US-Session)")
    lines.append("EOD-Signal-Check alle 15 Min (ab 22:15 CET)")
    st = snap.get("rebalance_status") or {}
    if st.get("is_due"):
        lines.append("Nächster sinnvoller Schritt: ② Rebalance (nach GUI-Bestätigung)")
    elif str(st.get("recommendation") or "") == "MARK_TO_MARKET_ONLY":
        lines.append("Nächster Schritt: ① Täglicher Markt oder warten auf Rebalance-Zähler")
    dw = snap.get("day_warnings") or {}
    for w in (dw.get("warnings") or [])[:3]:
        if w.get("severity") in ("critical", "warn"):
            lines.append(f"Achtung: {w.get('title_de')}")
    return lines
