"""T212-Konto-Identität — Fingerabdruck, Label, Bestätigung (fail-closed bei Wechsel)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_safe_io import atomic_write_json

_CONFIRMED_REL = Path("control/r3_t212_confirmed_account.json")
_SCOPE_REL = Path("control/authorization/t212_new_account_scope.json")


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


def credentials_fingerprint(root: Path) -> Optional[str]:
    root = Path(root)
    try:
        from integrations.trading212.t212_credentials_loader import load_credentials

        creds = load_credentials(root)
        if creds is None or not getattr(creds, "api_key", None):
            return None
        key = str(creds.api_key).strip()
        if not key:
            return None
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return None


def account_fingerprint(broker: Dict[str, Any]) -> Optional[str]:
    if not broker.get("credentials_configured"):
        return None
    summary = broker.get("account_summary") if isinstance(broker.get("account_summary"), dict) else {}
    total = summary.get("totalValue")
    try:
        total_s = f"{float(total):.2f}" if total is not None else "0.00"
    except (TypeError, ValueError):
        total_s = "0.00"
    parts = [
        str(broker.get("environment") or ""),
        str(summary.get("currency") or "EUR"),
        total_s,
        str(int(broker.get("positions_count") or 0)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def account_label(broker: Dict[str, Any]) -> str:
    env = str(broker.get("environment") or "—").replace("_", " ")
    summary = broker.get("account_summary") if isinstance(broker.get("account_summary"), dict) else {}
    currency = str(summary.get("currency") or "EUR")
    total = summary.get("totalValue")
    try:
        total_bit = f" · {float(total):.0f} {currency}" if total is not None else ""
    except (TypeError, ValueError):
        total_bit = ""
    positions = int(broker.get("positions_count") or 0)
    pos_bit = f" · {positions} Pos." if positions else ""
    return f"T212 {env}{total_bit}{pos_bit}".strip()


def connection_label(broker: Dict[str, Any], *, fingerprint: Optional[str] = None) -> str:
    fp = fingerprint or account_fingerprint(broker) or "—"
    return f"{account_label(broker)} · #{fp[:8]}"


def load_confirmed_account(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _CONFIRMED_REL)


def confirm_t212_account(root: Path, *, bond: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    if bond is None:
        from analytics.r3_t212_api_bond import build_r3_t212_api_bond

        bond = build_r3_t212_api_bond(root, persist=False)
    fp = bond.get("account_fingerprint")
    if not fp:
        return {
            "ok": False,
            "reason_de": "Kein T212-Konto erkennbar — zuerst Sync (GET /api/r3/t212?sync=1)",
        }
    doc = {
        "schema_version": 1,
        "confirmed_at_utc": _utc_now(),
        "account_fingerprint": fp,
        "account_label": bond.get("account_label"),
        "connection_label": bond.get("connection_label"),
        "environment": bond.get("environment"),
        "credentials_fingerprint": bond.get("credentials_fingerprint"),
        "approval_ref": str(_load_json(root / _SCOPE_REL).get("approval_ref") or ""),
    }
    atomic_write_json(root / _CONFIRMED_REL, doc)
    return {"ok": True, **doc}


def assess_account_confirmation(root: Path, *, bond: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    root = Path(root)
    if bond is None:
        bond = _load_json(root / Path("evidence/r3_t212_api_bond_latest.json"))
    fp = bond.get("account_fingerprint")
    label = str(bond.get("account_label") or account_label(bond))
    confirmed = load_confirmed_account(root)
    if not fp:
        return {
            "needs_confirmation": True,
            "account_confirmed": False,
            "message_de": "T212-Konto nicht erkannt — Sync prüfen",
        }
    if not confirmed.get("account_fingerprint"):
        return {
            "needs_confirmation": True,
            "account_confirmed": False,
            "message_de": f"Neues T212-Konto — bitte bestätigen ({label})",
            "confirm_api_de": "GET /api/r3/t212?confirm_account=1",
        }
    if fp != confirmed.get("account_fingerprint"):
        return {
            "needs_confirmation": True,
            "account_confirmed": False,
            "message_de": f"Konto gewechselt ({label}) — bitte erneut bestätigen",
            "prior_label": confirmed.get("account_label"),
            "confirm_api_de": "GET /api/r3/t212?confirm_account=1",
        }
    return {
        "needs_confirmation": False,
        "account_confirmed": True,
        "message_de": f"Konto bestätigt · {label}",
        "confirmed_at_utc": confirmed.get("confirmed_at_utc"),
    }
