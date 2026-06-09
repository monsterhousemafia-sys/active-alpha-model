"""Cancel workflow — single confirmation, mock-only in P17."""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json
from execution.confirmed_live.p17_review_mode_guard import review_mode_active


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tokens_path(root: Path) -> Path:
    p = root / "live_pilot/confirmed_execution/cancel_tokens.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def cancel_confirmation_phrase(order: Dict[str, Any]) -> str:
    oid = order.get("order_id") or order.get("draft_id") or "ORDER"
    return f"BESTÄTIGE STORNIERUNG {oid}"


def issue_cancel_token(root: Path, order: Dict[str, Any], *, profile: str) -> Dict[str, Any]:
    payload = {
        "order_id": order.get("order_id"),
        "draft_id": order.get("draft_id"),
        "instrument": order.get("instrument"),
        "quantity": order.get("quantity"),
    }
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    token = secrets.token_hex(16)
    expires = (datetime.now(timezone.utc) + timedelta(seconds=60)).replace(microsecond=0).isoformat()
    record = {
        "one_time_token": token,
        "payload_hash_sha256": payload_hash,
        "profile": profile,
        "issued_at_utc": _utc_now(),
        "expires_at_utc": expires,
        "used": False,
    }
    path = _tokens_path(root)
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"tokens": {}}
    data.setdefault("tokens", {})[token] = record
    atomic_write_json(path, data)
    return {"one_time_token": token, "confirmation_phrase": cancel_confirmation_phrase(order), "expires_at_utc": expires}


def validate_and_consume_cancel_token(root: Path, token: str, order: Dict[str, Any]) -> Dict[str, Any]:
    path = _tokens_path(root)
    if not path.is_file():
        return {"valid": False, "error": "NO_CANCEL_TOKEN"}
    data = json.loads(path.read_text(encoding="utf-8"))
    rec = (data.get("tokens") or {}).get(token)
    if not rec or rec.get("used"):
        return {"valid": False, "error": "TOKEN_INVALID_OR_USED"}
    expires = datetime.fromisoformat(rec["expires_at_utc"])
    if datetime.now(timezone.utc) > expires:
        return {"valid": False, "error": "TOKEN_EXPIRED"}
    payload = {
        "order_id": order.get("order_id"),
        "draft_id": order.get("draft_id"),
        "instrument": order.get("instrument"),
        "quantity": order.get("quantity"),
    }
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    if payload_hash != rec.get("payload_hash_sha256"):
        return {"valid": False, "error": "INVALIDATED_PAYLOAD_CHANGED_REVIEW_REQUIRED_AGAIN"}
    rec["used"] = True
    atomic_write_json(path, data)
    return {"valid": True, "record": rec}


def submit_cancel(root: Path, order: Dict[str, Any], *, one_time_token: str) -> Dict[str, Any]:
    v = validate_and_consume_cancel_token(root, one_time_token, order)
    if not v.get("valid"):
        return {"ok": False, "stage": "token", "error": v.get("error")}

    if review_mode_active():
        return {
            "ok": True,
            "status": "CANCEL_MOCK_BLOCKED_LIVE_REVIEW_MODE",
            "mock": True,
            "message": "P17 — keine Live-Stornierung; Fixture bestätigt.",
        }

    return {"ok": False, "stage": "network", "error": "LIVE_CANCEL_NETWORK_DISABLED"}
