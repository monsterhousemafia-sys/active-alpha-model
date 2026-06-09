"""Trading 212 read-only trade history sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_live_readonly_trade_history(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / "live_pilot/manual_execution/readonly_real_trade_history"
    out_dir.mkdir(parents=True, exist_ok=True)

    creds = load_credentials()
    if not creds or not creds.configured:
        result = {
            "trades": [],
            "verified": False,
            "status": "AWAITING_CREDENTIALS",
            "observed_at_utc": _utc_now(),
        }
        (out_dir / "latest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    trades: List[Dict[str, Any]] = []
    status = "FAILED"
    try:
        client = T212LiveReadOnlyClient(creds)
        for endpoint in ("/equity/history/orders", "/equity/history/transactions"):
            try:
                payload = client.get(endpoint)
                if isinstance(payload, list):
                    trades.extend(payload)
                elif isinstance(payload, dict):
                    trades.extend(payload.get("items") or payload.get("data") or [])
            except PermissionError:
                continue
            except Exception:
                continue
        status = "VERIFIED" if trades else "EMPTY"
        result = {
            "trades": trades,
            "verified": True,
            "status": status,
            "observed_at_utc": _utc_now(),
        }
    except Exception as exc:
        result = {
            "trades": [],
            "verified": False,
            "status": "FAILED",
            "error": str(exc)[:200],
            "observed_at_utc": _utc_now(),
        }

    (out_dir / "latest.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
