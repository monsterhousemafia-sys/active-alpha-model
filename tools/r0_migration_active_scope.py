#!/usr/bin/env python3
"""M1-only execution scope until M1 phase seal (trading path step 1)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
SCOPE_PATH = ROOT / "control" / "r0_migration" / "m1_active_scope.json"

BLOCKED_AFTER_M1 = [
    "M2",
    "M3",
    "M4",
    "M5",
    "M6",
    "M7",
    "M8",
    "M9",
    "M10",
    "M11",
    "M12",
]


def load_active_scope(root: Path = ROOT) -> Dict[str, Any]:
    p = root / SCOPE_PATH.relative_to(ROOT)
    if not p.is_file():
        return {"execution_focus": "M1_ONLY_UNTIL_SEALED", "current_execution_phase": "M1"}
    return json.loads(p.read_text(encoding="utf-8"))


def phase_allowed_before_m1_seal(phase: str) -> bool:
    return str(phase).upper() in ("M0", "M1")


def assert_m1_sealed_for_phase(root: Path, phase: str) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import is_phase_sealed

    phase = str(phase).upper()
    if phase_allowed_before_m1_seal(phase):
        return {"allowed": True, "phase": phase, "reason": "m0_or_m1"}
    if is_phase_sealed(root, "M1"):
        return {"allowed": True, "phase": phase, "reason": "m1_sealed"}
    return {
        "allowed": False,
        "phase": phase,
        "reason": "M1_NOT_SEALED",
        "blocked_by": "m1_active_scope",
        "scope_doc": "docs/R0_MIGRATION_M1_ACTIVE_SCOPE.md",
        "next": "complete_m1_then_seal",
    }


def sync_program_focus(root: Path) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_phase_guard import is_phase_sealed

    scope = load_active_scope(root)
    focus = "M1_IN_PROGRESS"
    next_phase = "M1"
    if is_phase_sealed(root, "M2"):
        focus = scope.get("execution_focus") or "M3_USER_GO"
        next_phase = scope.get("current_execution_phase") or "M3"
    elif is_phase_sealed(root, "M1"):
        focus = "M2_READY"
        next_phase = "M2"
    payload = {
        "schema_version": 1,
        "program": "R0_LONG_TERM_MIGRATION",
        "execution_focus": focus,
        "current_execution_phase": next_phase,
        "m1_sealed": is_phase_sealed(root, "M1"),
        "scope_doc": scope.get("scope_doc"),
        "blocked_until_m1_sealed": [] if is_phase_sealed(root, "M1") else BLOCKED_AFTER_M1,
    }
    atomic_write_json(root / "control" / "r0_migration_program.json", payload)
    return payload
