"""Secure persistent credential store — OS keyring when available, else session-only."""
from __future__ import annotations

from typing import Optional, Tuple

from integrations.trading212.t212_credentials_loader import T212Credentials

_SERVICE = "ActiveAlpha_Marktanalyse_T212"
_USER = "readonly_api_credentials"


def secure_store_available() -> bool:
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def save_credentials(api_key: str, api_secret: str) -> Tuple[bool, str]:
    if not secure_store_available():
        return False, "SICHERE DAUERHAFTE SPEICHERUNG NICHT VERFÜGBAR — NUR DIESE SITZUNG"
    try:
        import keyring

        keyring.set_password(_SERVICE, f"{_USER}_key", api_key.strip())
        keyring.set_password(_SERVICE, f"{_USER}_secret", api_secret.strip())
        return True, "CREDENTIALS_SICHER_GESPEICHERT"
    except Exception as exc:
        return False, f"SPEICHERUNG_FEHLGESCHLAGEN: {type(exc).__name__}"


def load_secure_credentials() -> Optional[T212Credentials]:
    if not secure_store_available():
        return None
    try:
        import keyring

        key = keyring.get_password(_SERVICE, f"{_USER}_key") or ""
        secret = keyring.get_password(_SERVICE, f"{_USER}_secret") or ""
        if key and secret:
            return T212Credentials(api_key=key, api_secret=secret)
    except Exception:
        return None
    return None


def forget_credentials() -> None:
    if not secure_store_available():
        return
    try:
        import keyring

        keyring.delete_password(_SERVICE, f"{_USER}_key")
        keyring.delete_password(_SERVICE, f"{_USER}_secret")
    except Exception:
        pass
