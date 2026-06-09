"""Trading 212 live read-only cash observation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_live_readonly_cash(root: Path) -> Dict[str, Any]:
    root = Path(root)
    creds = load_credentials()
    if not creds or not creds.configured:
        return {"available_cash_eur": None, "verified": False, "status": "AWAITING_CREDENTIALS"}

    try:
        client = T212LiveReadOnlyClient(creds)
        cash = client.get("/equity/account/cash")
        from integrations.trading212.t212_cash_parser import parse_cash_breakdown

        breakdown = parse_cash_breakdown(cash)
        available = breakdown.planning_cash_eur
        result = {
            "available_cash_eur": available,
            "cash_breakdown": breakdown.to_dict(),
            "verified": available is not None,
            "status": "VERIFIED" if available is not None else "PARTIAL",
            "observed_at_utc": _utc_now(),
        }
        out = root / "live_pilot/manual_execution/readonly_real_account_state/cash_observation.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        return {"available_cash_eur": None, "verified": False, "status": "FAILED", "error": str(exc)[:200]}
