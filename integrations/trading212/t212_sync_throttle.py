"""Trading 212 sync throttle — test vs full sync get separate counters."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from integrations.trading212.t212_user_messages import (
    humanize_t212_error,
    throttle_wait_message,
)

_THROTTLE_REL = Path("live_pilot/manual_execution/readonly_real_account_state/sync_throttle.json")
# Full sync = 3 GETs (summary, cash, positions).
MIN_SYNC_INTERVAL_S = 120
CACHE_STALE_FOR_AUTO_SYNC_S = 300
MIN_FORCE_SYNC_GAP_S = 8
# «Verbindung testen» = 1 GET — must not block orders/sync for 2 minutes.
MIN_CONNECTION_TEST_GAP_S = 5
CONNECTION_TEST_RATE_LIMIT_COOLDOWN_S = 45


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_utc(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _throttle_path(root: Path) -> Path:
    return Path(root) / _THROTTLE_REL


def read_throttle_state(root: Path) -> Dict[str, Any]:
    path = _throttle_path(root)
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _write_throttle_state(root: Path, doc: Dict[str, Any]) -> None:
    path = _throttle_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def record_sync_attempt(root: Path, *, success: bool, error: str = "") -> None:
    """Full account sync only — not used by «Verbindung testen»."""
    doc = read_throttle_state(root)
    doc["last_sync_attempt_utc"] = _utc_now()
    doc["last_attempt_utc"] = doc["last_sync_attempt_utc"]
    if success:
        doc["last_sync_success_utc"] = doc["last_sync_attempt_utc"]
        doc["last_success_utc"] = doc["last_sync_success_utc"]
        doc.pop("last_sync_rate_limit_utc", None)
        doc.pop("last_rate_limit_utc", None)
    elif "429" in error:
        doc["last_sync_rate_limit_utc"] = doc["last_sync_attempt_utc"]
        doc["last_rate_limit_utc"] = doc["last_sync_rate_limit_utc"]
    _write_throttle_state(root, doc)


def record_connection_test(root: Path, *, success: bool, error: str = "") -> None:
    """Lightweight probe — does not trigger the 120s full-sync pause."""
    doc = read_throttle_state(root)
    now = _utc_now()
    doc["last_connection_test_utc"] = now
    if success:
        doc["last_connection_test_ok_utc"] = now
        doc.pop("last_connection_test_rate_limit_utc", None)
    elif "429" in error:
        doc["last_connection_test_rate_limit_utc"] = now
    _write_throttle_state(root, doc)


def is_rate_limit_error(message: str) -> bool:
    return "429" in str(message or "")


def is_auth_error(message: str) -> bool:
    low = str(message or "").lower()
    return "401" in low or "403" in low or "unauthorized" in low or "bad api" in low


def _seconds_since(doc: Dict[str, Any], key: str) -> Optional[float]:
    dt = _parse_utc(doc.get(key))
    if dt is None:
        return None
    return (datetime.now(timezone.utc) - dt).total_seconds()


def seconds_since_last_sync_attempt(root: Path) -> Optional[float]:
    doc = read_throttle_state(root)
    elapsed = _seconds_since(doc, "last_sync_attempt_utc")
    if elapsed is not None:
        return elapsed
    return _seconds_since(doc, "last_attempt_utc")


def should_sync_now(
    root: Path,
    *,
    force: bool,
    last_successful_sync_utc: Optional[str] = None,
) -> Tuple[bool, str]:
    """Return (allowed, reason_de). Ignores connection-test timestamps."""
    if force:
        elapsed = seconds_since_last_sync_attempt(root)
        if elapsed is not None and elapsed < MIN_FORCE_SYNC_GAP_S:
            wait = int(MIN_FORCE_SYNC_GAP_S - elapsed)
            return False, throttle_wait_message(wait)
        doc = read_throttle_state(root)
        rl = _parse_utc(doc.get("last_sync_rate_limit_utc") or doc.get("last_rate_limit_utc"))
        if rl is not None:
            elapsed_rl = (datetime.now(timezone.utc) - rl).total_seconds()
            if elapsed_rl < CONNECTION_TEST_RATE_LIMIT_COOLDOWN_S:
                wait = int(CONNECTION_TEST_RATE_LIMIT_COOLDOWN_S - elapsed_rl)
                return False, humanize_t212_error("429") + f"\nNoch ca. {wait} s bis «Aktualisieren»."
        return True, ""

    elapsed = seconds_since_last_sync_attempt(root)
    if elapsed is not None and elapsed < MIN_SYNC_INTERVAL_S:
        wait = int(MIN_SYNC_INTERVAL_S - elapsed)
        return (
            False,
            f"{throttle_wait_message(wait)}\nAutomatischer Sync pausiert — später «Aktualisieren».",
        )

    last_ok = _parse_utc(last_successful_sync_utc)
    if last_ok is not None:
        age = (datetime.now(timezone.utc) - last_ok).total_seconds()
        if age < CACHE_STALE_FOR_AUTO_SYNC_S:
            return False, ""

    return True, ""


def format_api_error_de(message: str, *, last_sync_utc: Optional[str] = None) -> str:
    return humanize_t212_error(message, last_sync_utc=last_sync_utc)


def can_test_connection_now(root: Path) -> Tuple[bool, str]:
    """Only limits repeated «Verbindung testen» clicks — not trading/sync."""
    doc = read_throttle_state(root)
    now = datetime.now(timezone.utc)

    rl = _parse_utc(doc.get("last_connection_test_rate_limit_utc"))
    if rl is not None:
        elapsed_rl = (now - rl).total_seconds()
        if elapsed_rl < CONNECTION_TEST_RATE_LIMIT_COOLDOWN_S:
            wait = int(CONNECTION_TEST_RATE_LIMIT_COOLDOWN_S - elapsed_rl)
            return False, humanize_t212_error("429") + f"\nTest erneut in ca. {wait} s."

    elapsed = _seconds_since(doc, "last_connection_test_utc")
    if elapsed is not None and elapsed < MIN_CONNECTION_TEST_GAP_S:
        wait = int(MIN_CONNECTION_TEST_GAP_S - elapsed)
        return False, throttle_wait_message(wait)

    return True, ""


def rate_limit_user_message_de(last_sync_utc: Optional[str] = None) -> str:
    return humanize_t212_error("429", last_sync_utc=last_sync_utc)
