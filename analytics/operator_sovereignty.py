"""Operator-Souveränität — externe Linux-Eingriffe fail-closed, nur Sprache des Benutzers."""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/operator_sovereignty_policy.json")
_MANDATE_REL = Path("evidence/operator_natural_language_ack.json")
_STATUS_REL = Path("evidence/operator_sovereignty_latest.json")

PRIVILEGED_ACTIONS: FrozenSet[str] = frozenset(
    {
        "h1-force",
        "lean-on",
        "lean-turbo",
        "lean-max",
        "lean-off",
        "kernel-boundary-ack-apply",
        "kernel-boundary-apply-runtime",
        "cognitive-succession",
        "succession-finish",
        "server-bootstrap",
        "system",
        "operator-mandate-revoke",
        "sovereignty-disable",
    }
)

ROUTINE_EXTERNAL_ACTIONS: FrozenSet[str] = frozenset(
    {
        "status",
        "h1-status",
        "lean-status",
        "mandate",
        "warnings",
        "refresh",
        "learn",
        "h1",
        "h1-watch",
        "h1-benchmark",
        "king-pulse",
        "h1-dispatch",
        "trading-day",
        "kernel-boundary-audit",
        "kernel-boundary-plan-sysctl",
        "runtime-status",
        "cognitive-status",
        "launch-status",
        "sovereignty",
        "operator-mandate",
    }
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_policy(root: Path) -> Dict[str, Any]:
    path = Path(root) / _POLICY_REL
    if not path.is_file():
        return {"mandate_ttl_minutes": 120, "fail_closed": True}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {"mandate_ttl_minutes": 120, "fail_closed": True}


def detect_invocation_source() -> str:
    channel = os.environ.get("AA_OPERATOR_CHANNEL", "").strip().lower()
    if channel == "conversational":
        return "conversational"
    if os.environ.get("INVOCATION_ID", "").strip():
        return "systemd"
    if os.environ.get("CRON", "").strip() or os.environ.get("AA_INVOCATION_SOURCE", "").strip().lower() == "cron":
        return "cron"
    src = os.environ.get("AA_INVOCATION_SOURCE", "").strip().lower()
    if src in ("script", "timer", "systemd"):
        return "systemd" if src != "script" else "script"
    return "raw_cli"


def _mandate_path(root: Path) -> Path:
    return Path(root) / _MANDATE_REL


def load_mandate(root: Path) -> Optional[Dict[str, Any]]:
    path = _mandate_path(root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _mandate_valid(mandate: Optional[Dict[str, Any]], action: str, *, now: datetime | None = None) -> bool:
    if not mandate or not mandate.get("ok"):
        return False
    now = now or datetime.now(timezone.utc)
    try:
        exp = datetime.fromisoformat(str(mandate.get("expires_at_utc", "")).replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now > exp:
            return False
    except (TypeError, ValueError):
        return False
    actions = {str(a).strip() for a in (mandate.get("authorized_actions") or [])}
    return action in actions or "*" in actions


def record_natural_language_mandate(
    root: Path,
    *,
    utterance_de: str,
    authorized_actions: List[str],
    ttl_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Sprach-Mandat des Benutzers — nur über conversational-Kanal."""
    root = Path(root)
    if detect_invocation_source() != "conversational":
        return {
            "ok": False,
            "blocked_de": "Mandat nur über Agent-Kanal (natürliche Sprache) — kein Roh-CLI",
            "hint_de": "Benutzer spricht mit dem Agenten; der Agent setzt AA_OPERATOR_CHANNEL=conversational",
        }
    policy = load_policy(root)
    ttl = int(ttl_minutes or policy.get("mandate_ttl_minutes") or 120)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=max(5, ttl))
    text = str(utterance_de or "").strip()[:2000]
    actions = sorted({str(a).strip() for a in authorized_actions if str(a).strip()})
    if not actions:
        actions = ["*"]
    doc = {
        "schema_version": 1,
        "ok": True,
        "utterance_de": text,
        "utterance_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
        "authorized_actions": actions,
        "issued_at_utc": now.replace(microsecond=0).isoformat(),
        "expires_at_utc": expires.replace(microsecond=0).isoformat(),
        "channel": "conversational",
        "authority_de": "Benutzer → Agent → Mandat",
    }
    atomic_write_json(_mandate_path(root), doc)
    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(
            root,
            level="A",
            action="operator_nl_mandate",
            result="OK",
            details={"actions": actions, "utterance_hash": doc["utterance_hash"]},
        )
    except Exception:
        pass
    return doc


def check_privileged_action(root: Path, action: str) -> Dict[str, Any]:
    """Fail-closed: externe Linux-Quellen dürfen keine privilegierten Aktionen."""
    root = Path(root)
    action = str(action or "").strip()
    policy = load_policy(root)

    if action in ROUTINE_EXTERNAL_ACTIONS or action not in PRIVILEGED_ACTIONS:
        doc = {
            "ok": True,
            "action": action,
            "privileged": False,
            "source": detect_invocation_source(),
            "headline_de": "Routine — keine Souveränitätsprüfung",
        }
        atomic_write_json(root / _STATUS_REL, {**doc, "checked_at_utc": _utc_now()})
        return doc

    source = detect_invocation_source()
    mandate = load_mandate(root)
    valid = _mandate_valid(mandate, action)

    if source == "conversational" and valid:
        doc = {
            "ok": True,
            "action": action,
            "privileged": True,
            "source": source,
            "mandate_expires_at_utc": mandate.get("expires_at_utc") if mandate else None,
            "headline_de": f"Erlaubt — Sprach-Mandat für {action}",
        }
        atomic_write_json(root / _STATUS_REL, {**doc, "checked_at_utc": _utc_now()})
        return doc

    blocked_de = {
        "systemd": "Systemd-Timer darf das nicht — nur der Benutzer über normale Sprache",
        "cron": "Cron darf das nicht — nur der Benutzer über normale Sprache",
        "script": "Hintergrund-Skript blockiert — nur Sprach-Mandat des Benutzers",
        "raw_cli": "Roh-Terminal blockiert — bitte mit dem Agenten in normaler Sprache sprechen",
    }.get(source, "Externe Quelle blockiert")

    doc = {
        "ok": False,
        "action": action,
        "privileged": True,
        "source": source,
        "mandate_present": mandate is not None,
        "mandate_valid": valid,
        "blocked_de": blocked_de,
        "hint_de": (
            "Benutzer formuliert Wunsch in normaler Sprache → Agent protokolliert Mandat → "
            "dann Ausführung. Kein Computercode vom Benutzer nötig."
        ),
        "policy_de": policy.get("principle_de"),
        "headline_de": f"Blockiert — {blocked_de}",
    }
    atomic_write_json(root / _STATUS_REL, {**doc, "checked_at_utc": _utc_now()})
    try:
        from analytics.linux_operator_scope import log_operator_action

        log_operator_action(
            root,
            level="A",
            action=f"sovereignty_block_{action}",
            result="BLOCKED",
            approved=False,
            details={"source": source},
        )
    except Exception:
        pass
    return doc


def assert_privileged_action(root: Path, action: str) -> Tuple[bool, Dict[str, Any]]:
    doc = check_privileged_action(root, action)
    return bool(doc.get("ok")), doc


def sovereignty_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    policy = load_policy(root)
    mandate = load_mandate(root)
    source = detect_invocation_source()
    return {
        "schema_version": 1,
        "source": source,
        "policy_id": policy.get("policy_id"),
        "principle_de": policy.get("principle_de"),
        "authority_chain_de": policy.get("authority_chain_de") or [],
        "mandate_active": _mandate_valid(mandate, "*") if mandate else False,
        "mandate_expires_at_utc": (mandate or {}).get("expires_at_utc"),
        "mandate_actions": (mandate or {}).get("authorized_actions"),
        "privileged_actions": sorted(PRIVILEGED_ACTIONS),
        "headline_de": (
            "Souveränität aktiv — externe Linux-Eingriffe an privilegierten Aktionen blockiert"
            if policy.get("fail_closed", True)
            else "Souveränität — Policy prüfen"
        ),
        "ok": True,
    }
