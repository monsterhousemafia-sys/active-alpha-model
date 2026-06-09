"""One-time confirmation tokens bound to exact order payload."""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

TOKEN_TTL_SECONDS = 60


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _payload_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def confirmation_phrase(payload: Dict[str, Any]) -> str:
    side = payload.get("side", "BUY")
    sym = payload.get("instrument", "?")
    amt = payload.get("max_notional_eur", 0)
    return f"BESTÄTIGE LIMIT {side} {sym} {amt:.2f} EUR"


def issue_token(root: Path, payload: Dict[str, Any], *, profile: str) -> Dict[str, Any]:
    root = Path(root)
    token_id = str(uuid.uuid4())
    token_secret = secrets.token_urlsafe(32)
    ph = _payload_hash(payload)
    expires = (datetime.now(timezone.utc) + timedelta(seconds=TOKEN_TTL_SECONDS)).replace(microsecond=0).isoformat()
    record = {
        "token_id": token_id,
        "token_secret_hash": hashlib.sha256(token_secret.encode()).hexdigest(),
        "payload_hash_sha256": ph,
        "payload": payload,
        "profile": profile,
        "issued_at_utc": _utc_now(),
        "expires_at_utc": expires,
        "used": False,
        "status": "CONFIRMED_PAYLOAD_LOCKED",
    }
    store = root / "live_pilot/confirmed_execution/confirmation_tokens"
    store.mkdir(parents=True, exist_ok=True)
    atomic_write_json(store / f"{token_id}.json", record)
    return {**record, "one_time_token": f"{token_id}:{token_secret}", "confirmation_phrase": confirmation_phrase(payload)}


def validate_and_consume(root: Path, one_time_token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    if ":" not in one_time_token:
        return {"valid": False, "error": "INVALID_TOKEN_FORMAT"}
    token_id, token_secret = one_time_token.split(":", 1)
    path = root / "live_pilot/confirmed_execution/confirmation_tokens" / f"{token_id}.json"
    if not path.is_file():
        return {"valid": False, "error": "TOKEN_NOT_FOUND"}
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("used"):
        return {"valid": False, "error": "TOKEN_ALREADY_USED"}
    if _payload_hash(payload) != record.get("payload_hash_sha256"):
        return {"valid": False, "error": "INVALIDATED_PAYLOAD_CHANGED_REVIEW_REQUIRED_AGAIN"}
    if hashlib.sha256(token_secret.encode()).hexdigest() != record.get("token_secret_hash"):
        return {"valid": False, "error": "TOKEN_SECRET_MISMATCH"}
    expires = record.get("expires_at_utc", "")
    if expires and expires < _utc_now():
        return {"valid": False, "error": "TOKEN_EXPIRED"}
    record["used"] = True
    record["consumed_at_utc"] = _utc_now()
    record["status"] = "SUBMISSION_IN_PROGRESS"
    atomic_write_json(path, record)
    return {"valid": True, "token_id": token_id, "record": record}
