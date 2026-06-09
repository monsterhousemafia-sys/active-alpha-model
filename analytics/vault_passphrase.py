"""Zusatz-Passphrase — zweite Schicht, PBKDF2 600k Iterationen."""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

_SALT_REL = Path("control/secrets/.vault_kdf_salt")
_ITERATIONS = 600_000
_KEYRING_SERVICE = "active-alpha-credential-vault"


def _account(root: Path) -> str:
    import hashlib

    return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:16]


def _salt_path(root: Path) -> Path:
    return Path(root) / _SALT_REL


def ensure_salt(root: Path) -> bytes:
    root = Path(root)
    path = _salt_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    if path.is_file():
        return path.read_bytes()[:32]
    salt = secrets.token_bytes(32)
    path.write_bytes(salt)
    os.chmod(path, 0o600)
    return salt


def derive_passphrase_key(root: Path, passphrase: str) -> bytes:
    salt = ensure_salt(root)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_ITERATIONS,
    )
    return kdf.derive(str(passphrase or "").encode("utf-8"))


def combine_keys(machine_key: bytes, passphrase_key: bytes) -> bytes:
    return hashlib.sha256(machine_key + passphrase_key).digest()


def cache_passphrase_unlock(root: Path, passphrase: str) -> bool:
    try:
        import keyring

        derived = base64.urlsafe_b64encode(derive_passphrase_key(root, passphrase)).decode("ascii")
        keyring.set_password(_KEYRING_SERVICE, f"{_account(root)}:pw_unlock", derived)
        return True
    except Exception:
        return False


def load_cached_passphrase_key(root: Path) -> Optional[bytes]:
    try:
        import keyring

        raw = keyring.get_password(_KEYRING_SERVICE, f"{_account(root)}:pw_unlock")
        if not raw:
            return None
        return base64.urlsafe_b64decode(raw.encode("ascii"))
    except Exception:
        return None


def clear_cached_passphrase(root: Path) -> None:
    try:
        import keyring

        keyring.delete_password(_KEYRING_SERVICE, f"{_account(root)}:pw_unlock")
    except Exception:
        pass


def validate_passphrase(passphrase: str) -> Optional[str]:
    pw = str(passphrase or "")
    if len(pw) < 12:
        return "Passphrase mindestens 12 Zeichen"
    return None
