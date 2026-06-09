"""Dual-profile session credential store — monitoring and execution separated."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from integrations.trading212.t212_auth_profile_model import (
    PROFILE_CONFIRMED_EXECUTION,
    PROFILE_MONITORING_READONLY,
)
from integrations.trading212.t212_credentials_loader import T212Credentials


@dataclass
class ProfileCredentialState:
    profile: str
    connection_name: str = "Trading 212"
    mode: str = "LIVE_READ_ONLY"
    api_key: str = ""
    api_secret: str = ""
    persist_requested: bool = False


_profiles: dict[str, ProfileCredentialState] = {}


def set_profile_credentials(
    profile: str,
    *,
    api_key: str,
    api_secret: str,
    mode: str = "LIVE_READ_ONLY",
    connection_name: str = "Trading 212",
    persist_requested: bool = False,
) -> None:
    _profiles[profile] = ProfileCredentialState(
        profile=profile,
        connection_name=connection_name,
        mode=mode.upper(),
        api_key=api_key.strip(),
        api_secret=api_secret.strip(),
        persist_requested=persist_requested,
    )


def get_profile_credentials(profile: str) -> Optional[T212Credentials]:
    st = _profiles.get(profile)
    if st and st.api_key and st.api_secret:
        return T212Credentials(api_key=st.api_key, api_secret=st.api_secret)
    return None


def get_profile_state(profile: str) -> Optional[ProfileCredentialState]:
    return _profiles.get(profile)


def clear_profile(profile: str) -> None:
    _profiles.pop(profile, None)


def clear_all_profiles() -> None:
    _profiles.clear()


def monitoring_configured() -> bool:
    st = _profiles.get(PROFILE_MONITORING_READONLY)
    return bool(st and st.api_key and st.api_secret)


def execution_configured() -> bool:
    st = _profiles.get(PROFILE_CONFIRMED_EXECUTION)
    return bool(st and st.api_key and st.api_secret)
