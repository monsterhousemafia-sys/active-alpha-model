"""Trading 212 live read-only account state sync."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from integrations.trading212.t212_credentials_loader import load_credentials
from integrations.trading212.t212_live_readonly_client import T212LiveReadOnlyClient


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_live_readonly_account(root: Path) -> Dict[str, Any]:
    root = Path(root)
    out_dir = root / "live_pilot/manual_execution/readonly_real_account_state"
    out_dir.mkdir(parents=True, exist_ok=True)

    creds = load_credentials()
    if not creds or not creds.configured:
        return {
            "status": "AWAITING_SECURE_LOCAL_CREDENTIAL_CONFIGURATION",
            "credentials_configured": False,
            "account_cash_verified": False,
        }

    try:
        client = T212LiveReadOnlyClient(creds)
        summary = client.get_account_summary()
        result = {
            "status": "LIVE_READ_ONLY_ACCOUNT_OBSERVED",
            "credentials_configured": True,
            "account_cash_verified": True,
            "summary_redacted": {k: v for k, v in summary.items() if "secret" not in k.lower()},
            "observed_at_utc": _utc_now(),
        }
        (out_dir / "live_account_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result
    except Exception as exc:
        return {
            "status": "LIVE_READ_ONLY_SYNC_FAILED",
            "credentials_configured": True,
            "account_cash_verified": False,
            "error": str(exc)[:200],
        }
