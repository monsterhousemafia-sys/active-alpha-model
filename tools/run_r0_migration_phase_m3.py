#!/usr/bin/env python3
"""Phase M3 — R0* tuning scaffold (requires M2 sealed + user_phase_go).

Preregisters trials per alpha_objective.json. Heavy backtests are NOT autostarted;
run explicitly when ready (prefer WSL: bash tools/wsl_conductor.sh m3-daily).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LEDGER_PATH = "research_evidence/r0_tuning_trial_ledger.json"
DECISION_PATH = "evidence/r0_migration/m3_candidate_decision.json"
OBJECTIVE_PATH = "control/r0_migration/alpha_objective.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_objective(root: Path) -> Dict[str, Any]:
    p = root / OBJECTIVE_PATH
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _build_ledger(root: Path) -> Dict[str, Any]:
    obj = _load_objective(root)
    decision = obj.get("decision") or {}
    objective = obj.get("objective") or {}
    trials: List[Dict[str, Any]] = [
        {
            "trial_id": "M3_DAILY_ALPHA_H1",
            "variant_key": "DAILY_ALPHA_H1",
            "hypothesis": "ensemble horizon=1 rebalance=1 beats 1-day momentum net of cost",
            "horizon": decision.get("horizon", 1),
            "rebalance_every": decision.get("rebalance_every", 1),
            "benchmark": objective.get("benchmark", "1_day_momentum"),
            "status": "PREREGISTERED",
            "heavy_run": True,
            "launch": "python tools/run_validation_matrix.py --phase matrix --variant DAILY_ALPHA_H1",
            "wsl_launch": "bash tools/wsl_conductor.sh m3-daily",
        },
        {
            "trial_id": "M3_R0_BASELINE_REFERENCE",
            "variant_key": "R0_LEGACY_ENSEMBLE",
            "hypothesis": "reference — already sealed in M1",
            "status": "COMPLETE_M1",
            "heavy_run": False,
        },
    ]
    return {
        "schema_version": 1,
        "phase": "M3",
        "generated_at_utc": _utc_now(),
        "objective_ref": OBJECTIVE_PATH,
        "authoritative_champion_until_m9": "R3_w075_q065_noexit",
        "trials": trials,
        "heavy_runs_autostart": False,
        "note": "Trials preregistered; execute heavy runs only with explicit launch command.",
    }


def _build_decision(root: Path, ledger: Dict[str, Any]) -> Dict[str, Any]:
    """Candidate selection only when a trial has integrity PASS returns — never fabricated."""
    selected = None
    rationale = "awaiting heavy trial completion"
    for t in ledger.get("trials") or []:
        if str(t.get("status", "")).upper() in ("SELECTED", "PASS"):
            selected = t.get("variant_key")
            rationale = t.get("hypothesis", "")
            break
    return {
        "schema_version": 1,
        "phase": "M3",
        "generated_at_utc": _utc_now(),
        "status": "SCAFFOLD" if not selected else "CANDIDATE_READY",
        "selected_variant_id": selected,
        "rationale": rationale,
        "ledger_ref": LEDGER_PATH,
        "seal_requires": "selected_variant_id + trial evidence PASS",
    }


def run_m3(root: Path, *, dry_run_matrix: bool = False) -> Dict[str, Any]:
    from aa_safe_io import atomic_write_json
    from tools.r0_migration_phase_guard import is_phase_sealed, try_seal_phase
    from tools.r0_migration_user_go import is_phase_user_authorized, load_user_go

    if not is_phase_sealed(root, "M2"):
        return {"status": "BLOCKED", "reason": "M2_not_sealed"}
    if not is_phase_user_authorized(root, "M3"):
        return {"status": "BLOCKED", "reason": "M3_not_user_authorized", "go": load_user_go(root)}

    ledger = _build_ledger(root)
    decision = _build_decision(root, ledger)
    atomic_write_json(root / LEDGER_PATH, ledger)
    atomic_write_json(root / DECISION_PATH, decision)

    out: Dict[str, Any] = {
        "status": "SCAFFOLD_COMPLETE",
        "ledger": str(root / LEDGER_PATH),
        "decision": decision,
        "user_go": load_user_go(root).get("status"),
    }

    if dry_run_matrix:
        import subprocess

        py = root / ".venv" / "Scripts" / "python.exe"
        if not py.is_file():
            py = Path(sys.executable)
        proc = subprocess.run(
            [
                str(py),
                str(root / "tools" / "run_validation_matrix.py"),
                "--phase",
                "matrix",
                "--variant",
                "DAILY_ALPHA_H1",
                "--dry-run",
            ],
            cwd=str(root),
            capture_output=True,
            text=True,
        )
        out["dry_run"] = {"returncode": proc.returncode, "stdout_tail": (proc.stdout or "")[-1500:]}

    if decision.get("selected_variant_id"):
        seal = try_seal_phase(root, "M3")
        out["seal"] = seal
        if str(seal.get("status", "")).upper() == "SEALED":
            out["status"] = "COMPLETE"
    else:
        out["seal"] = {"status": "SKIPPED", "reason": "no_candidate_yet"}

    return out


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="M3 R0 tuning scaffold")
    p.add_argument("--dry-run", action="store_true", help="Include validation_matrix dry-run for DAILY_ALPHA_H1")
    args = p.parse_args()
    result = run_m3(ROOT, dry_run_matrix=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in ("SCAFFOLD_COMPLETE", "COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
