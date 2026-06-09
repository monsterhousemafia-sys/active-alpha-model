#!/usr/bin/env python3
"""Headless Windows Task Scheduler worker for R0 migration M1 (no prompts)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOG_PATH = ROOT / "evidence" / "r0_migration" / "scheduled_worker.log"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _append_log(line: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(f"{_utc_now()} {line}\n")


def run_worker(root: Path, *, dry_run: bool = False) -> Dict[str, Any]:
    race = root / "control" / "r0_migration" / "m1_race_mode.json"
    if race.is_file() and not dry_run:
        result = {"started_at_utc": _utc_now(), "action": "SKIP_RACE_MODE", "dry_run": dry_run}
        _append_log(f"SKIP_RACE_MODE {json.dumps(result, default=str)}")
        return result

    from aa_runtime_profile import is_batch_work_active
    from tools.r0_migration_outage_guard import run_outage_check
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase

    result: Dict[str, Any] = {"started_at_utc": _utc_now(), "dry_run": dry_run}
    if dry_run:
        recovery = {"unblocked": True, "snapshot": {"m1_blockers": []}}
    else:
        recovery = run_outage_check(root, repair=True)
    snap = recovery.get("snapshot") or {}
    result["recovery"] = {
        "unblocked": recovery.get("unblocked", snap.get("batch_active") is False),
        "batch_active": snap.get("batch_active"),
        "m1_blockers": snap.get("m1_blockers"),
        "stall": recovery.get("stall"),
    }

    if is_phase_sealed(root, "M1"):
        result["action"] = "DONE_M1_SEALED"
        _append_log(f"DONE_M1_SEALED {json.dumps(result, default=str)}")
        return result

    from tools.r0_migration_runtime import matrix_work_in_progress

    if matrix_work_in_progress(root):
        result["action"] = "SKIP_MATRIX_ALREADY_RUNNING"
        _append_log(f"SKIP_MATRIX_ALREADY_RUNNING {json.dumps(result, default=str)}")
        return result

    from tools.run_r0_migration_phase_m1 import build_returns_manifest, run_m1

    manifest = build_returns_manifest(root)
    if manifest.get("all_m1_variants_integrity_pass"):
        result["action"] = "REFRESH_AND_SEAL"
        if dry_run:
            result["note"] = "would run_m1 refresh + seal M1"
            _append_log(f"DRY_RUN_REFRESH_AND_SEAL {json.dumps(result, default=str)}")
            return result
        m1_out = run_m1(apply_env_fix=False)
        result["m1_status"] = m1_out.get("m1_status")
        seal = try_seal_phase(root, "M1")
        result["seal"] = seal
        result["action"] = "DONE_M1_SEALED" if seal.get("status") == "SEALED" else "REFRESH_DONE_SEAL_FAILED"
        _append_log(f"{result['action']} {json.dumps(result, default=str)}")
        return result

    result["action"] = "FINISH_PUSH"
    if dry_run:
        result["note"] = "would run finish_push (hold / commander / seal)"
        _append_log(f"DRY_RUN_FINISH_PUSH {json.dumps(result, default=str)}")
        return result

    from tools.r0_migration_finish_push import run_finish_push

    push = run_finish_push(root)
    result["finish_push"] = push
    result["action"] = f"FINISH_PUSH_{push.get('verdict', 'UNKNOWN')}"
    _append_log(f"{result['action']} {json.dumps(result, default=str)}")
    return result


def main() -> int:
    p = argparse.ArgumentParser(description="R0 M1 scheduled worker (Task Scheduler, no UI).")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()
    try:
        result = run_worker(ROOT, dry_run=args.dry_run)
    except Exception as exc:
        _append_log(f"ERROR {exc!r}")
        print(str(exc), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"action={result.get('action')}")
    action = str(result.get("action") or "")
    if action in ("DONE_M1_SEALED", "SKIP_MATRIX_ALREADY_RUNNING"):
        return 0
    if action == "REFRESH_DONE_SEAL_FAILED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
