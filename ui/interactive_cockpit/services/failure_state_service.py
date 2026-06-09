"""Failure-state classification for professional UX — fail-closed, user-visible."""
from __future__ import annotations

from typing import Any, Dict, List


def classify_system_state(state: Dict[str, Any]) -> Dict[str, Any]:
    broker = state.get("broker") or {}
    p17 = state.get("p17") or {}
    p16h = state.get("p16h") or {}
    cash = state.get("cash") or {}

    issues: List[Dict[str, str]] = []
    status = broker.get("status", "NOT_CONFIGURED")
    last_error = broker.get("last_error")

    if status in ("NOT_CONFIGURED", "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI"):
        issues.append(
            {
                "code": "BROKER_NOT_CONFIGURED",
                "severity": "INFO",
                "title": "Trading 212 Read-only nicht eingerichtet",
                "user_action": "Optional: API-Key unter „Trading 212 Verbindung & Profile“ eingeben.",
                "recovery": "Setup überspringbar — Paper und Planung bleiben verfügbar.",
            }
        )
    elif last_error:
        low = str(last_error).lower()
        if "429" in low or "rate" in low:
            issues.append(
                {
                    "code": "BROKER_RATE_LIMIT",
                    "severity": "WARNING",
                    "title": "Broker-Rate-Limit erreicht",
                    "user_action": "Warten und später erneut synchronisieren.",
                    "recovery": "Keine Orders — nur Read-only-Sync pausiert.",
                }
            )
        elif "timeout" in low or "timed out" in low:
            issues.append(
                {
                    "code": "BROKER_TIMEOUT",
                    "severity": "WARNING",
                    "title": "Broker antwortet nicht rechtzeitig",
                    "user_action": "Internetverbindung prüfen; „Aktualisieren“ erneut versuchen.",
                    "recovery": "Fail-closed: keine Live-Orders; Planung weiter möglich.",
                }
            )
        else:
            issues.append(
                {
                    "code": "BROKER_CONNECTION_ERROR",
                    "severity": "ERROR",
                    "title": "Read-only-Verbindung fehlgeschlagen",
                    "user_action": f"Details: {last_error[:120]}",
                    "recovery": "Credentials prüfen oder Session-only neu eingeben.",
                }
            )
    elif status == "CONNECTED_READONLY_OK":
        if not cash.get("readonly_broker_cash_verified"):
            issues.append(
                {
                    "code": "CASH_NOT_VERIFIED",
                    "severity": "WARNING",
                    "title": "Cash noch nicht verifiziert",
                    "user_action": "Read-only-Synchronisation ausführen.",
                    "recovery": "Order-Review bleibt gesperrt bis Cash bestätigt.",
                }
            )

    if p16h.get("kill_switch", {}).get("active"):
        issues.append(
            {
                "code": "KILL_SWITCH_ACTIVE",
                "severity": "CRITICAL",
                "title": "Kill Switch aktiv",
                "user_action": "Unter „Risiko, Limits & Kill Switch“ prüfen.",
                "recovery": "Neue Submissions blockiert bis Freigabe durch Nutzer.",
            }
        )

    if p17.get("review_mode_no_live_submission", True):
        issues.append(
            {
                "code": "P17_REVIEW_MODE",
                "severity": "INFO",
                "title": "Interne Reviewversion — keine Live-Orderübermittlung",
                "user_action": "Confirm-Workflow nur als Demonstration/Fixture.",
                "recovery": "Echtgeldsubmission in späterer freigegebener Phase.",
            }
        )

    mp_fresh = state.get("market_price_freshness") or {}
    mp_status = mp_fresh.get("status")
    if mp_status == "STALE":
        issues.append(
            {
                "code": "MARKET_PRICES_STALE",
                "severity": "WARNING",
                "title": "Marktpreise veraltet",
                "user_action": "F5 drücken oder „Live-Preise aktualisieren“ — Berechnungen sind gesperrt.",
                "recovery": mp_fresh.get("reason", "Live-Refresh erforderlich."),
            }
        )
    elif mp_status in ("MISSING", "ERROR", "DEGRADED"):
        issues.append(
            {
                "code": "MARKET_PRICES_UNAVAILABLE",
                "severity": "ERROR" if mp_status == "MISSING" else "WARNING",
                "title": "Live-Marktpreise nicht verfügbar",
                "user_action": "Internet prüfen und Marktdaten-Tab öffnen.",
                "recovery": mp_fresh.get("reason", "Keine aktuellen Kurse für Planung."),
            }
        )

    lr = state.get("learning_readiness") or {}
    if lr.get("error") or lr.get("capture_errors"):
        issues.append(
            {
                "code": "LEARNING_CAPTURE_ERROR",
                "severity": "WARNING",
                "title": "Lern-Archiv: Erfassung eingeschränkt",
                "user_action": str(lr.get("error") or lr.get("capture_errors"))[:160],
                "recovery": "Internet prüfen und erneut aktualisieren — kein Auto-Training.",
            }
        )
    elif lr.get("learning_collection_active") and not lr.get("last_eod_date"):
        issues.append(
            {
                "code": "LEARNING_EOD_PENDING",
                "severity": "INFO",
                "title": "Lern-Archiv: erster Tagesabschluss ausstehend",
                "user_action": "App einmal mit Internet starten — EOD wird automatisch erfasst.",
                "recovery": "Kein Auto-Training — nur Beobachtungs-Ledger.",
            }
        )

    refresh_err = state.get("refresh_error")
    if refresh_err:
        issues.append(
            {
                "code": "REFRESH_DEGRADED",
                "severity": "WARNING",
                "title": "Aktualisierung eingeschränkt",
                "user_action": str(refresh_err)[:160],
                "recovery": "Erneut F5 — bei anhaltendem Fehler App neu starten.",
            }
        )

    for sub_err in state.get("subsystem_errors") or []:
        if not isinstance(sub_err, dict):
            continue
        code = str(sub_err.get("code") or "SUBSYSTEM_ERROR")
        if code in {i.get("code") for i in issues}:
            continue
        issues.append(
            {
                "code": code,
                "severity": "WARNING",
                "title": f"Teilsystem: {sub_err.get('subsystem', 'runtime')}",
                "user_action": str(sub_err.get("message", ""))[:160],
                "recovery": "Fail-closed — Funktion eingeschränkt, keine Auto-Orders.",
            }
        )

    overall = "OK"
    if any(i["severity"] == "CRITICAL" for i in issues):
        overall = "CRITICAL"
    elif any(i["severity"] == "ERROR" for i in issues):
        overall = "ERROR"
    elif any(i["severity"] == "WARNING" for i in issues):
        overall = "WARNING"
    elif issues:
        overall = "INFO"

    return {
        "overall": overall,
        "issues": issues,
        "broker_online": status == "CONNECTED_READONLY_OK" and not last_error,
        "empty_state_message": _empty_state_message(status, issues),
    }


def _empty_state_message(status: str, issues: List[Dict[str, str]]) -> str:
    if status in ("NOT_CONFIGURED", "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI"):
        return (
            "Noch keine Trading-212-Read-only-Verbindung.\n"
            "Sie können Paper-Simulation und Planung sofort nutzen.\n"
            "Realdaten erscheinen nach optionalem API-Setup."
        )
    if any(i["code"] == "BROKER_CONNECTION_ERROR" for i in issues):
        return "Verbindung unterbrochen — Read-only-Daten nicht aktuell. Fail-closed aktiv."
    return "System bereit."
