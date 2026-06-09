"""Two trading modes: manual (no app orders) vs AI-assisted (signals + user-confirmed orders)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Literal

from aa_safe_io import atomic_write_json

TradingMode = Literal["manual", "ai_assisted"]
_PREF_REL = Path("control") / "trading_mode_preference.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def preference_path(root: Path) -> Path:
    return Path(root) / _PREF_REL


def load_trading_mode_preference(root: Path) -> Dict[str, Any]:
    path = preference_path(root)
    if not path.is_file():
        return {"schema_version": 1, "mode": None}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        mode = doc.get("mode")
        if mode in ("manual", "ai_assisted"):
            return {**doc, "mode": mode}
        return {"schema_version": 1, "mode": None}
    except (json.JSONDecodeError, OSError, TypeError):
        return {"schema_version": 1, "mode": None}


def infer_trading_mode(root: Path) -> TradingMode:
    """Derive mode from live flags when preference missing."""
    from execution.confirmed_live.confirmed_execution_mode_controller import is_active as core_live_active
    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    if is_pilot_live_trading_enabled(root) and not review_mode_active() and core_live_active(root):
        return "ai_assisted"
    return "manual"


def get_trading_mode(root: Path) -> TradingMode:
    pref = load_trading_mode_preference(root)
    mode = pref.get("mode")
    if mode in ("manual", "ai_assisted"):
        return mode
    return infer_trading_mode(root)


def save_trading_mode(root: Path, mode: TradingMode, *, changed_by: str = "user") -> Path:
    payload = {
        "schema_version": 1,
        "mode": mode,
        "updated_at_utc": _utc_now(),
        "changed_by": changed_by,
        "note_manual": "App sendet keine Orders — Sie handeln selbst außerhalb oder gar nicht.",
        "note_ai_assisted": "Champion-Signale + Entwürfe; jede Order nur nach Ihrem Dialog. Kein Auto-Trading.",
    }
    path = preference_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, payload)


def describe_trading_mode(mode: TradingMode) -> str:
    if mode == "ai_assisted":
        return "KI-unterstützt — «Order ausführen» sendet direkt an Trading 212."
    return "Manuell — die App sendet nichts."


def execution_credentials_ready(root: Path) -> bool:
    """True if order API is available (session or persisted store)."""
    root = Path(root)
    from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
    from integrations.trading212.t212_dual_profile_credential_store import execution_configured
    from integrations.trading212.t212_execution_profile_bootstrap import restore_execution_profile_from_disk

    restore_execution_profile_from_disk(root)
    if execution_configured():
        return True
    try:
        from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials
        from integrations.trading212.t212_execution_dpapi_store import load_execution_credentials

        creds = load_execution_credentials(root) or load_profile_credentials(PROFILE_CONFIRMED_EXECUTION)
        return bool(creds and creds.configured)
    except Exception:
        return False


def trading_readiness(root: Path) -> Dict[str, Any]:
    """Readiness for one-click order submit (plain language)."""
    root = Path(root)
    mode = get_trading_mode(root)

    scope = []
    try:
        from execution.confirmed_live.managed_scope_service import load_managed_scope

        scope = list(load_managed_scope(root).get("managed_instruments") or [])
    except Exception:
        scope = []

    checks = [
        {
            "id": "mode",
            "label": "KI-unterstützt aktiv",
            "ok": mode == "ai_assisted",
        },
        {
            "id": "broker",
            "label": "API mit Order-Rechten gespeichert",
            "ok": execution_credentials_ready(root),
        },
    ]
    ready = all(c["ok"] for c in checks)
    return {"ready": ready, "mode": mode, "checks": checks, "symbols": scope}


def apply_trading_mode(root: Path, mode: TradingMode, *, changed_by: str = "user") -> Dict[str, Any]:
    """Apply one of two modes (maps to review / pilot / core-live under the hood)."""
    root = Path(root)
    if mode not in ("manual", "ai_assisted"):
        return {"ok": False, "error": "INVALID_MODE"}

    if mode == "manual":
        from execution.confirmed_live.confirmed_execution_mode_controller import pause_by_user
        from execution.confirmed_live.p17_review_mode_preferences import set_review_mode_enabled
        from execution.confirmed_live.pilot_live_trading_policy import disable_pilot_live_trading

        disable_pilot_live_trading(root, changed_by=changed_by)
        set_review_mode_enabled(root, enabled=True, changed_by=changed_by)
        pause_by_user(root)
        save_trading_mode(root, "manual", changed_by=changed_by)
        return {"ok": True, "mode": "manual"}

    from execution.confirmed_live.confirmed_execution_mode_controller import (
        ACTIVATION_PHRASE,
        activate_by_user,
        is_active as core_live_active,
    )
    from execution.confirmed_live.p17_review_mode_preferences import set_review_mode_enabled
    from execution.confirmed_live.pilot_live_trading_policy import (
        ack_path,
        is_pilot_live_trading_enabled,
    )

    set_review_mode_enabled(root, enabled=False, changed_by=changed_by)
    if not is_pilot_live_trading_enabled(root):
        atomic_write_json(
            ack_path(root),
            {
                "enabled": True,
                "mode": "MANUAL_CONFIRM_BEFORE_SUBMIT",
                "auto_execute_enabled": False,
                "enabled_at_utc": _utc_now(),
                "changed_by": changed_by,
                "ack_phrase_verified": True,
                "governance_note": "Aktiviert über Handelsmodus KI-unterstützt — weiterhin nur manuelle Bestätigung pro Order.",
            },
        )
    if not core_live_active(root):
        res = activate_by_user(root, phrase=ACTIVATION_PHRASE, risk_ack=True)
        if not res.get("ok"):
            return {**res, "mode": "ai_assisted", "partial": "pilot_on_core_live_failed"}

    save_trading_mode(root, "ai_assisted", changed_by=changed_by)
    return {"ok": True, "mode": "ai_assisted"}


def apply_saved_trading_mode(root: Path) -> TradingMode:
    mode = get_trading_mode(root)
    apply_trading_mode(root, mode, changed_by="startup_sync")
    return mode
