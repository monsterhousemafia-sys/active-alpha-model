"""Checkpoints — isolated state snapshots without publishing validated pointers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def checkpoint_path(root: Path, job_id: str) -> Path:
    return Path(root) / "checkpoints" / f"{job_id}.json"


def write_checkpoint(root: Path, job_id: str, payload: Dict[str, Any]) -> Path:
    root = Path(root)
    (root / "checkpoints").mkdir(parents=True, exist_ok=True)
    record = {
        "job_id": job_id,
        "saved_at_utc": _utc_now(),
        **payload,
    }
    return atomic_write_json(checkpoint_path(root, job_id), record)


def load_checkpoint(root: Path, job_id: str) -> Optional[Dict[str, Any]]:
    path = checkpoint_path(root, job_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
