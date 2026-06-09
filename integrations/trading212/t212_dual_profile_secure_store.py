"""Secure store for dual T212 profiles."""
from __future__ import annotations

from typing import Optional, Tuple

from integrations.trading212.t212_auth_profile_model import (
    PROFILE_CONFIRMED_EXECUTION,
    PROFILE_MONITORING_READONLY,
)
from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_secure_credential_store import secure_store_available

_SERVICE = "ActiveAlpha_Marktanalyse_T212"


def _users(profile: str) -> tuple[str, str]:
    return f"{profile}_key", f"{profile}_secret"


def save_profile_credentials(profile: str, api_key: str, api_secret: str) -> Tuple[bool, str]:
    if not secure_store_available():
        return False, "SICHERE DAUERHAFTE SPEICHERUNG NICHT VERFÜGBAR — NUR DIESE SITZUNG"
    try:
        import keyring

        uk, us = _users(profile)
        keyring.set_password(_SERVICE, uk, api_key.strip())
        keyring.set_password(_SERVICE, us, api_secret.strip())
        return True, "CREDENTIALS_SICHER_GESPEICHERT"
    except Exception as exc:
        return False, f"SPEICHERUNG_FEHLGESCHLAGEN: {type(exc).__name__}"


def load_profile_credentials(profile: str) -> Optional[T212Credentials]:
    if not secure_store_available():
        return None
    try:
        import keyring

        uk, us = _users(profile)
        key = keyring.get_password(_SERVICE, uk) or ""
        secret = keyring.get_password(_SERVICE, us) or ""
        if key and secret:
            return T212Credentials(api_key=key, api_secret=secret)
    except Exception:
        return None
    return None


def forget_profile_credentials(profile: str) -> None:
    if not secure_store_available():
        return
    try:
        import keyring

        uk, us = _users(profile)
        keyring.delete_password(_SERVICE, uk)
        keyring.delete_password(_SERVICE, us)
    except Exception:
        pass


def forget_all_profile_credentials() -> None:
    forget_profile_credentials(PROFILE_MONITORING_READONLY)
    forget_profile_credentials(PROFILE_CONFIRMED_EXECUTION)
