"""Fail-closed gate — wer darf Live-Quotes aus dem Internet refreshen."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_live_quote_access_policy.json")
_EVIDENCE_REL = Path("evidence/r3_live_quote_access_latest.json")

_DEFAULT_ALLOWED = (
    "king_ops",
    "keepalive",
    "r3_quote_keepalive",
    "ensure",
    "r3_ops_kernel",
    "daily_alpha",
    "r3_browser_ingest",
    "fall_watch",
    "pilot_live_trade_gate",
    "champion_quote_gate",
    "R3_COCKPIT",
    "R3_DESKTOP",
    "R3_ORDER_DESK",
    "ORDER_WORKFLOW_DIALOG",
    "LIVE_DASHBOARD_PORTFOLIO",
    "LIVE_DASHBOARD_REBALANCE",
    "USER_CLICK",
)
_DEFAULT_FORBIDDEN = (
    "background",
    "headless",
    "scheduler",
    "session",
    "aa_scheduler",
    "sync_r3_flow",
    "alpha_engine",
    "DEFERRED_INTENT",
    "unknown",
    "UNKNOWN",
)


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


def load_live_quote_access_policy(root: Path) -> Dict[str, Any]:
    doc = _load_json(Path(root) / _POLICY_REL)
    if not doc.get("allowed_owners"):
        doc["allowed_owners"] = list(_DEFAULT_ALLOWED)
    if not doc.get("forbidden_owners"):
        doc["forbidden_owners"] = list(_DEFAULT_FORBIDDEN)
    return doc


def _test_bypass() -> bool:
    if os.environ.get("AA_LIVE_QUOTE_ACCESS_TEST_BYPASS", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.environ.get("AA_OFFLINE_COCKPIT_TEST", "").strip() == "1":
        return True
    return "pytest" in sys.modules


def is_authorized_live_quote_owner(owner: str, policy: Optional[Dict[str, Any]] = None) -> bool:
    who = str(owner or "").strip()
    if not who:
        return False
    pol = policy or {}
    forbidden = {str(s) for s in (pol.get("forbidden_owners") or _DEFAULT_FORBIDDEN)}
    if who in forbidden:
        return False
    allowed = {str(s) for s in (pol.get("allowed_owners") or _DEFAULT_ALLOWED)}
    return who in allowed


def _record_access(root: Path, doc: Dict[str, Any]) -> None:
    atomic_write_json(Path(root) / _EVIDENCE_REL, doc)


def check_live_quote_refresh_allowed(
    root: Path,
    *,
    owner: str,
    operation: str = "refresh",
) -> Dict[str, Any]:
    """Fail-closed before any Yahoo/T212 live quote fetch."""
    root = Path(root)
    who = str(owner or "").strip() or "UNKNOWN"
    if _test_bypass():
        return {
            "allowed": True,
            "owner": who,
            "operation": operation,
            "bypass": "test",
            "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        }

    policy = load_live_quote_access_policy(root)
    if not is_authorized_live_quote_owner(who, policy):
        doc = {
            "schema_version": 1,
            "updated_at_utc": _utc_now(),
            "allowed": False,
            "owner": who,
            "operation": operation,
            "error": "LIVE_QUOTE_ACCESS_DENIED",
            "message_de": (
                f"Live-Quote-Refresh blockiert — owner '{who}' nicht autorisiert "
                "(fail-closed)."
            ),
            "policy_ref": str(_POLICY_REL).replace("\\", "/"),
        }
        _record_access(root, doc)
        return doc

    if policy.get("refresh_requires_internet", True):
        try:
            from analytics.r3_internet_requirement import require_internet_for

            net = require_internet_for(root, consumer="r3")
            if not net.get("allowed"):
                doc = {
                    "schema_version": 1,
                    "updated_at_utc": _utc_now(),
                    "allowed": False,
                    "owner": who,
                    "operation": operation,
                    "error": "INTERNET_REQUIRED",
                    "message_de": str(net.get("message_de") or "Kein Internet — Live-Quotes blockiert"),
                    "policy_ref": str(_POLICY_REL).replace("\\", "/"),
                }
                _record_access(root, doc)
                return doc
        except Exception as exc:
            doc = {
                "schema_version": 1,
                "updated_at_utc": _utc_now(),
                "allowed": False,
                "owner": who,
                "operation": operation,
                "error": "INTERNET_GATE_ERROR",
                "message_de": f"Internet-Gate — {str(exc)[:80]}",
                "policy_ref": str(_POLICY_REL).replace("\\", "/"),
            }
            _record_access(root, doc)
            return doc

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "allowed": True,
        "owner": who,
        "operation": operation,
        "message_de": f"Live-Quote-Refresh erlaubt — {who}",
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    _record_access(root, doc)
    return doc


def access_denied_snapshot(root: Path, *, gate: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only stale fallback when refresh is blocked."""
    from market.live_quote_engine import classify_freshness, load_live_quote_snapshot

    cached = load_live_quote_snapshot(root)
    if cached:
        stale = dict(cached)
        stale["refresh_skipped"] = True
        stale["live_quote_access_denied"] = True
        stale["access_gate"] = {
            "error": gate.get("error"),
            "owner": gate.get("owner"),
            "message_de": gate.get("message_de"),
        }
        stale["freshness"] = classify_freshness(stale)
        return stale
    now = _utc_now()
    snap = {
        "generated_at_utc": now,
        "provider": "ACCESS_DENIED",
        "executable_prices_eur": {},
        "quotes_by_symbol": {},
        "refresh_skipped": True,
        "live_quote_access_denied": True,
        "access_gate": {
            "error": gate.get("error"),
            "owner": gate.get("owner"),
            "message_de": gate.get("message_de"),
        },
        "freshness": classify_freshness({"generated_at_utc": "1970-01-01T00:00:00+00:00"}),
    }
    return snap
