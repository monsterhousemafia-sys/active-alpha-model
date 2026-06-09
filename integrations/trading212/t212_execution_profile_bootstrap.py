"""Execution API profile — restore from disk or mirror monitoring key."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION
from integrations.trading212.t212_dual_profile_credential_store import (
    execution_configured,
    set_profile_credentials,
)


def restore_execution_profile_from_disk(root: Path) -> Dict[str, Any]:
    from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials
    from integrations.trading212.t212_execution_dpapi_store import load_execution_credentials

    if execution_configured():
        return {"restored": False, "reason": "SESSION_ALREADY_HAS_EXECUTION"}

    creds = load_execution_credentials(root) or load_profile_credentials(PROFILE_CONFIRMED_EXECUTION)
    if not creds or not creds.configured:
        return {"restored": False, "reason": "NO_STORED_EXECUTION_CREDENTIALS"}

    set_profile_credentials(
        PROFILE_CONFIRMED_EXECUTION,
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        persist_requested=True,
    )
    return {"restored": True, "source": "disk"}


def mirror_monitoring_to_execution(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Use the same T212 key for orders when pilot live is on (single-key setup)."""
    root = Path(root)
    if execution_configured():
        return {"mirrored": False, "reason": "execution_already_configured"}

    from execution.confirmed_live.pilot_live_trading_policy import is_pilot_live_trading_enabled

    if not is_pilot_live_trading_enabled(root):
        return {"mirrored": False, "reason": "pilot_live_off"}

    from integrations.trading212.t212_credentials_loader import load_credentials

    creds = load_credentials(root)
    if not creds or not creds.configured:
        return {"mirrored": False, "reason": "no_monitoring_credentials"}

    set_profile_credentials(
        PROFILE_CONFIRMED_EXECUTION,
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        mode="LIVE_READ_ONLY",
        persist_requested=persist,
    )
    if persist:
        from integrations.trading212.t212_dual_profile_secure_store import save_profile_credentials
        from integrations.trading212.t212_execution_dpapi_store import save_execution_credentials

        save_profile_credentials(PROFILE_CONFIRMED_EXECUTION, creds.api_key, creds.api_secret)
        save_execution_credentials(root, creds.api_key, creds.api_secret)

    return {"mirrored": True, "source": "monitoring_key"}


def ensure_execution_profile_ready(root: Path) -> Dict[str, Any]:
    restored = restore_execution_profile_from_disk(root)
    if restored.get("restored"):
        return restored
    return mirror_monitoring_to_execution(root, persist=True)
