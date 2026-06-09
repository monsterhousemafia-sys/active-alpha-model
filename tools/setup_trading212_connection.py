#!/usr/bin/env python3
"""Verify Trading 212 API connectivity (read-only by default)."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from aa_safe_io import atomic_write_json
from research.p13.broker_adapter import get_broker_adapter
from research.p13.brokers.trading212_config import load_trading212_config
from research.p13.constants import TRADING212_STATUS_REL


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description="Test Trading 212 read-only API connection")
    parser.add_argument("--env-file", default=str(_REPO / ".env"), help="Optional .env path")
    args = parser.parse_args()

    _load_env_file(Path(args.env_file))
    cfg = load_trading212_config()
    root = _REPO

    if cfg is None:
        print(
            json.dumps(
                {
                    "status": "NOT_CONFIGURED",
                    "message": "Set TRADING212_API_KEY and TRADING212_API_SECRET in .env (see .env.trading212.example)",
                },
                indent=2,
            )
        )
        return 1

    adapter = get_broker_adapter(root)
    state = adapter.read_only_account_state()
    payload = {
        "checked_at_utc": _utc_now(),
        "environment": cfg.environment,
        "read_only": cfg.read_only,
        "allow_live_orders": cfg.allow_live_orders,
        "account_state": state,
        "connected": bool(state.get("account_connected")),
        "real_order_routing": cfg.allow_live_orders and not cfg.read_only,
    }
    out_path = root / TRADING212_STATUS_REL
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_path, payload)
    print(json.dumps(payload, indent=2))
    return 0 if payload["connected"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
