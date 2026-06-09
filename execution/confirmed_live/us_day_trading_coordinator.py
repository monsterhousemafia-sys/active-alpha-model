"""US day-trading playbook — session, reeval, deferred queue, readiness (one view)."""
from __future__ import annotations

import json
from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/us_day_trading.json")
_EVIDENCE_REL = Path("evidence/us_day_trading_playbook_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": True,
        "execution_window_mode": "full_session",
        "open_burst_minutes": 45,
        "pause_new_buys_minutes_before_close": 20,
        "quote_refresh_seconds_open": 60,
        "quote_refresh_seconds_preopen": 180,
        "full_refresh_minutes_open": 5,
        "full_refresh_minutes_closed": 30,
        "reeval_minutes_open_early": 3,
        "reeval_minutes_open": 5,
        "suggest_enqueue_on_high_urgency": True,
    }


def load_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    return policy_section(Path(root), "playbook")


def _session_timing() -> Dict[str, Any]:
    from zoneinfo import ZoneInfo

    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    session_start = time(9, 30)
    session_end = time(16, 0)
    ny = ZoneInfo("America/New_York")
    sess = us_equity_regular_session_open_now()
    now_ny = datetime.now(timezone.utc).astimezone(ny)
    t = now_ny.time()
    mins_since_open = 0
    mins_until_close = 0
    if sess.get("open"):
        open_m = session_start.hour * 60 + session_start.minute
        now_m = t.hour * 60 + t.minute
        close_m = session_end.hour * 60 + session_end.minute
        mins_since_open = max(0, now_m - open_m)
        mins_until_close = max(0, close_m - now_m)
    phase = str(sess.get("phase") or "CLOSED")
    if sess.get("open"):
        if mins_since_open <= 45:
            detail = "OPEN_EARLY"
        elif mins_until_close <= 30:
            detail = "OPEN_LATE"
        else:
            detail = "OPEN_MID"
    else:
        detail = phase
    return {
        **sess,
        "detail_phase": detail,
        "minutes_since_open": mins_since_open,
        "minutes_until_close": mins_until_close,
        "now_ny_hm": now_ny.strftime("%H:%M") + " NY",
    }


def effective_quote_refresh_seconds(root: Path) -> int:
    from analytics.pilot_day_trading_policy import effective_quote_refresh_seconds as _s

    return _s(root)


def effective_full_refresh_ms(root: Path) -> int:
    from analytics.pilot_day_trading_policy import effective_full_refresh_ms as _ms

    return _ms(root)


def is_deferred_execution_allowed(root: Path) -> bool:
    """When auto-armed intents may fire (full US regular vs open burst only)."""
    from integrations.trading212.t212_exchange_session import (
        is_within_us_open_execution_window,
        us_equity_regular_session_open_now,
    )

    pol = load_policy(root)
    if not us_equity_regular_session_open_now().get("open"):
        return False
    mode = str(pol.get("execution_window_mode") or "full_session")
    if mode == "full_session":
        return True
    return is_within_us_open_execution_window(
        minutes_after_open=int(pol.get("open_burst_minutes") or 45),
    )


def _pause_new_buys(timing: Dict[str, Any], pol: Dict[str, Any]) -> bool:
    if not timing.get("open"):
        return False
    return int(timing.get("minutes_until_close") or 0) <= int(
        pol.get("pause_new_buys_minutes_before_close") or 20
    )


def build_day_trading_playbook(
    root: Path,
    *,
    broker: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    champion_guard: Optional[Dict[str, Any]] = None,
    reevaluation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    root = Path(root)
    pol = load_policy(root)
    if not pol.get("enabled"):
        return {"status": "DISABLED", "summary_de": "US-Session-Playbook aus."}

    timing = _session_timing()
    guard = champion_guard or {}
    from execution.confirmed_live.us_equity_deferred_intents import load_deferred_summary, load_policy as load_def_pol

    deferred = load_deferred_summary(root)
    def_pol = load_def_pol(root)

    readiness: Dict[str, Any] = {}
    if broker:
        from integrations.trading212.t212_order_readiness import assess_order_readiness

        r = assess_order_readiness(root, free_cash_eur=broker.get("cash_eur"))
        readiness = r.as_dict()

    if reevaluation is None and broker:
        from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion

        reevaluation = evaluate_live_portfolio_vs_champion(
            root,
            broker=broker,
            plan=plan,
            quote_snapshot=quote_snapshot,
            champion_guard=guard,
        )

    reeval = reevaluation or {}
    primary = (plan or {}).get("primary_action") or {}
    primary_sym = str(primary.get("symbol") or "").upper()
    pending_n = int(deferred.get("pending_count") or 0)
    armed = bool(def_pol.get("user_armed_auto_open_execution"))
    pause_buys = _pause_new_buys(timing, pol)

    next_action, steps = _derive_playbook(
        timing=timing,
        readiness=readiness,
        reeval=reeval,
        guard=guard,
        deferred=deferred,
        armed=armed,
        pause_buys=pause_buys,
        primary_sym=primary_sym,
        plan=plan,
        pol=pol,
        root=root,
    )

    summary = _playbook_summary(timing, next_action, steps, reeval, pending_n, armed)

    target_eur = float(primary.get("target_eur") or 0)
    if target_eur > 0 and next_action in ("EXECUTE_NOW", "ENQUEUE_OPEN"):
        from integrations.trading212.t212_us_cost_model import format_cost_step_de

        cost_line = format_cost_step_de(root, notional_eur=target_eur)
        if cost_line:
            steps.append(cost_line)

    plan_safety: Dict[str, Any] = {}
    if plan:
        from analytics.pilot_day_trading_reliability import assess_plan_trade_safety

        plan_safety = assess_plan_trade_safety(root, plan)

    doc: Dict[str, Any] = {
        "status": "OK",
        "generated_at_utc": _utc_now(),
        "plan_safety": plan_safety,
        "policy": {
            "execution_window_mode": pol.get("execution_window_mode"),
            "armed": armed,
        },
        "session": timing,
        "readiness_ok": bool(readiness.get("ok")),
        "readiness": readiness,
        "reevaluation_urgency": reeval.get("urgency"),
        "trade_required": bool(reeval.get("trade_required")),
        "deferred_pending": pending_n,
        "primary_symbol": primary_sym,
        "pause_new_buys": pause_buys,
        "deferred_execution_allowed": is_deferred_execution_allowed(root),
        "next_action": next_action,
        "playbook_steps": steps,
        "summary_de": summary,
        "headline_de": _headline(timing, next_action),
    }
    atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _headline(timing: Dict[str, Any], action: str) -> str:
    phase = timing.get("detail_phase") or timing.get("phase")
    labels = {
        "OPEN_EARLY": "US-Eröffnung — aktives Fenster",
        "OPEN_MID": "US-Session läuft",
        "OPEN_LATE": "US-Schlussphase — Vorsicht",
        "PREOPEN": "Vor US-Eröffnung",
        "CLOSED": "US-Session zu",
    }
    base = labels.get(str(phase), "US-Markt")
    action_de = {
        "EXECUTE_NOW": "→ Jetzt Order",
        "EXECUTE_DEFERRED": "→ Vorgemerkte ausführen",
        "ENQUEUE_OPEN": "→ Für Eröffnung vormerken",
        "REFRESH": "→ Daten aktualisieren",
        "WAIT": "→ Abwarten",
        "NO_TRADE": "→ Kein Trade",
    }.get(action, "")
    return f"{base} {action_de}".strip()


def _derive_playbook(
    *,
    timing: Dict[str, Any],
    readiness: Dict[str, Any],
    reeval: Dict[str, Any],
    guard: Dict[str, Any],
    deferred: Dict[str, Any],
    armed: bool,
    pause_buys: bool,
    primary_sym: str,
    plan: Optional[Dict[str, Any]] = None,
    pol: Dict[str, Any],
    root: Optional[Path] = None,
) -> tuple[str, List[str]]:
    steps: List[str] = []
    if not guard.get("champion_ok"):
        steps.append("Champion-Guard blockiert — keine Orders.")
        return "NO_TRADE", steps
    if not guard.get("signals_ok"):
        steps.append("Signale veraltet — nur beobachten.")
        return "NO_TRADE", steps

    if reeval.get("urgency") == "STALE_QUOTES" and timing.get("open"):
        steps.append("Live-Kurse refreshen (F5 / «Aktualisieren»).")
        return "REFRESH", steps

    if plan and root is not None:
        from analytics.pilot_day_trading_reliability import assess_plan_trade_safety

        safety = assess_plan_trade_safety(root, plan)
        for w in safety.get("warnings_de") or []:
            steps.append(f"Hinweis: {w}")
        if safety.get("blocks_execute"):
            for err in safety.get("errors_de") or []:
                steps.append(f"Blockiert: {err}")
            return "NO_TRADE", steps

    if not readiness.get("ok"):
        blockers = readiness.get("blockers") or []
        if "US_REGULAR_SESSION_CLOSED" in blockers and primary_sym:
            n_alloc = len((plan or {}).get("allocations") or [])
            if n_alloc > 1:
                steps.append(
                    f"Session zu — «Order ausführen» vormerkt alle {n_alloc} Modell-Allokationen für Eröffnung."
                )
            else:
                steps.append(f"Session zu — «Order ausführen» vormerkt {primary_sym} für Eröffnung.")
            if pol.get("suggest_enqueue_on_high_urgency") and reeval.get("trade_required"):
                steps.append("Portfolio-Check empfiehlt Handlung — Vormerkung sinnvoll.")
            return "ENQUEUE_OPEN", steps
        steps.append("Order-Bereitschaft: " + (readiness.get("status_de") or "nicht bereit")[:200])
        return "WAIT", steps

    pending = int(deferred.get("pending_count") or 0)
    if timing.get("open") and pending and armed:
        steps.append(f"{pending} vorgemerkte Order(s) — Auto-Ausführung aktiv.")
        return "EXECUTE_DEFERRED", steps

    if timing.get("open") and reeval.get("trade_required") and not pause_buys:
        top = (reeval.get("recommended_actions") or [{}])[0]
        sym = top.get("symbol") or primary_sym
        steps.append(f"Portfolio-Check {reeval.get('urgency')}: {sym} priorisieren.")
        steps.append("«Order ausführen» sendet Limit an T212 (US-Regular).")
        return "EXECUTE_NOW", steps

    if timing.get("open") and pause_buys:
        steps.append("Schlussphase — keine neuen Käufe; nur reduzieren/halten.")
        return "WAIT", steps

    if not timing.get("open") and reeval.get("trade_required") and primary_sym:
        steps.append("Außerhalb US-Session: Vormerkung + optional Auto bei Eröffnung.")
        return "ENQUEUE_OPEN", steps

    if timing.get("open"):
        steps.append("Kein dringender Trade laut Modell — Portfolio beobachten.")
        return "WAIT", steps

    steps.append("Nächste US-Regular-Session abwarten.")
    return "WAIT", steps


def _playbook_summary(
    timing: Dict[str, Any],
    action: str,
    steps: List[str],
    reeval: Dict[str, Any],
    pending: int,
    armed: bool,
) -> str:
    parts = [
        _headline(timing, action),
        f"NY {timing.get('now_ny_hm', '—')}",
    ]
    if timing.get("open"):
        parts.append(
            f"+{timing.get('minutes_since_open')} Min / −{timing.get('minutes_until_close')} Min bis Schluss"
        )
    if reeval.get("summary_de"):
        parts.append(str(reeval["summary_de"])[:220])
    if pending:
        parts.append(f"Vorgemerkt: {pending} ({'Auto AN' if armed else 'Auto AUS'}).")
    if steps:
        parts.append(steps[0])
    return " · ".join(parts)


def maybe_enqueue_from_playbook(
    root: Path,
    playbook: Dict[str, Any],
    *,
    plan: Dict[str, Any],
    limit_price_eur: float,
    quote_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Enqueue all plan allocations when playbook says ENQUEUE_OPEN and policy allows."""
    root = Path(root)
    pol = load_policy(root)
    if not pol.get("suggest_enqueue_on_high_urgency"):
        return {"ok": False, "skipped": "SUGGEST_OFF"}
    if playbook.get("next_action") != "ENQUEUE_OPEN":
        return {"ok": False, "skipped": "ACTION_NOT_ENQUEUE"}
    from execution.confirmed_live.us_equity_deferred_intents import (
        enqueue_all_allocations_from_plan,
        enqueue_intent,
        load_policy as load_def_pol,
    )

    if load_def_pol(root).get("batch_execute_all_allocations", True):
        return enqueue_all_allocations_from_plan(
            root,
            plan=plan,
            quote_snapshot=quote_snapshot,
            source="DAY_TRADING_PLAYBOOK",
            primary_limit_price_eur=limit_price_eur,
        )
    return enqueue_intent(
        root, plan=plan, limit_price_eur=limit_price_eur, source="DAY_TRADING_PLAYBOOK"
    )


def write_playbook_evidence(root: Path, doc: Dict[str, Any]) -> Path:
    return atomic_write_json(Path(root) / _EVIDENCE_REL, doc)
