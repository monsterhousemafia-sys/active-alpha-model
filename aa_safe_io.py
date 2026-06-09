"""Atomic file writes for control-plane and run artifacts."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Union


def atomic_write_bytes(path: Path, data: bytes) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if tmp_path.is_file():
            tmp_path.unlink(missing_ok=True)
    return path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> Path:
    return atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(path: Path, payload: Any, *, indent: int = 2) -> Path:
    text = json.dumps(payload, indent=indent, sort_keys=True, ensure_ascii=False)
    return atomic_write_text(path, text + "\n")


def atomic_write_yaml(path: Path, payload: Any, *, sort_keys: bool = False) -> Path:
    import yaml

    text = yaml.safe_dump(payload, sort_keys=sort_keys, allow_unicode=True, default_flow_style=False)
    if not text.endswith("\n"):
        text += "\n"
    return atomic_write_text(path, text)
