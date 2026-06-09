#!/usr/bin/env python3
"""One-shot strategic M1 setup: sleep guard, outage repair, matrix or finish path."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_bootstrap(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    from tools.r0_migration_hw import prevent_sleep_off, prevent_sleep_on
    from tools.r0_migration_phase_guard import is_phase_sealed

    out: Dict[str, Any] = {"dry_run": dry_run}
    if not dry_run:
        out["prevent_sleep"] = prevent_sleep_on()

    if is_phase_sealed(root, "M1"):
        out["action"] = "M1_ALREADY_SEALED"
        if not dry_run:
            out["prevent_sleep_restore"] = prevent_sleep_off()
        return out

    if dry_run:
        out["action"] = "DRY_RUN"
        return out

    from tools.r0_migration_finish_push import run_finish_push
    from tools.r0_migration_active_scope import sync_program_focus

    sync_program_focus(root)
    push = run_finish_push(root)
    out["finish_push"] = push
    out["action"] = f"FINISH_PUSH_{push.get('verdict', 'UNKNOWN')}"
    out["scope_doc"] = "docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md"
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Strategic R0 M1 bootstrap.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    result = run_bootstrap(ROOT, dry_run=args.dry_run)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"action={result.get('action')}")
        if result.get("note"):
            print(f"note={result.get('note')}")
    action = str(result.get("action") or "")
    if action.startswith("FINISH_PUSH_HOLD") or action.startswith("FINISH_PUSH_M1_ALREADY"):
        return 0
    if action.startswith("FINISH_PUSH_SEALED"):
        return 0
    if action.endswith("FAILED"):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
