"""EXE-only user confirmation lease before any live T212 order POST."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_LEASE_REL = Path("live_pilot/confirmed_execution/gui_execution_confirmation.json")
_DEFAULT_TTL_SECONDS = 600


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _lease_path(root: Path) -> Path:
    p = Path(root) / _LEASE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load_lease(root: Path) -> Dict[str, Any]:
    path = _lease_path(root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_lease(root: Path, doc: Dict[str, Any]) -> None:
    atomic_write_json(_lease_path(root), doc)


def _parse_utc(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def manual_gui_confirm_enforced(root: Path | None = None) -> bool:
    """Live broker POSTs require an EXE confirmation lease (never headless auto-trade)."""
    if os.environ.get("AA_ALLOW_HEADLESS_LIVE_ORDERS", "").strip() == "1":
        return False
    return True


def grant_execution_confirmation(
    root: Path,
    *,
    source: str,
    scope: str = "LIVE_WAVE",
    max_submissions: int = 50,
    ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Called from EXE after user confirms Yes — unlocks live submit_confirmed_order calls."""
    root = Path(root)
    from analytics.prediction_operations import evaluate_prediction_readiness_for_orders

    pred = evaluate_prediction_readiness_for_orders(root)
    if not pred.get("ok") and not pred.get("skipped"):
        return {
            "ok": False,
            "error": "PREDICTION_NOT_READY",
            "message_de": pred.get("message_de"),
            "blockers": pred.get("blockers"),
        }

    now = _utc_now()
    doc = {
        "schema_version": 1,
        "lease_id": str(uuid.uuid4()),
        "scope": scope,
        "source": source,
        "granted_at_utc": now.isoformat(),
        "expires_at_utc": (now + timedelta(seconds=max(30, int(ttl_seconds)))).isoformat(),
        "max_submissions": max(1, int(max_submissions)),
        "remaining_submissions": max(1, int(max_submissions)),
        "metadata": metadata or {},
        "status": "ACTIVE",
    }
    _save_lease(root, doc)
    return {"ok": True, "lease": doc}


def _lease_valid(doc: Dict[str, Any]) -> bool:
    if not doc or doc.get("status") != "ACTIVE":
        return False
    expires = _parse_utc(str(doc.get("expires_at_utc") or ""))
    if expires is not None and _utc_now() >= expires:
        return False
    remaining = int(doc.get("remaining_submissions") or 0)
    return remaining > 0


def has_active_execution_confirmation(root: Path) -> bool:
    return _lease_valid(_load_lease(root))


def lease_status(root: Path) -> Dict[str, Any]:
    doc = _load_lease(root)
    valid = _lease_valid(doc)
    return {
        "active": valid,
        "remaining_submissions": int(doc.get("remaining_submissions") or 0) if valid else 0,
        "expires_at_utc": doc.get("expires_at_utc"),
        "source": doc.get("source"),
        "scope": doc.get("scope"),
    }


def consume_execution_slot(root: Path) -> Dict[str, Any]:
    """Consume one submission slot from the active GUI confirmation lease."""
    root = Path(root)
    if not manual_gui_confirm_enforced(root):
        return {"ok": True, "skipped": "HEADLESS_OVERRIDE"}

    doc = _load_lease(root)
    if not _lease_valid(doc):
        return {
            "ok": False,
            "error": "GUI_CONFIRMATION_REQUIRED",
            "message_de": (
                "Live-Order blockiert: In der EXE einmal bestätigen "
                "(«Champion-Portfolio an T212 senden» oder Order-Dialog «Ja — ausführen»)."
            ),
        }

    remaining = int(doc.get("remaining_submissions") or 0) - 1
    doc["remaining_submissions"] = remaining
    doc["last_consumed_at_utc"] = _utc_now_iso()
    if remaining <= 0:
        doc["status"] = "EXHAUSTED"
        doc["exhausted_at_utc"] = _utc_now_iso()
    _save_lease(root, doc)
    return {"ok": True, "remaining_submissions": max(0, remaining)}


def revoke_execution_confirmation(root: Path, *, reason: str = "REVOKED") -> None:
    doc = _load_lease(root)
    if not doc:
        return
    doc["status"] = reason
    doc["revoked_at_utc"] = _utc_now_iso()
    _save_lease(root, doc)
