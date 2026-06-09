#!/usr/bin/env python3
"""Keep M1 status artifacts consistent (phase_status, completion_summary, health)."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_evidence_schema import AUTHORITATIVE_CHAMPION
from aa_safe_io import atomic_write_json

EVIDENCE_DIR = Path("evidence") / "r0_migration"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sync_m1_status_artifacts(root: Path, *, blockers: List[str] | None = None) -> Dict[str, Any]:
    from tools.r0_migration_crash_guard import _m1_blockers, reconcile_m1_phase_status
    from tools.r0_migration_phase_guard import is_phase_sealed
    from tools.run_r0_migration_phase_m1 import build_returns_manifest

    if blockers is None:
        blockers = _m1_blockers(root)
    manifest = build_returns_manifest(root)
    returns_ok = bool(manifest.get("all_m1_variants_integrity_pass"))
    if is_phase_sealed(root, "M1"):
        status = "SEALED"
    elif returns_ok and not blockers:
        status = "READY_TO_SEAL"
    elif blockers:
        status = "IN_PROGRESS"
    else:
        status = "COMPLETE_WITH_BLOCKER"

    summary = {
        "phase": "M1",
        "status": status,
        "completed_at_utc": _utc_now(),
        "blockers": blockers,
        "returns_complete": returns_ok,
        "authoritative_champion_unchanged": AUTHORITATIVE_CHAMPION,
        "synced_by": "tools/r0_migration_status_sync.py",
    }
    atomic_write_json(root / EVIDENCE_DIR / "m1_completion_summary.json", summary)
    phase = reconcile_m1_phase_status(root)
    from tools.r0_migration_active_scope import sync_program_focus

    program = sync_program_focus(root)
    return {
        "m1_completion_summary": summary,
        "phase_status_m1": (phase.get("phases") or {}).get("M1"),
        "program_focus": program,
    }
