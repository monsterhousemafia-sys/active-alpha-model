"""Execution profile activation guard — blocked during P17 review."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from execution.confirmed_live.p17_review_mode_guard import review_mode_active

_ACTIVATION_ERROR_MESSAGES = {
    "P17_REVIEW_MODE_CORE_LIVE_ACTIVATION_LOCKED": (
        "Core-Live ist gesperrt, solange der Review Mode AN ist.\n\n"
        "Schritt: Risiko → Live-Trading aktivieren "
        "(schaltet Review Mode automatisch AUS)."
    ),
    "RISK_ACK_REQUIRED": "Bitte die Risiko-Checkbox ankreuzen.",
    "AKTIVIERUNGSPHRASE_UNGUELTIG": (
        "Aktivierungsphrase stimmt nicht exakt überein.\n"
        "Tipp: Button «Korrekte Phrase einfügen» unter dem Eingabefeld nutzen."
    ),
}


def _live_trading_allows_activation(root: Path | None) -> bool:
    if root is None:
        return False
    try:
        from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

        return is_pilot_live_trading_enabled(Path(root))
    except ImportError:
        return False


def can_enable_execution_profile(root: Path | None = None) -> bool:
    if root is not None and _live_trading_allows_activation(root):
        return True
    return not review_mode_active()


def can_activate_core_live(root: Path | None = None) -> bool:
    if root is not None and _live_trading_allows_activation(root):
        return True
    return not review_mode_active()


def activation_block_reason(root: Path | None = None) -> str | None:
    if review_mode_active() and not (root is not None and _live_trading_allows_activation(root)):
        return "P17_REVIEW_MODE_CORE_LIVE_ACTIVATION_LOCKED"
    return None


def _fail(error: str, **extra: Any) -> Dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "message": _ACTIVATION_ERROR_MESSAGES.get(error, error),
        **extra,
    }


def guard_activation_attempt(*, phrase_valid: bool, risk_ack: bool, root: Path | None = None) -> Dict[str, Any]:
    if review_mode_active() and not (root is not None and _live_trading_allows_activation(root)):
        return _fail("P17_REVIEW_MODE_CORE_LIVE_ACTIVATION_LOCKED")
    if not risk_ack:
        return _fail("RISK_ACK_REQUIRED")
    if not phrase_valid:
        return _fail("AKTIVIERUNGSPHRASE_UNGUELTIG")
    return {"ok": True}


def describe_core_live_prerequisites(root: Path) -> Dict[str, Any]:
    """Human-readable checklist for the Risiko panel."""
    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    live_on = is_pilot_live_trading_enabled(root)
    review = review_mode_active()
    ready = (live_on or not review) and can_activate_core_live(root)
    hints: list[str] = []
    if review and not live_on:
        hints.append("① Live-Trading aktivieren (Review Mode → AUS)")
    if live_on and review:
        hints.append("① Review Mode ist noch AN — Risiko → Live-Trading deaktivieren/aktivieren")
    hints.append("② Risiko-Checkbox bestätigen")
    hints.append("③ Core-Live nur bei Bedarf (optional)")
    return {
        "live_trading": live_on,
        "pilot_live": live_on,
        "review_mode": review,
        "can_activate": ready,
        "hints": hints,
    }


_pilot_allows_activation = _live_trading_allows_activation
