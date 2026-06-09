"""Windows DPAPI encrypted local credential blob — survives app restart without keyring."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from integrations.trading212.t212_credentials_loader import T212Credentials

_REL_PATH = Path("live_pilot/manual_execution/readonly_credentials/monitoring_readonly.dpapi")


def _cred_path(root: Path) -> Path:
    return Path(root) / _REL_PATH


def dpapi_available() -> bool:
    return sys.platform == "win32"


def _protect(data: bytes) -> Optional[bytes]:
    if not dpapi_available():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        def _blob(raw: bytes) -> DATA_BLOB:
            buf = ctypes.create_string_buffer(raw, len(raw))
            return DATA_BLOB(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))

        in_blob = _blob(data)
        out_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    except (AttributeError, OSError, ValueError):
        return None


def _unprotect(blob: bytes) -> Optional[bytes]:
    if not dpapi_available():
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        in_blob = DATA_BLOB(
            len(blob),
            ctypes.cast(ctypes.create_string_buffer(blob, len(blob)), ctypes.POINTER(ctypes.c_byte)),
        )
        out_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    except (AttributeError, OSError, ValueError):
        return None


def save_monitoring_credentials(root: Path, api_key: str, api_secret: str) -> Tuple[bool, str]:
    if not dpapi_available():
        return False, "DPAPI_NOT_WINDOWS"
    payload = json.dumps(
        {"api_key": api_key.strip(), "api_secret": api_secret.strip()},
        separators=(",", ":"),
    ).encode("utf-8")
    protected = _protect(payload)
    if not protected:
        return False, "DPAPI_ENCRYPT_FAILED"
    path = _cred_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(protected)
    return True, "DPAPI_SAVED"


def load_monitoring_credentials(root: Path) -> Optional[T212Credentials]:
    path = _cred_path(root)
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


def forget_monitoring_credentials(root: Path) -> None:
    path = _cred_path(root)
    if path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def persistence_status(root: Path) -> Dict[str, Any]:
    from integrations.trading212.t212_auth_profile_model import PROFILE_MONITORING_READONLY
    from integrations.trading212.t212_dual_profile_secure_store import load_profile_credentials
    from integrations.trading212.t212_secure_credential_store import load_secure_credentials, secure_store_available

    dpapi_path = _cred_path(root)
    return {
        "keyring_available": secure_store_available(),
        "keyring_configured": bool(load_secure_credentials() or load_profile_credentials(PROFILE_MONITORING_READONLY)),
        "dpapi_available": dpapi_available(),
        "dpapi_configured": dpapi_path.is_file() and load_monitoring_credentials(root) is not None,
        "dpapi_path": str(dpapi_path),
    }
