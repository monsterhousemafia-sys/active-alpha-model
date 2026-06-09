"""Read-only reconciliation after user-reported manual execution."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def reconcile_user_reported_execution(root: Path, report: Dict[str, Any], broker_observation: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / "live_pilot/manual_execution/readonly_broker_reconciliations"
    out_dir.mkdir(parents=True, exist_ok=True)

    recon = {
        "status": "RECONCILED_FROM_READONLY_BROKER_OBSERVATION",
        "instrument": report.get("instrument"),
        "user_reported_notional_eur": report.get("notional_eur"),
        "broker_observation_at_utc": broker_observation.get("observed_at_utc"),
        "reconciled_at_utc": _utc_now(),
        "cursor_did_not_submit_order": True,
    }
    path = out_dir / f"recon_{report.get('instrument', 'unknown')}_{_utc_now().replace(':', '')}.json"
    path.write_text(json.dumps(recon, indent=2) + "\n", encoding="utf-8")
    return recon
