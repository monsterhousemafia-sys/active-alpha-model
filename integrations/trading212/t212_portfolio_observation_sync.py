"""Optional Trading 212 demo portfolio observation sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from aa_safe_io import atomic_write_json
from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_demo_readonly_client import T212DemoReadOnlyClient, T212DemoReadOnlyError


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_demo_observation(root: Path) -> Dict[str, Any]:
    root = Path(root)
    creds = load_credentials()
    if creds is None:
        return {
            "status": "AWAITING_OPTIONAL_CREDENTIAL_CONFIGURATION_NON_BLOCKING",
            "connected": False,
            "simulation_only": True,
        }
    client = T212DemoReadOnlyClient(creds)
    try:
        summary = client.get_account_summary()
        positions = client.get_positions()
        payload = {
            "status": "DEMO_READ_ONLY_SYNC_ACTIVE",
            "connected": True,
            "synced_at_utc": _utc_now(),
            "account_summary": summary,
            "positions": positions,
            "environment": "DEMO_ONLY",
            "read_only": True,
            "broker_order_sent": False,
        }
    except T212DemoReadOnlyError as exc:
        payload = {
            "status": "BLOCKED_BY_ENVIRONMENT_GUARD",
            "connected": False,
            "error": str(exc),
        }
    ledger = root / "paper/p14/t212_sync_audit_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({**payload, "recorded_at_utc": _utc_now()}, default=str) + "\n")
    atomic_write_json(root / "control/p14_trading212_demo_health.json", payload)
    return payload
