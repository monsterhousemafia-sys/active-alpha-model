#!/usr/bin/env python3
"""Single M1 control surface — one entry per host (no .bat sprawl)."""
from __future__ import annotations

import os
from typing import Any, Dict

if os.name == "nt":
    M1_ENTRY = "python tools/r0_migration_commander.py"
    M1_STATUS = "python tools/r0_migration_status.py"
    M1_FINISH = "python tools/_m1_autoseal.py"
    M1_FOREGROUND_MATRIX = (
        "python tools/run_validation_matrix.py --phase matrix "
        "--variant M1_MOM_BLEND_MATCHED_CONTROLS --parallel-jobs 1"
    )
else:
    M1_ENTRY = "bash tools/wsl_conductor.sh m1"
    M1_STATUS = "bash tools/wsl_conductor.sh status"
    M1_FINISH = "bash tools/wsl_conductor.sh autoseal"
    M1_FOREGROUND_MATRIX = "bash tools/wsl_conductor.sh m1"


def m1_hints() -> Dict[str, Any]:
    return {
        "primary_entry": M1_ENTRY,
        "resume_hint": M1_ENTRY,
        "finish_hint": M1_FINISH,
        "status_hint": M1_STATUS,
        "foreground_matrix": M1_FOREGROUND_MATRIX,
        "wsl_conductor": "bash tools/wsl_conductor.sh",
    }
