"""Confirmed core live mode — user enablement required."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

ACTIVATION_PHRASE = "AKTIVIERE BESTÄTIGUNGSPFLICHTIGEN CORE-LIVE-PILOTEN MIT MAXIMAL 500 EUR"
POLICY_VERSION = "P16H_CORE_LIVE_V1"

CORE_LIVE_MAX_CAPITAL_EUR = 500.0
# 0 = no artificial cash reserve (T212 broker rules still apply)
CORE_LIVE_MIN_RESERVE_EUR = 0.0
CORE_LIVE_MAX_DEPLOYABLE_EUR = CORE_LIVE_MAX_CAPITAL_EUR
# 0 = no per-order notional cap (pilot capital cap remains elsewhere)
CORE_LIVE_MAX_SINGLE_POSITION_EUR = 0.0
CORE_LIVE_MAX_OPEN_POSITIONS = 6
# 0 = unlimited (enforced in order_daily_limit); kept for metadata/legacy displays
CORE_LIVE_MAX_ORDERS_PER_DAY = 0
CORE_LIVE_MAX_DAILY_LOSS_EUR = 15.0
CORE_LIVE_MAX_DRAWDOWN_EUR = 35.0

_DASH_VARIANTS = ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212")


def activation_phrase_matches(user: str) -> bool:
    """Match activation phrase (Unicode-normalized, tolerant on dash variants)."""
    import unicodedata

    def norm(text: str) -> str:
        s = unicodedata.normalize("NFC", str(text or "").strip())
        for ch in _DASH_VARIANTS:
            s = s.replace(ch, "-")
        return " ".join(s.split())

    return norm(user) == norm(ACTIVATION_PHRASE)


def _path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/core_live_mode_state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_mode(root: Path) -> Dict[str, Any]:
    path = _path(root)
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "LOCKED", "policy_version": POLICY_VERSION}


def mode_status(root: Path) -> str:
    return str(load_mode(root).get("status", "LOCKED"))


def is_active(root: Path) -> bool:
    return mode_status(root) == "ACTIVE_CONFIRM_BEFORE_SUBMIT_ONLY"


def can_submit_orders(root: Path) -> bool:
    from execution.confirmed_live.global_kill_switch import is_active as kill_active

    if kill_active(root):
        return False
    return is_active(root)


def activate_by_user(root: Path, *, phrase: str, risk_ack: bool) -> Dict[str, Any]:
    from integrations.trading212.t212_execution_profile_activation_guard import guard_activation_attempt

    guard = guard_activation_attempt(
        phrase_valid=activation_phrase_matches(phrase),
        risk_ack=risk_ack,
        root=root,
    )
    if not guard.get("ok"):
        return guard
    state = {
        "status": "ACTIVE_CONFIRM_BEFORE_SUBMIT_ONLY",
        "policy_version": POLICY_VERSION,
        "activated_at_utc": _utc_now(),
        "limits": {
            "max_capital_eur": CORE_LIVE_MAX_CAPITAL_EUR,
            "min_reserve_eur": CORE_LIVE_MIN_RESERVE_EUR,
            "max_single_position_eur": CORE_LIVE_MAX_SINGLE_POSITION_EUR,
            "max_orders_per_day": CORE_LIVE_MAX_ORDERS_PER_DAY,
            "max_daily_loss_eur": CORE_LIVE_MAX_DAILY_LOSS_EUR,
            "max_drawdown_eur": CORE_LIVE_MAX_DRAWDOWN_EUR,
        },
    }
    atomic_write_json(_path(root), state)
    return {"ok": True, "state": state}


def pause_by_user(root: Path) -> Dict[str, Any]:
    state = {**load_mode(root), "status": "PAUSED_BY_USER", "paused_at_utc": _utc_now()}
    atomic_write_json(_path(root), state)
    return state


def pause_fail_closed(root: Path, *, reason: str) -> Dict[str, Any]:
    state = {**load_mode(root), "status": "PAUSED_FAIL_CLOSED", "pause_reason": reason, "paused_at_utc": _utc_now()}
    atomic_write_json(_path(root), state)
    return state
