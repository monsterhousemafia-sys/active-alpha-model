"""T212 Trust — quantifizierte Evidence (Zahlen + Schwellen, fail-closed)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

from integrations.trading212.t212_trust_gate import (
    assess_t212_trust_from_root,
    load_trust_policy,
    sync_age_seconds,
)

_EVIDENCE_REL = Path("evidence/t212_trust_quantified_latest.json")

_UNTRUSTED_STATUSES = frozenset(
    {
        "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI",
        "CONNECTION_FAILED_RETRY_AVAILABLE",
        "CREDENTIALS_EXPIRED_SHOWING_CACHED_DATA",
        "CACHED_READONLY_DATA",
        "RATE_LIMITED_SHOWING_CACHED_DATA",
    }
)
_TRUSTED_LIVE_STATUSES = frozenset(
    {
        "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "DEMO_READONLY_CONNECTED",
    }
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


def _criterion(
    *,
    id_: str,
    label_de: str,
    required_de: str,
    actual: Any,
    passed: bool,
    detail_de: str = "",
) -> Dict[str, Any]:
    return {
        "id": id_,
        "label_de": label_de,
        "required_de": required_de,
        "actual": actual,
        "passed": passed,
        "detail_de": detail_de,
    }


def build_t212_trust_quantified(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    """Zahlenbasierte Begründung warum T212 trusted/untrusted ist."""
    root = Path(root)
    policy = load_trust_policy(root)
    trust = assess_t212_trust_from_root(root, persist=persist)
    bond = _load_json(root / "evidence/r3_t212_api_bond_latest.json")
    learn = _load_json(root / "evidence/t212_learning_sync_latest.json")
    cash_align = _load_json(root / "evidence/t212_cash_alignment_latest.json")
    throttle = _load_json(
        root / "live_pilot/manual_execution/readonly_real_account_state/sync_throttle.json"
    )

    max_stale = int(policy.get("max_stale_sync_s") or 900)
    max_display = int(policy.get("max_stale_display_s") or 1800)

    creds_ok = bool(bond.get("credentials_configured") or trust.get("broker_status"))
    status = str(bond.get("broker_status") or trust.get("broker_status") or "")
    sync_utc = bond.get("last_sync_utc") or trust.get("last_sync_utc") or learn.get("last_sync_utc")
    age = sync_age_seconds(sync_utc)
    cash_live = trust.get("cash_eur")
    cash_cached = learn.get("cash_eur") or cash_align.get("stored_cash_eur")

    criteria: List[Dict[str, Any]] = [
        _criterion(
            id_="credentials",
            label_de="API-Zugang konfiguriert",
            required_de="credentials_configured = true",
            actual=bool(bond.get("credentials_configured")),
            passed=bool(bond.get("credentials_configured")),
        ),
        _criterion(
            id_="broker_status",
            label_de="Broker-Status vertrauenswürdig",
            required_de=f"status ∉ {sorted(_UNTRUSTED_STATUSES)}",
            actual=status or None,
            passed=bool(status) and status not in _UNTRUSTED_STATUSES,
            detail_de=str(bond.get("message_de") or trust.get("reason_de") or "")[:200],
        ),
        _criterion(
            id_="live_status",
            label_de="Live-Readonly-Monitoring aktiv",
            required_de=f"status ∈ {sorted(_TRUSTED_LIVE_STATUSES)}",
            actual=status or None,
            passed=status in _TRUSTED_LIVE_STATUSES,
        ),
        _criterion(
            id_="sync_present",
            label_de="Erfolgreicher Sync vorhanden",
            required_de="last_sync_utc ≠ null",
            actual=sync_utc,
            passed=bool(sync_utc),
        ),
        _criterion(
            id_="sync_fresh",
            label_de="Sync frisch genug für Orders",
            required_de=f"sync_age_s ≤ {max_stale}",
            actual=round(age, 1) if age is not None else None,
            passed=age is not None and age <= max_stale,
            detail_de=f"Schwelle Orders: {max_stale}s ({max_stale // 60} min)",
        ),
        _criterion(
            id_="sync_display",
            label_de="Sync frisch genug für Cash-Anzeige",
            required_de=f"sync_age_s ≤ {max_display}",
            actual=round(age, 1) if age is not None else None,
            passed=age is not None and age <= max_display,
            detail_de=f"Schwelle Anzeige: {max_display}s ({max_display // 60} min)",
        ),
        _criterion(
            id_="cash_live",
            label_de="Live-Kontostand (nicht nur Cache)",
            required_de="cash_eur ≠ null aus frischem Sync",
            actual=cash_live,
            passed=cash_live is not None and trust.get("trusted") is True,
            detail_de=f"Cache-Referenz (nicht für Orders): {cash_cached} EUR" if cash_cached else "",
        ),
    ]

    passed_n = sum(1 for c in criteria if c["passed"])
    failed = [c for c in criteria if not c["passed"]]

    verdict_de = (
        f"T212 vertrauenswürdig — {passed_n}/{len(criteria)} Kriterien erfüllt"
        if trust.get("trusted")
        else f"T212 nicht vertrauenswürdig — {len(failed)} Blocker, {passed_n}/{len(criteria)} Kriterien"
    )

    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "trusted": bool(trust.get("trusted")),
        "fail_closed": bool(policy.get("fail_closed", True)),
        "orders_allowed": bool(trust.get("orders_allowed")),
        "plan_capital_allowed": bool(trust.get("plan_capital_allowed")),
        "reason_code": trust.get("reason_code"),
        "reason_de": trust.get("reason_de"),
        "message_de": trust.get("message_de"),
        "verdict_de": verdict_de,
        "policy": {
            "max_stale_sync_s": max_stale,
            "max_stale_display_s": max_display,
            "block_orders_when_untrusted": bool(policy.get("block_orders_when_untrusted", True)),
            "block_plan_scaling_when_untrusted": bool(policy.get("block_plan_scaling_when_untrusted", True)),
            "ref": "control/t212_trust_policy.json",
        },
        "measurements": {
            "broker_status": status or None,
            "last_sync_utc": sync_utc,
            "sync_age_s": round(age, 1) if age is not None else None,
            "cash_eur_live": cash_live,
            "cash_eur_cached_ref": cash_cached,
            "positions_count": trust.get("positions_count") or bond.get("positions_count"),
            "connected": bond.get("connected"),
            "bonded": bond.get("bonded"),
            "rate_limit_wait_s": _parse_rate_limit_wait(bond.get("message_de") or ""),
            "last_sync_attempt_utc": throttle.get("last_sync_attempt_utc"),
            "learning_stale_cache": learn.get("stale_cache"),
            "learning_last_error": (learn.get("steps") or [{}])[0].get("last_error", "")[:160]
            if learn.get("steps")
            else None,
        },
        "criteria": criteria,
        "blockers_de": [f"{c['label_de']}: {c['required_de']} — ist {c['actual']}" for c in failed],
        "consequence_de": (
            "Orders und Plan-Skalierung blockiert (fail-closed)."
            if not trust.get("trusted")
            else "Live-Cash und Read-only-Monitoring für Planung freigegeben."
        ),
        "refs": [
            "evidence/t212_trust_latest.json",
            "evidence/r3_t212_api_bond_latest.json",
            "integrations/trading212/t212_trust_gate.py",
        ],
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _parse_rate_limit_wait(message: str) -> Optional[int]:
    import re

    m = re.search(r"(\d+)\s*Sekunden", message or "")
    return int(m.group(1)) if m else None
