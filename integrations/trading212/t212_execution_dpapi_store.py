"""DPAPI persistence for confirmed-execution API profile."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Tuple

from integrations.trading212.t212_credentials_loader import T212Credentials
from integrations.trading212.t212_windows_dpapi_credential_store import _protect, _unprotect, dpapi_available

_REL = Path("live_pilot/manual_execution/readonly_credentials/execution_confirmed.dpapi")


def _path(root: Path) -> Path:
    return Path(root) / _REL


def save_execution_credentials(root: Path, api_key: str, api_secret: str) -> Tuple[bool, str]:
    if not dpapi_available():
        return False, "DPAPI_NOT_WINDOWS"
    payload = json.dumps(
        {"api_key": api_key.strip(), "api_secret": api_secret.strip()},
        separators=(",", ":"),
    ).encode("utf-8")
    protected = _protect(payload)
    if not protected:
        return False, "DPAPI_ENCRYPT_FAILED"
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(protected)
    return True, "DPAPI_SAVED"


def load_execution_credentials(root: Path) -> Optional[T212Credentials]:
    path = _path(root)
    if not path.is_file():
        return None
    raw = _unprotect(path.read_bytes())
    if not raw:
        return None
    try:
        doc = json.loads(raw.decode("utf-8"))
        key = str(doc.get("api_key") or "").strip()
        secret = str(doc.get("api_secret") or "").strip()
        if key and secret:
            return T212Credentials(api_key=key, api_secret=secret)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return None
    return None


def forget_execution_credentials(root: Path) -> None:
    path = _path(root)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass
