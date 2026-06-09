"""Pre-submit readiness — permissions, cash, US session, broker stock-buy gate."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_GATE_REL = Path("live_pilot/manual_execution/readonly_real_account_state/t212_stock_buy_gate.json")


@dataclass(frozen=True)
class T212OrderReadiness:
    ok: bool
    api_execute_configured: bool
    api_execute_scope_proven: bool
    us_session_open: bool
    cash_eur: Optional[float]
    cash_source: str
    blockers: List[str]
    warnings: List[str]
    status_de: str
    session: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "api_execute_configured": self.api_execute_configured,
            "api_execute_scope_proven": self.api_execute_scope_proven,
            "us_session_open": self.us_session_open,
            "cash_eur": self.cash_eur,
            "cash_source": self.cash_source,
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "status_de": self.status_de,
            "session": dict(self.session),
        }


def _gate_path(root: Path) -> Path:
    return Path(root) / _GATE_REL


def load_stock_buy_gate(root: Path) -> Dict[str, Any]:
    path = _gate_path(root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def record_stock_buy_attempt(
    root: Path,
    *,
    ok: bool,
    error: str = "",
) -> Dict[str, Any]:
    """Track consecutive broker insufficient responses (misleading when session closed)."""
    doc = load_stock_buy_gate(root)
    if ok:
        doc = {
            "consecutive_insufficient": 0,
            "last_ok_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
    else:
        low = str(error or "").lower()
        session_open, _sess = us_orders_allowed_now()
        if "insufficient-free-for-stocks-buy" in low or "insufficient funds" in low:
            if not session_open:
                doc["last_outside_session_insufficient_utc"] = (
                    datetime.now(timezone.utc).replace(microsecond=0).isoformat()
                )
            else:
                n = int(doc.get("consecutive_insufficient") or 0) + 1
                doc["consecutive_insufficient"] = n
                doc["last_insufficient_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            doc["last_error_snippet"] = str(error)[:240]
        else:
            doc["last_other_error_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            doc["last_error_snippet"] = str(error)[:240]
    path = _gate_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def broker_stock_buy_likely_blocked(root: Path, *, threshold: int = 2) -> bool:
    return int(load_stock_buy_gate(root).get("consecutive_insufficient") or 0) >= threshold


def reset_stock_buy_gate(root: Path, *, reason: str = "user_reset") -> Dict[str, Any]:
    """Clear consecutive T212 «insufficient» streak after manual test in T212 app."""
    doc = {
        "consecutive_insufficient": 0,
        "reset_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "reset_reason": reason,
    }
    prev = load_stock_buy_gate(root)
    if prev.get("api_execute_scope_proven"):
        doc["api_execute_scope_proven"] = True
        doc["api_execute_scope_proven_utc"] = prev.get("api_execute_scope_proven_utc")
    path = _gate_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return doc


def us_orders_allowed_now() -> tuple[bool, Dict[str, Any]]:
    """Return (allowed, session_info). Override for controlled diagnostics only."""
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    sess = us_equity_regular_session_open_now()
    if os.environ.get("AA_ALLOW_US_ORDERS_OUTSIDE_SESSION", "").strip() == "1":
        return True, {**sess, "override": True}
    return bool(sess.get("open")), sess


def assess_order_readiness(
    root: Path,
    *,
    free_cash_eur: float | None = None,
    require_min_cash_eur: float = 1.0,
) -> T212OrderReadiness:
    root = Path(root)
    blockers: List[str] = []
    warnings: List[str] = []

    from integrations.trading212.t212_dual_profile_credential_store import execution_configured

    api_ok = execution_configured()
    if not api_ok:
        blockers.append("EXECUTION_API_NOT_CONFIGURED")

    scope_proven = bool(load_stock_buy_gate(root).get("api_execute_scope_proven"))
    if api_ok and not scope_proven:
        warnings.append("API_EXECUTE_SCOPE_NOT_YET_PROVEN_BY_POST")

    session_allowed, sess = us_orders_allowed_now()
    if not session_allowed:
        blockers.append("US_REGULAR_SESSION_CLOSED")

    cash = free_cash_eur
    cash_source = "caller"
    if cash is None:
        try:
            from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

            broker = sync_readonly_account(root, force=False)
            cash = broker.cash_eur
            cash_source = "readonly_sync"
        except Exception:
            cash = None
            warnings.append("CASH_SYNC_FAILED")

    if cash is None:
        blockers.append("CASH_NOT_VERIFIED")
    elif float(cash) < require_min_cash_eur:
        blockers.append("CASH_BELOW_MINIMUM")

    if broker_stock_buy_likely_blocked(root):
        if session_allowed:
            warnings.append("BROKER_STOCK_BUY_INSUFFICIENT_STREAK")
        else:
            warnings.append("INSUFFICIENT_OUTSIDE_US_SESSION_NOT_COUNTED")

    from execution.confirmed_live.trading_mode_policy import get_trading_mode

    if get_trading_mode(root) != "ai_assisted":
        blockers.append("TRADING_MODE_NOT_AI_ASSISTED")

    from execution.confirmed_live.confirmed_execution_mode_controller import can_submit_orders

    if not can_submit_orders(root):
        blockers.append("CORE_LIVE_MODE_NOT_ACTIVE")

    from execution.confirmed_live.order_daily_limit import can_submit_more_orders_today

    allowed_day, day_reason = can_submit_more_orders_today(root)
    if not allowed_day:
        blockers.append(day_reason)

    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from execution.confirmed_live.pilot_live_trading_policy import live_submission_allowed

    if review_mode_active() and not live_submission_allowed(root):
        blockers.append("REVIEW_MODE_BLOCKS_LIVE_ORDERS")

    ok = len(blockers) == 0
    status_de = _format_status_de(
        ok=ok,
        blockers=blockers,
        warnings=warnings,
        cash=cash,
        sess=sess,
        api_ok=api_ok,
    )
    return T212OrderReadiness(
        ok=ok,
        api_execute_configured=api_ok,
        api_execute_scope_proven=scope_proven,
        us_session_open=bool(sess.get("open")),
        cash_eur=float(cash) if cash is not None else None,
        cash_source=cash_source,
        blockers=blockers,
        warnings=warnings,
        status_de=status_de,
        session=sess,
    )


def assess_deferred_enqueue_readiness(
    root: Path,
    *,
    free_cash_eur: float | None = None,
) -> T212OrderReadiness:
    """Like assess_order_readiness but allows enqueue outside US regular session."""
    base = assess_order_readiness(root, free_cash_eur=free_cash_eur)
    blockers = [
        b
        for b in base.blockers
        if b not in ("US_REGULAR_SESSION_CLOSED", "BROKER_STOCK_BUY_BLOCKED_STREAK")
    ]
    ok = len(blockers) == 0
    status_de = base.status_de
    if ok and not base.us_session_open:
        from integrations.trading212.t212_exchange_session import format_next_open_de

        status_de = (
            f"Vormerkung möglich | API OK | US-Session zu | nächste Eröffnung {format_next_open_de()}"
        )
    elif "US_REGULAR_SESSION_CLOSED" in base.blockers and blockers:
        status_de = assess_order_readiness(root, free_cash_eur=free_cash_eur).status_de
    return T212OrderReadiness(
        ok=ok,
        api_execute_configured=base.api_execute_configured,
        api_execute_scope_proven=base.api_execute_scope_proven,
        us_session_open=base.us_session_open,
        cash_eur=base.cash_eur,
        cash_source=base.cash_source,
        blockers=blockers,
        warnings=base.warnings,
        status_de=status_de,
        session=base.session,
    )


def mark_api_execute_scope_proven(root: Path) -> None:
    doc = load_stock_buy_gate(root)
    doc["api_execute_scope_proven"] = True
    doc["api_execute_scope_proven_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    path = _gate_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _format_status_de(
    *,
    ok: bool,
    blockers: List[str],
    warnings: List[str],
    cash: Optional[float],
    sess: Dict[str, Any],
    api_ok: bool,
) -> str:
    if ok:
        cash_s = f"{float(cash):.2f}" if cash is not None else "?"
        return f"Order bereit | API OK | US-Session offen | frei {cash_s} EUR"
    lines: List[str] = []
    if "US_REGULAR_SESSION_CLOSED" in blockers:
        lines.append(str(sess.get("reason_de") or "US-Regular-Session geschlossen."))
        lines.append(
            "Hinweis: Ausserhalb US-Regular meldet T212 oft «Insufficient funds» — "
            "obwohl API «Orders ausführen» hat. Ihr Konto: keine Extended-Hours."
        )
        lines.append(
            "Alternative: In der App «Order ausführen» zum Vormerken oder "
            "«Automatisch bei US-Eröffnung» aktivieren."
        )
    if "EXECUTION_API_NOT_CONFIGURED" in blockers:
        lines.append("API mit Order-Rechten in der App speichern.")
    elif api_ok:
        lines.append("API-Key mit Order-Rechten ist geladen (Berechtigungen OK).")
    if "BROKER_STOCK_BUY_BLOCKED_STREAK" in blockers:
        lines.append(
            "Mehrere Kaeufe wurden von T212 abgelehnt — einmal INTC in der T212-App testen "
            "(Invest-Konto, US-Handelszeit). Bei Erfolg dort: Support/T212-Kontotyp prüfen."
        )
    if "CASH_NOT_VERIFIED" in blockers:
        lines.append("Kontostand nicht verifiziert — «Aktualisieren».")
    if "TRADING_MODE_NOT_AI_ASSISTED" in blockers:
        lines.append("Handelsmodus «KI-unterstützt» einschalten.")
    if warnings and not lines:
        lines.append("Warnungen: " + ", ".join(warnings))
    return "\n".join(lines) if lines else "Order derzeit nicht möglich."
