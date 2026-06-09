"""Managed live trading baseline and scope (full T212 cash, no pilot cap)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _dir(root: Path) -> Path:
    d = root / "live_pilot/confirmed_execution"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_baseline(root: Path) -> Dict[str, Any]:
    p = _dir(root) / "live_pilot_baseline.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def load_managed_scope(root: Path) -> Dict[str, Any]:
    p = _dir(root) / "managed_scope_policy.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"managed_instruments": [], "authorized_capital_eur": 0.0, "reserve_eur": 0.0}


def create_baseline(
    root: Path,
    *,
    account_currency: str,
    available_cash: Optional[float],
    positions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    payload = {
        "baseline_timestamp_utc": _utc_now(),
        "account_currency": account_currency,
        "available_cash": available_cash,
        "positions_snapshot": positions,
    }
    h = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    baseline = {**payload, "baseline_hash_sha256": h}
    atomic_write_json(_dir(root) / "live_pilot_baseline.json", baseline)
    atomic_write_json(_dir(root) / "baseline_audit_manifest.json", {"baseline_hash": h, "created_at_utc": _utc_now()})

    pre_existing = []
    for pos in positions:
        pre_existing.append({**pos, "classification": "REAL_PRE_EXISTING_DISPLAY_ONLY"})
    atomic_write_json(_dir(root) / "pre_existing_positions_registry.json", {"entries": pre_existing})
    return baseline


def set_managed_scope(
    root: Path,
    *,
    managed_instruments: List[str],
    authorized_capital_eur: float = 0.0,
    reserve_eur: float = 0.0,
) -> Dict[str, Any]:
    cap = max(0.0, float(authorized_capital_eur or 0))
    scope = {
        "managed_instruments": sorted(set(managed_instruments)),
        "authorized_capital_eur": cap,
        "reserve_eur": max(0.0, float(reserve_eur or 0)),
        "updated_at_utc": _utc_now(),
        "live_trading_active": True,
    }
    atomic_write_json(_dir(root) / "managed_scope_policy.json", scope)
    managed = [{"symbol": s, "classification": "REAL_CONFIRMED_CORE_LIVE_ORDER"} for s in scope["managed_instruments"]]
    atomic_write_json(_dir(root) / "managed_positions_registry.json", {"entries": managed})
    return scope


def is_instrument_managed(root: Path, symbol: str) -> bool:
    scope = load_managed_scope(root)
    return symbol.upper() in {s.upper() for s in scope.get("managed_instruments") or []}


def baseline_exists(root: Path) -> bool:
    return (_dir(root) / "live_pilot_baseline.json").is_file()
