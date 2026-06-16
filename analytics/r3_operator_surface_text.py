"""Minimal operator-facing copy for R3 exec mirror — keine Trust-/Governance-Floskeln."""
from __future__ import annotations

OPERATOR_API_ENTER = "API eingeben"
OPERATOR_SYNC_WAIT = "Kurz warten"
OPERATOR_SAVED = "Gespeichert"
OPERATOR_START = "Start"
OPERATOR_RETRY = "Erneut"

_FORBIDDEN = ("vertrauenswürdig", "fail-closed", "trust gate", "bond gehalten")

_STATUS: dict[str, str] = {
    "NOT_CONFIGURED": OPERATOR_API_ENTER,
    "CONNECTION_FAILED_RETRY_AVAILABLE": OPERATOR_SYNC_WAIT,
    "RATE_LIMITED_SHOWING_CACHED_DATA": OPERATOR_SYNC_WAIT,
    "CACHED_READONLY_DATA": OPERATOR_SYNC_WAIT,
    "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA": "API prüfen",
    "NO_SYNC": OPERATOR_SYNC_WAIT,
    "STALE_SYNC": "Aktualisieren",
    "NO_CASH": OPERATOR_SYNC_WAIT,
    "UNKNOWN_STATUS": OPERATOR_SYNC_WAIT,
    "OK": "",
}


def operator_status_de(code: str | None) -> str:
    return _STATUS.get(str(code or "").strip(), OPERATOR_SYNC_WAIT)


def sanitize_operator_text(text: str, *, fallback: str = "") -> str:
    s = str(text or "").strip()
    if not s:
        return fallback
    low = s.lower()
    if any(x in low for x in _FORBIDDEN):
        return fallback or OPERATOR_SYNC_WAIT
    if s.startswith(("✗", "✓", "⚠", "⏱")):
        s = s.lstrip("✗✓⚠⏱ ").strip()
    if "trading212" in low and len(s) > 40:
        return fallback or OPERATOR_SYNC_WAIT
    if len(s) > 56:
        return fallback or OPERATOR_SYNC_WAIT
    return s


def freigabe_blocked_de(*, reason_code: str | None = None, needs_api: bool = False) -> str:
    if needs_api:
        return OPERATOR_API_ENTER
    code = str(reason_code or "").strip()
    if code == "NOT_CONFIGURED":
        return OPERATOR_API_ENTER
    return "Freigabe"


def start_hint_de(
    *,
    needs_api: bool,
    trusted: bool,
    reason_code: str | None = None,
) -> str:
    if needs_api:
        return OPERATOR_API_ENTER
    if trusted:
        return ""
    return operator_status_de(reason_code) or OPERATOR_SYNC_WAIT
