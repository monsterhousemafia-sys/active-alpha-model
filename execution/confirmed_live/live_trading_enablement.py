"""Live trading enablement — no pilot phrase / 500 EUR gate."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

_ACK_REL = Path("control/live_trading_enabled.json")
_LEGACY_ACK = Path("control/pilot_live_trading_ack.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ack_path(root: Path) -> Path:
    return Path(root) / _ACK_REL


def load_live_trading_ack(root: Path) -> Dict[str, Any]:
    path = ack_path(root)
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                return doc
        except (json.JSONDecodeError, OSError):
            pass
    legacy = Path(root) / _LEGACY_ACK
    if legacy.is_file():
        try:
            leg = json.loads(legacy.read_text(encoding="utf-8"))
            if isinstance(leg, dict) and leg.get("enabled"):
                return {
                    "enabled": True,
                    "mode": "MANUAL_CONFIRM_BEFORE_SUBMIT",
                    "migrated_from": "pilot_live_trading_ack",
                }
        except (json.JSONDecodeError, OSError):
            pass
    return {"enabled": False}


def is_live_trading_enabled(root: Path) -> bool:
    doc = load_live_trading_ack(root)
    return bool(doc.get("enabled"))


def live_submission_allowed(root: Path) -> bool:
    """Orders allowed when live trading is on and review mode is off."""
    if not is_live_trading_enabled(root):
        return False
    from execution.confirmed_live.p17_review_mode_guard import review_mode_active

    return not review_mode_active()


def ensure_live_trading_enabled(root: Path, *, changed_by: str = "system") -> Dict[str, Any]:
    """Idempotent — enable live trading without activation phrase."""
    if is_live_trading_enabled(root):
        return {"ok": True, "already": True}
    return enable_live_trading(root, risk_ack=True, changed_by=changed_by)


def enable_live_trading(
    root: Path,
    *,
    risk_ack: bool = True,
    changed_by: str = "user",
    phrase: str = "",
    **_kwargs: Any,
) -> Dict[str, Any]:
    _ = phrase  # legacy pilot phrase — ignored
    if not risk_ack:
        return {"ok": False, "error": "RISK_ACK_REQUIRED"}

    from execution.confirmed_live.p17_review_mode_preferences import set_review_mode_enabled

    set_review_mode_enabled(root, enabled=False, changed_by=changed_by)

    doc = {
        "enabled": True,
        "mode": "MANUAL_CONFIRM_BEFORE_SUBMIT",
        "auto_execute_enabled": False,
        "enabled_at_utc": _utc_now(),
        "changed_by": changed_by,
        "governance_note": "Live-Trading (Paper-Workflow); Champion unverändert; keine Echtgeld-Auto-Promotion.",
    }
    atomic_write_json(ack_path(root), doc)
    return {"ok": True, "ack": doc}


def disable_live_trading(root: Path, *, changed_by: str = "user") -> Dict[str, Any]:
    from execution.confirmed_live.p17_review_mode_preferences import set_review_mode_enabled

    set_review_mode_enabled(root, enabled=True, changed_by=changed_by)
    atomic_write_json(
        ack_path(root),
        {"enabled": False, "disabled_at_utc": _utc_now(), "changed_by": changed_by},
    )
    return {"ok": True}


# Backward-compatible aliases for existing imports
load_pilot_trading_ack = load_live_trading_ack
is_pilot_live_trading_enabled = is_live_trading_enabled
enable_pilot_live_trading = enable_live_trading
disable_pilot_live_trading = disable_live_trading


def activation_phrase() -> str:
    return ""
