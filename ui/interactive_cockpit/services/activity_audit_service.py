"""Activity audit log for interactive cockpit transparency."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _log_path(root: Path) -> Path:
    p = root / "live_pilot/activity/activity_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def log_activity(
    root: Path,
    *,
    category: str,
    action: str,
    result: str,
    status: str = "ERFOLGREICH",
    source: str = "SYSTEM",
    details: Optional[Dict[str, Any]] = None,
    amounts_eur: Optional[float] = None,
    instruments: Optional[List[str]] = None,
    user_action_required: bool = False,
) -> Dict[str, Any]:
    entry = {
        "id": str(uuid.uuid4()),
        "timestamp_utc": _utc_now(),
        "category": category,
        "action": action,
        "source": source,
        "result": result,
        "status": status,
        "amounts_eur": amounts_eur,
        "instruments": instruments or [],
        "user_action_required": user_action_required,
        "details": details or {},
        "real_order_capability": False,
    }
    with _log_path(root).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def load_recent_activities(root: Path, limit: int = 50) -> List[Dict[str, Any]]:
    path = _log_path(root)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return list(reversed(out))


def planned_next_actions(root: Path, state: Dict[str, Any]) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    broker = state.get("broker") or {}
    if broker.get("status") == "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI":
        actions.append(
            {
                "title": "Trading 212 Read-Only einrichten",
                "purpose": "Reale Kontodaten für Investitionsübersicht und Trigger",
                "execution_type": "Nutzerkonfiguration in GUI",
                "status": "WARTET AUF NUTZER",
                "real_money_impact": "NEIN — KEINE ORDERFÄHIGKEIT",
            }
        )
    trigger = state.get("trigger") or {}
    if trigger.get("trigger_status") == "INACTIVE_REALIZED_NET_PROFIT_BELOW_50_EUR":
        actions.append(
            {
                "title": "Realisierten Gewinn über 50 EUR beobachten",
                "purpose": "Intraday Paper/Research Freischaltung",
                "execution_type": "Read-only Reconciliation",
                "status": "LAUFEND",
                "real_money_impact": "NEIN",
            }
        )
    return actions
