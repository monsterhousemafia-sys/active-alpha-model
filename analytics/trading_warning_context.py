"""Off-hours / Wochenende — Warnungen für Kreis „Entscheiden“ abschwächen."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

# Nur Markt-/Timing-Warnungen — echte Blocker (Broker, Champion) bleiben kritisch.
_OFF_HOURS_DAMPEN_CODES = frozenset(
    {
        "PARTIAL_QUOTE_COVERAGE",
        "STALE_QUOTES",
        "UNDER_INVESTED_CASH",
        "REBALANCE_DUE_NO_POSITIONS",
    }
)


def us_trading_action_window_open() -> bool:
    try:
        from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

        return bool(us_equity_regular_session_open_now().get("open"))
    except Exception:
        return False


def dampen_off_hours_warnings(
    warnings: List[Dict[str, Any]],
    *,
    us_open: bool | None = None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Außerhalb US-Regular: erwartbare Warnungen von critical → warn.
    Evolution/Kreis „Entscheiden“ wird am Wochenende nicht fälschlich rot.
    """
    if us_open is None:
        us_open = us_trading_action_window_open()
    if us_open:
        return warnings, []

    out: List[Dict[str, Any]] = []
    dampened: List[str] = []
    for w in warnings:
        row = deepcopy(w)
        code = str(row.get("code") or "")
        if code in _OFF_HOURS_DAMPEN_CODES and row.get("severity") == "critical":
            row["severity"] = "warn"
            row["dampened_off_hours"] = True
            detail = str(row.get("detail_de") or "")
            if "Wochenende" not in detail and "US-Regular" not in detail:
                row["detail_de"] = f"{detail} · US zu — Montag/Session".strip(" ·")[:300]
            dampened.append(code)
        out.append(row)
    return out, dampened


def finalize_warning_counts(
    warnings: List[Dict[str, Any]],
    *,
    dampened_codes: List[str] | None = None,
    us_open: bool | None = None,
) -> Dict[str, Any]:
    sev_rank = {"critical": 3, "warn": 2, "info": 1}
    top = max((sev_rank.get(w["severity"], 0) for w in warnings), default=0)
    severity = "ok" if top == 0 else ("critical" if top >= 3 else "warn")
    critical = [w for w in warnings if w["severity"] == "critical"]
    warn_only = [w for w in warnings if w["severity"] == "warn"]
    raw_critical_n = int(len(critical) + len(dampened_codes or []))

    us_session = us_open if us_open is not None else us_trading_action_window_open()

    if critical:
        headline = f"⚠ {len(critical)} kritisch — vor US-Handel beheben: {critical[0]['title_de']}"
    elif dampened_codes and not us_session:
        headline = (
            f"Hinweis: {len(dampened_codes)} Punkt(e) für Montag/US-Session "
            f"({dampened_codes[0].replace('_', ' ')})"
        )
    elif warn_only:
        headline = f"Hinweis: {len(warn_only)} Punkt(e) — {warn_only[0]['title_de']}"
    else:
        headline = "Keine kritischen Warnungen — Routine möglich"

    return {
        "severity": severity,
        "critical_count": len(critical),
        "critical_count_raw": raw_critical_n,
        "warn_count": len(warn_only),
        "headline_de": headline,
        "must_resolve_before_trading": len(critical) > 0,
        "dampened_off_hours": list(dampened_codes or []),
        "us_session_open": us_session,
    }
