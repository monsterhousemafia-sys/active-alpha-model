#!/usr/bin/env python3
"""M1 autopilot — thin wrapper around finish_push (no duplicate matrix starts)."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

HANDOFF = ROOT / "control" / "r0_migration" / "autopilot_handoff.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def run_autopilot(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_active_scope import sync_program_focus
    from tools.r0_migration_finish_push import run_finish_push
    from tools.r0_migration_m1_control import M1_ENTRY_BAT, m1_hints

    sync_program_focus(root)
    push = run_finish_push(root)
    out: Dict[str, Any] = {
        "started_at_utc": _utc_now(),
        "status": f"FINISH_PUSH_{push.get('verdict', 'UNKNOWN')}",
        "finish_push": push,
        "hints": m1_hints(),
        "primary_entry": M1_ENTRY_BAT,
    }
    atomic_write_handoff(root, out)
    return out


def atomic_write_handoff(root: Path, payload: Dict[str, Any]) -> None:
    from aa_safe_io import atomic_write_json

    payload["updated_at_utc"] = _utc_now()
    atomic_write_json(root / HANDOFF.relative_to(root), payload)


def main() -> int:
    result = run_autopilot(ROOT)
    print(json.dumps(result, indent=2, default=str))
    verdict = str((result.get("finish_push") or {}).get("verdict") or "")
    ok = verdict in (
        "HOLD_LIVE_MATRIX",
        "RESET_AND_STARTED_MATRIX",
        "SEALED",
        "M1_ALREADY_SEALED",
        "COMMANDER",
    ) or str(result.get("status", "")).startswith("FINISH_PUSH_")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
