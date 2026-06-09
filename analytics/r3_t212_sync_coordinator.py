"""T212 API sync coordinator — single owner, coalesce concurrent callers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_t212_sync_policy.json")
_STATE_REL = Path("control/r3_t212_sync_coordinator_state.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_sync_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc:
        return {
            "schema_version": 1,
            "canonical_owner": "prognosis_pipeline",
            "min_coalesce_interval_s": 120,
            "prognosis_first": True,
        }
    return doc


def _parse_utc(raw: str) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _seconds_since_sync(state: Dict[str, Any]) -> Optional[float]:
    dt = _parse_utc(str(state.get("last_sync_utc") or ""))
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def resolve_t212_sync_force(root: Path, *, owner: str, force: bool = False) -> bool:
    """Return effective force flag — coalesce non-owner / recent syncs."""
    root = Path(root)
    policy = load_sync_policy(root)
    if not policy.get("prognosis_first", True):
        return force

    canonical = str(policy.get("canonical_owner") or "prognosis_pipeline")
    min_gap = int(policy.get("min_coalesce_interval_s") or 120)
    state = _load_json(root / _STATE_REL)
    elapsed = _seconds_since_sync(state)

    if owner == canonical:
        if force:
            return True
        if elapsed is not None and elapsed < min_gap and state.get("last_sync_ok"):
            return False
        return force

    if elapsed is not None and elapsed < min_gap and state.get("last_sync_ok"):
        return False
    return False


def should_coalesce_t212_sync(root: Path, *, owner: str, force: bool = False) -> Tuple[bool, str]:
    """
    Return (skip_sync, reason_de).
    skip_sync=True → caller must use cached broker evidence only.
    """
    root = Path(root)
    policy = load_sync_policy(root)
    if not policy.get("prognosis_first", True):
        return False, ""

    if force and resolve_t212_sync_force(root, owner=owner, force=True):
        return False, ""

    canonical = str(policy.get("canonical_owner") or "prognosis_pipeline")
    min_gap = int(policy.get("min_coalesce_interval_s") or 120)
    state = _load_json(root / _STATE_REL)
    elapsed = _seconds_since_sync(state)

    if owner != canonical and elapsed is not None and elapsed < min_gap and state.get("last_sync_ok"):
        return True, f"T212 kürzlich von {state.get('last_owner') or canonical} — Cache"

    if owner == canonical and not force and elapsed is not None and elapsed < min_gap and state.get("last_sync_ok"):
        return True, f"T212 frisch ({int(elapsed)} s) — übersprungen"

    try:
        from integrations.trading212.t212_sync_throttle import should_sync_now
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        cached = load_cached_broker_status(root)
        cached_sync = cached.last_successful_sync_utc if cached else None
        allow, throttle_de = should_sync_now(root, force=force, last_successful_sync_utc=cached_sync)
        if not allow and not force:
            return True, throttle_de or "T212 throttle — Cache"
    except Exception:
        pass

    return False, ""


def record_t212_sync(root: Path, *, owner: str, ok: bool, throttled: bool = False) -> None:
    state = _load_json(Path(root) / _STATE_REL)
    now = _utc_now()
    state.update(
        {
            "updated_at_utc": now,
            "last_owner": owner,
            "last_sync_ok": bool(ok),
            "last_throttled": bool(throttled),
        }
    )
    if ok and not throttled:
        state["last_sync_utc"] = now
    atomic_write_json(Path(root) / _STATE_REL, state)
