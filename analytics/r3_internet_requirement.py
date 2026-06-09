"""Internet-Pflicht für R3 und Active Alpha Model — gemeinsamer Probe + Evidence."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_POLICY_REL = Path("control/r3_internet_requirement_policy.json")
_EVIDENCE_REL = Path("evidence/r3_internet_latest.json")
_MAX_EVIDENCE_AGE_S = 300


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


def load_internet_policy(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _POLICY_REL)


def probe_internet_stack(*, timeout_s: float = 8.0) -> Dict[str, Any]:
    """Kombinierter Check: Yahoo/SPY + generischer DNS-Fallback."""
    probes: List[Dict[str, Any]] = []
    prices_ok = False
    generic_ok = False
    try:
        from aa_adaptive_runtime import probe_internet_prices

        prices_ok = bool(probe_internet_prices(timeout_s=timeout_s))
        probes.append({"id": "price_feed", "ok": prices_ok})
    except Exception as exc:
        probes.append({"id": "price_feed", "ok": False, "error_de": str(exc)[:80]})
    try:
        from analytics.r3_ki_web import probe_internet_generic

        generic_ok = bool(probe_internet_generic(timeout_s=min(timeout_s, 4.0)))
        probes.append({"id": "generic", "ok": generic_ok})
    except Exception as exc:
        probes.append({"id": "generic", "ok": False, "error_de": str(exc)[:80]})
    internet_ok = prices_ok or generic_ok
    return {
        "internet_ok": internet_ok,
        "price_feed_ok": prices_ok,
        "generic_ok": generic_ok,
        "probes": probes,
    }


def probe_and_record_internet(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    policy = load_internet_policy(root)
    probe = probe_internet_stack()
    internet_ok = bool(probe.get("internet_ok"))
    doc: Dict[str, Any] = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "headline_de": str(policy.get("headline_de") or "Internet erforderlich"),
        "internet_ok": internet_ok,
        "price_feed_ok": probe.get("price_feed_ok"),
        "generic_ok": probe.get("generic_ok"),
        "probes": probe.get("probes") or [],
        "required_for_de": list((policy.get("required_consumers_de") or {}).keys()),
        "confirmation_de": (
            "✓ Internet OK — R3 und Active Alpha Model können rechnen"
            if internet_ok
            else "✗ Kein Internet — R3 und Active Alpha Model pausiert"
        ),
        "message_de": (
            "Internet verfügbar"
            if internet_ok
            else "Kein Internet — Kurse, T212-Sync und Engine-Tick blockiert"
        ),
        "policy_ref": str(_POLICY_REL).replace("\\", "/"),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def load_internet_status(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)


def _evidence_age_seconds(status: Dict[str, Any]) -> Optional[float]:
    raw = str(status.get("updated_at_utc") or "").strip()
    if not raw:
        return None
    try:
        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds()
    except ValueError:
        return None


def require_internet_for(root: Path, *, consumer: str) -> Dict[str, Any]:
    """Fail-closed Gate — consumer: r3 | alpha_engine | both."""
    root = Path(root)
    status = load_internet_status(root)
    age = _evidence_age_seconds(status) if status else None
    stale = age is None or age > _MAX_EVIDENCE_AGE_S
    if not status or status.get("updated_at_utc") is None or stale or not status.get("internet_ok"):
        status = probe_and_record_internet(root, persist=True)
    internet_ok = bool(status.get("internet_ok"))
    allowed = internet_ok
    return {
        "allowed": allowed,
        "internet_ok": internet_ok,
        "consumer": consumer,
        "error": None if allowed else "INTERNET_REQUIRED",
        "message_de": (
            status.get("message_de")
            if not allowed
            else f"Internet OK — {consumer}"
        ),
        "confirmation_de": status.get("confirmation_de"),
        "evidence_ref": str(_EVIDENCE_REL).replace("\\", "/"),
    }


def internet_step_blocked(step: str, gate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "step": step,
        "ok": False,
        "skipped": True,
        "reason_de": "internet_required",
        "internet_ok": False,
        "detail_de": str(gate.get("message_de") or "Kein Internet")[:120],
    }
