#!/usr/bin/env python3
"""Post-M1 phases after M1 seal. M2+M3 implemented; M4+ gated."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHASE_ORDER = ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11", "M12"]

PHASE_RUNNERS: Dict[str, Callable[[Path], Dict[str, Any]]] = {}


def _register_runners() -> None:
    if PHASE_RUNNERS:
        return
    from tools.run_r0_migration_phase_m2 import run_m2
    from tools.run_r0_migration_phase_m3 import run_m3
    from tools.run_r0_migration_phases_m5_m12 import (
        finalize_m3_candidate,
        run_m10,
        run_m11,
        run_m12,
        run_m5,
        run_m6,
        run_m7,
        run_m8,
        run_m9,
        run_accel_chain,
    )

    PHASE_RUNNERS["M2"] = run_m2
    PHASE_RUNNERS["M3"] = run_m3
    PHASE_RUNNERS["M3_finalize"] = finalize_m3_candidate  # type: ignore[assignment]
    PHASE_RUNNERS["M5"] = run_m5
    PHASE_RUNNERS["M6"] = run_m6
    PHASE_RUNNERS["M7"] = run_m7
    PHASE_RUNNERS["M8"] = run_m8
    PHASE_RUNNERS["M9"] = run_m9
    PHASE_RUNNERS["M10"] = run_m10
    PHASE_RUNNERS["M11"] = run_m11
    PHASE_RUNNERS["M12"] = run_m12
    PHASE_RUNNERS["ACCEL"] = run_accel_chain  # type: ignore[assignment]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _ok_status(st: str) -> bool:
    return st in ("COMPLETE", "SCAFFOLD_COMPLETE")


def run_orchestrator(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_active_scope import assert_m1_sealed_for_phase, sync_program_focus
    from tools.r0_migration_phase_guard import is_phase_sealed
    from tools.run_r0_migration_autopilot_selfcheck import run_selfcheck

    _register_runners()
    sync_program_focus(root)
    out: Dict[str, Any] = {"started_at_utc": _utc_now(), "steps": []}
    out["selfcheck"] = run_selfcheck(root)

    if not is_phase_sealed(root, "M1"):
        gate = assert_m1_sealed_for_phase(root, "M2")
        out["m1_scope_gate"] = gate
        out["status"] = "M1_ONLY_COMPLETE_M1_FIRST"
        from tools.r0_migration_m1_control import m1_hints

        out["next_action"] = m1_hints()["primary_entry"]
        return out

    for phase in PHASE_ORDER[1:]:
        if is_phase_sealed(root, phase):
            continue
        gate = assert_m1_sealed_for_phase(root, phase)
        if not gate.get("allowed"):
            out["steps"].append({"phase": phase, "gate": gate})
            out["status"] = "BLOCKED_BY_M1_SCOPE"
            return out
        runner = PHASE_RUNNERS.get(phase)
        if runner is None:
            out["steps"].append({"phase": phase, "status": "NOT_IMPLEMENTED_STOP"})
            out["status"] = f"STOPPED_AT_{phase}_NOT_IMPLEMENTED"
            return out
        result = runner(root)
        out["steps"].append({phase: result})
        if not _ok_status(str(result.get("status", ""))) and result.get("status") != "COMPLETE":
            out["status"] = f"{phase}_FAILED"
            return out
        out["status"] = f"{phase}_COMPLETE"
        if phase == "M3" and result.get("status") == "SCAFFOLD_COMPLETE":
            from tools.r0_migration_time_gate_waiver import waiver_active

            if waiver_active(root):
                fin = PHASE_RUNNERS["M3_finalize"](root)
                out["steps"].append({"M3_finalize": fin})
                if fin.get("status") != "COMPLETE":
                    out["status"] = "M3_FINALIZE_FAILED"
                    return out
                accel = PHASE_RUNNERS["ACCEL"](root)
                out["steps"].append({"ACCEL": accel})
                out["status"] = accel.get("status", "ACCEL_UNKNOWN")
                return out
            out["next_action"] = "heavy_run: bash tools/wsl_conductor.sh m3-daily (after WSL setup)"
            return out
        if not is_phase_sealed(root, phase) and phase != "M3":
            continue
        if phase == "M3" and not is_phase_sealed(root, "M3"):
            out["next_action"] = "complete M3 trial then seal"
            return out

    out["status"] = "ALL_IMPLEMENTED_DONE"
    return out


def main() -> int:
    from aa_safe_io import atomic_write_json

    result = run_orchestrator(ROOT)
    atomic_write_json(ROOT / "control" / "r0_migration" / "orchestrator_last_run.json", result)
    print(json.dumps(result, indent=2, default=str))
    ok = {
        "M2_COMPLETE",
        "M3_COMPLETE",
        "ALL_IMPLEMENTED_DONE",
        "M1_ONLY_COMPLETE_M1_FIRST",
    }
    if result.get("status", "").endswith("_COMPLETE"):
        ok.add(result["status"])
    return 0 if result.get("status") in ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
