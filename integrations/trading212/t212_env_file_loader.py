"""Load Trading 212 credentials from a local .env file (never committed)."""
from __future__ import annotations

import os
from pathlib import Path


def load_trading212_env_file(root: Path, *, filename: str = ".env") -> bool:
    """Populate os.environ from local env files without overwriting existing vars."""
    root = Path(root)
    loaded = False
    for name in ("trading212_zugangsdaten.env", filename, ".env.trading212.local"):
        if load_env_file(root / name):
            loaded = True
    return loaded


def load_env_file(path: Path) -> bool:
    """Populate os.environ from an env file without overwriting existing vars."""
    path = Path(path)
    if not path.is_file():
        return False
    loaded = False
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key or key in os.environ:
            continue
        os.environ[key] = val
        loaded = True
    return loaded
