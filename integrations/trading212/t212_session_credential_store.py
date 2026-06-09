"""In-memory session-only Trading 212 credentials — never persisted to disk."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from integrations.trading212.t212_credentials_loader import T212Credentials


@dataclass
class SessionCredentialState:
    connection_name: str = "Trading 212"
    mode: str = "LIVE_READ_ONLY"  # DEMO_READ_ONLY | LIVE_READ_ONLY
    api_key: str = ""
    api_secret: str = ""
    persist_requested: bool = False
    secure_store_available: bool = False


_session: Optional[SessionCredentialState] = None


def get_session_state() -> Optional[SessionCredentialState]:
    return _session


def set_session_credentials(
    *,
    api_key: str,
    api_secret: str,
    mode: str = "LIVE_READ_ONLY",
    connection_name: str = "Trading 212",
    persist_requested: bool = False,
    secure_store_available: bool = False,
) -> None:
    global _session
    _session = SessionCredentialState(
        connection_name=connection_name,
        mode=mode.upper(),
        api_key=api_key.strip(),
        api_secret=api_secret.strip(),
        persist_requested=persist_requested,
        secure_store_available=secure_store_available,
    )


def get_session_credentials() -> Optional[T212Credentials]:
    if _session and _session.api_key and _session.api_secret:
        return T212Credentials(api_key=_session.api_key, api_secret=_session.api_secret)
    return None


def clear_session_credentials() -> None:
    global _session
    _session = None


def session_configured() -> bool:
    return bool(_session and _session.api_key and _session.api_secret)
