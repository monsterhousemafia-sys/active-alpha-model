"""Persisted user preference for P17 review mode (order submission block)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json

P17_ENV = "AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION"
LIVE_ORDER_ENV = "AA_NO_LIVE_ORDER_SUBMISSION"
_PREF_REL = Path("control") / "p17_review_mode_user_preference.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def preference_path(root: Path) -> Path:
    return Path(root) / _PREF_REL


def load_review_mode_preference(root: Path) -> Dict[str, Any]:
    path = preference_path(root)
    if not path.is_file():
        return {
            "schema_version": 1,
            "review_mode_enabled": True,
            "source": "default_fail_closed",
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return {
            **doc,
            "review_mode_enabled": bool(doc.get("review_mode_enabled", True)),
        }
    except (json.JSONDecodeError, OSError, TypeError):
        return {
            "schema_version": 1,
            "review_mode_enabled": True,
            "source": "corrupt_pref_fail_closed",
        }


def save_review_mode_preference(root: Path, *, enabled: bool, changed_by: str = "user") -> Path:
    payload = {
        "schema_version": 1,
        "review_mode_enabled": bool(enabled),
        "updated_at_utc": _utc_now(),
        "changed_by": changed_by,
        "note": "True = keine Live-Orders aus der App (Review Mode AN).",
    }
    path = preference_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, payload)


def apply_review_mode_to_environment(*, enabled: bool) -> None:
    flag = "1" if enabled else "0"
    os.environ[P17_ENV] = flag
    os.environ[LIVE_ORDER_ENV] = flag


def apply_saved_review_mode_to_environment(root: Path) -> bool:
    pref = load_review_mode_preference(root)
    enabled = bool(pref.get("review_mode_enabled", True))
    apply_review_mode_to_environment(enabled=enabled)
    return enabled


def set_review_mode_enabled(root: Path, *, enabled: bool, changed_by: str = "user") -> bool:
    save_review_mode_preference(root, enabled=enabled, changed_by=changed_by)
    apply_review_mode_to_environment(enabled=enabled)
    return enabled
