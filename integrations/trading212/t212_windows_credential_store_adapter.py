"""Windows Credential Manager adapter — preferred persistent store on Windows."""
from __future__ import annotations

import sys
from typing import Optional, Tuple

from integrations.trading212.t212_credentials_loader import T212Credentials

_SERVICE = "ActiveAlpha_Marktanalyse_T212_Windows"
_PREFIX = "profile_"


def windows_credential_store_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _users(profile: str) -> tuple[str, str]:
    return f"{_PREFIX}{profile}_key", f"{_PREFIX}{profile}_secret"


def save_profile(profile: str, api_key: str, api_secret: str) -> Tuple[bool, str]:
    if not windows_credential_store_available():
        return False, "WINDOWS_CREDENTIAL_STORE_UNAVAILABLE"
    try:
        import keyring

        uk, us = _users(profile)
        keyring.set_password(_SERVICE, uk, api_key.strip())
        keyring.set_password(_SERVICE, us, api_secret.strip())
        return True, "WINDOWS_CREDENTIAL_STORE_SAVED"
    except Exception as exc:
        return False, f"WINDOWS_STORE_FAILED:{type(exc).__name__}"


def load_profile(profile: str) -> Optional[T212Credentials]:
    if not windows_credential_store_available():
        return None
    try:
        import keyring

        uk, us = _users(profile)
        k = keyring.get_password(_SERVICE, uk)
        s = keyring.get_password(_SERVICE, us)
        if k and s:
            return T212Credentials(api_key=k, api_secret=s)
    except Exception:
        return None
    return None


def clear_profile(profile: str) -> None:
    if not windows_credential_store_available():
        return
    try:
        import keyring

        uk, us = _users(profile)
        try:
            keyring.delete_password(_SERVICE, uk)
        except Exception:
            pass
        try:
            keyring.delete_password(_SERVICE, us)
        except Exception:
            pass
    except Exception:
        pass


def storage_status() -> str:
    if windows_credential_store_available():
        return "PASS_SECURE_WINDOWS_STORE_AVAILABLE"
    return "PASS_SESSION_ONLY_FAILSAFE_ENFORCED"
