"""Trading 212 live read-only positions sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_live_readonly_positions(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / "live_pilot/manual_execution/readonly_real_positions"
    out_dir.mkdir(parents=True, exist_ok=True)

    creds = load_credentials()
    if not creds or not creds.configured:
        return {"positions_verified": False, "status": "AWAITING_CREDENTIALS"}

    try:
        client = T212LiveReadOnlyClient(creds)
        positions = client.get_positions()
        result = {
            "positions_verified": True,
            "position_count": len(positions) if isinstance(positions, list) else 0,
            "observed_at_utc": _utc_now(),
        }
        (out_dir / "positions_snapshot.json").write_text(json.dumps({"meta": result, "positions": positions}, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        return {"positions_verified": False, "status": "FAILED", "error": str(exc)[:200]}
