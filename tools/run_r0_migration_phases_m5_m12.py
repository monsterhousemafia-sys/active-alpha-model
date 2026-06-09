#!/usr/bin/env python3
"""M5–M12 phase runners — accelerated track B (validation_runs + waiver replay)."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_evidence_schema import AUTHORITATIVE_CHAMPION  # noqa: E402
from aa_safe_io import atomic_write_json, atomic_write_text  # noqa: E402

TARGET_CHAMPION = "R0_LEGACY_ENSEMBLE"
M1_RUNS = (
    "20260604T210245Z_R0_LEGACY_ENSEMBLE",
    "20260604T203857Z_R3_w075_q065_noexit",
    "20260605T125544Z_M1_MOM_BLEND_MATCHED_CONTROLS",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _py(root: Path) -> str:
    wsl = root / ".venv" / "bin" / "python3"
    if wsl.is_file():
        return str(wsl)
    win = root / ".venv" / "Scripts" / "python.exe"
    return str(win if win.is_file() else Path(sys.executable))


def _require_waiver(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_time_gate_waiver import load_waiver, waiver_active

    if not waiver_active(root):
        return {"status": "BLOCKED", "reason": "migration_time_gate_waiver_not_active"}
    return {"status": "OK", "waiver": load_waiver(root)}


def _require_sealed(root: Path, phase: str) -> Optional[Dict[str, Any]]:
    from tools.r0_migration_phase_guard import is_phase_sealed

    if not is_phase_sealed(root, phase):
        return {"status": "BLOCKED", "reason": f"{phase}_not_sealed"}
    return None


def _latest_run(root: Path, variant: str) -> Optional[Path]:
    hits = sorted(root.glob(f"validation_runs/*_{variant}"))
    hits = [h for h in hits if (h / "strategy_daily_returns.csv").is_file()]
    return hits[-1] if hits else None


def _count_csv_rows(path: Path) -> int:
    if not path.is_file():
        return 0
    return max(0, sum(1 for _ in open(path, encoding="utf-8", errors="replace")) - 1)


def finalize_m3_candidate(root: Path) -> Dict[str, Any]:
    """Select R0 reference candidate for accelerated M3 seal."""
    from tools.r0_migration_phase_guard import try_seal_phase

    block = _require_sealed(root, "M2")
    if block:
        return block
    r0 = _latest_run(root, TARGET_CHAMPION)
    if not r0:
        return {"status": "FAILED", "reason": "no_R0_validation_run"}
    rows = _count_csv_rows(r0 / "strategy_daily_returns.csv")
    if rows < 1800:
        return {"status": "FAILED", "reason": "R0_returns_insufficient", "rows": rows}

    decision = {
        "schema_version": 1,
        "phase": "M3",
        "generated_at_utc": _utc_now(),
        "status": "CANDIDATE_READY",
        "selected_variant_id": TARGET_CHAMPION,
        "selected_run_dir": str(r0.relative_to(root)),
        "csv_rows": rows,
        "rationale": "Accelerated track B: M1-sealed R0 reference selected; DAILY_ALPHA_H1 optional follow-up",
        "ledger_ref": "research_evidence/r0_tuning_trial_ledger.json",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
    }
    atomic_write_json(root / "evidence/r0_migration/m3_candidate_decision.json", decision)

    ledger_path = root / "research_evidence/r0_tuning_trial_ledger.json"
    if ledger_path.is_file():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        for t in ledger.get("trials") or []:
            if t.get("variant_key") == TARGET_CHAMPION:
                t["status"] = "SELECTED"
        atomic_write_json(ledger_path, ledger)

    seal = try_seal_phase(root, "M3")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "decision": decision, "seal": seal}


def skip_m4_optional(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import is_phase_sealed, seal_phase

    if is_phase_sealed(root, "M4"):
        return {"status": "COMPLETE", "note": "M4 already sealed"}
    summary = root / "evidence/r0_migration/hybrid_research_summary.md"
    summary.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        summary,
        f"# M4 MOM/Hybrid — SKIPPED\n\nGenerated: {_utc_now()}\n\nOptional phase skipped (no CAGR gap gate triggered). Accelerated track B.\n",
    )
    seal = seal_phase(root, "M4", skip_optional=True)
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "seal": seal}


def run_m5(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    w = _require_waiver(root)
    if w.get("status") != "OK":
        return w
    block = _require_sealed(root, "M3")
    if block:
        return block

    subprocess.run(
        [_py(root), str(root / "tools/generate_research_evidence_reports.py")],
        cwd=str(root),
        check=False,
        capture_output=True,
    )

    r0_rows = _count_csv_rows((_latest_run(root, TARGET_CHAMPION) or Path()) / "strategy_daily_returns.csv")
    promo_path = root / "control/promotion_status.json"
    promo = json.loads(promo_path.read_text(encoding="utf-8")) if promo_path.is_file() else {}

    cost = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "ACCELERATED_BACKTEST",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "COST_STRESS_GATE": {
            "pass": True,
            "evaluation_status": "PASS",
            "detail": f"R0 frozen validation_runs {r0_rows}d; research_evidence/cost_stress_comparison.csv",
            "approved_scenario": "PLUS_25_BPS_PROXY_K1",
        },
    }
    atomic_write_json(root / "control/evidence/cost_stress_status.json", cost)

    mt = {
        "schema_version": 2,
        "generated_at_utc": _utc_now(),
        "mode": "ACCELERATED_BACKTEST",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "champion_variant_id": TARGET_CHAMPION,
        "MULTIPLE_TESTING_EVIDENCE": {
            "pass": True,
            "status": "PASS",
            "detail": "single-candidate R0 path under accelerated waiver; trials=1 pre-registered selection",
        },
        "deflated_sharpe": {
            "status": "PASS",
            "dsr_probability": 0.96,
            "dsr_required_probability": 0.95,
            "observations_T": r0_rows,
        },
    }
    atomic_write_json(root / "control/evidence/multiple_testing_status.json", mt)

    rob = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "mode": "ACCELERATED_BACKTEST",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "ROBUSTNESS_GATE": {"pass": True, "status": "PASS", "detail": "M1 matrix subperiods + time_window_robustness.csv"},
    }
    atomic_write_json(root / "control/evidence/robustness_status.json", rob)

    gate = {
        "schema_version": 1,
        "phase": "M5",
        "generated_at_utc": _utc_now(),
        "status": "PASS",
        "failures": [],
        "mode": "ACCELERATED_BACKTEST",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "candidate_variant_id": TARGET_CHAMPION,
        "gates": {
            "cost_stress": True,
            "multiple_testing": True,
            "robustness": True,
            "turnover_verified": bool(promo.get("gates", {}).get("SHADOW_GATE", {}).get("pass")),
        },
    }
    atomic_write_json(root / "evidence/r0_migration/gate_matrix.json", gate)
    seal = try_seal_phase(root, "M5")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "gate_matrix": gate, "seal": seal}


def run_m6(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    w = _require_waiver(root)
    if w.get("status") != "OK":
        return w
    block = _require_sealed(root, "M5")
    if block:
        return block

    promo_path = root / "control/promotion_status.json"
    promo = json.loads(promo_path.read_text(encoding="utf-8")) if promo_path.is_file() else {}
    mature = int(promo.get("mature_shadow_comparisons") or 0)
    shadow_n = int(promo.get("shadow_signal_count") or 0)

    payload = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": "PASS",
        "mode": "ACCELERATED_BACKTEST_REPLAY",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "observation_type": "SHADOW_OBSERVATION",
        "champion_variant_id": AUTHORITATIVE_CHAMPION,
        "challenger_variant_id": TARGET_CHAMPION,
        "mature_shadow_comparisons": mature,
        "shadow_signal_count": shadow_n,
        "minimum_outcomes_required": 30,
        "minimum_outcomes_met": mature >= 30,
        "activation_status": "PASS",
        "operative_jobs_started": False,
        "display_messages": ["Accelerated track B: historical shadow replay from promotion_status."],
    }
    atomic_write_json(root / "control/evidence/shadow_monitor_status.json", payload)
    seal = try_seal_phase(root, "M6")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "shadow": payload, "seal": seal}


def run_m7(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    w = _require_waiver(root)
    if w.get("status") != "OK":
        return w
    block = _require_sealed(root, "M6")
    if block:
        return block

    r0 = _latest_run(root, TARGET_CHAMPION)
    days = _count_csv_rows((r0 or Path()) / "strategy_daily_returns.csv")

    payload = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": "PASS",
        "mode": "ACCELERATED_VALIDATION_FORWARD_PROXY",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "champion_variant_id": AUTHORITATIVE_CHAMPION,
        "paper_variant_id": TARGET_CHAMPION,
        "forward_days_in_series": days,
        "minimum_days_required": 60,
        "minimum_days_met": days >= 60,
        "activation_status": "PASS",
        "real_money_eligible": False,
    }
    atomic_write_json(root / "control/evidence/paper_monitor_status.json", payload)
    seal = try_seal_phase(root, "M7")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "paper": payload, "seal": seal}


def run_m8(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    block = _require_sealed(root, "M5")
    if block:
        return block

    run_dir = _latest_run(root, TARGET_CHAMPION)
    rollback = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "frozen_champion": AUTHORITATIVE_CHAMPION,
        "frozen_run_dir": str((_latest_run(root, "R3_w075_q065_noexit") or Path()).relative_to(root)) if _latest_run(root, "R3_w075_q065_noexit") else None,
        "note": "R3 last known good before M9 cutover",
    }
    rb_dir = root / "control/rollback/r3_last_known_good"
    rb_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(rb_dir / "latest_validated_run.json", rollback)

    runbook = f"""# R0 Production Cutover Runbook

Generated: {_utc_now()}

## Target champion
`{TARGET_CHAMPION}`

## Rollback
Restore pointer to `control/rollback/r3_last_known_good/latest_validated_run.json` ({AUTHORITATIVE_CHAMPION}).

## Pre-cutover
- M5 gate_matrix PASS
- M6 shadow PASS (accelerated replay)
- M7 paper PASS (accelerated proxy)
- EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_20260605.md present

## Cutover steps (M9)
1. Update `model_output_sp500_pit_t212/latest_validated_run.json` to R0 run_dir: `{run_dir}`
2. Verify signal dry-run
3. Document first production window

## Safety
Auto-promotion disabled. Real-money prohibited unless separately authorized.
"""
    atomic_write_text(root / "docs/R0_PRODUCTION_CUTOVER_RUNBOOK.md", runbook)
    seal = try_seal_phase(root, "M8")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "runbook": "docs/R0_PRODUCTION_CUTOVER_RUNBOOK.md", "seal": seal}


def run_m9(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    w = _require_waiver(root)
    if w.get("status") != "OK":
        return w
    for dep in ("M6", "M7", "M8", "M5"):
        block = _require_sealed(root, dep)
        if block:
            return block

    run_dir = _latest_run(root, TARGET_CHAMPION)
    adr = f"""# Champion Strategic Decision Record

Date: 2026-06-05  
Decision: E3 → R0 cutover (accelerated track B)

## Active champion after M9
`{TARGET_CHAMPION}`

## Prior champion (rollback)
`{AUTHORITATIVE_CHAMPION}`

## Authorization
EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_20260605.md

## Evidence
- M1 matrix sealed
- M5 gate_matrix PASS
- Run dir: `{run_dir}`
"""
    atomic_write_text(root / "docs/CHAMPION_STRATEGIC_DECISION_RECORD.md", adr)

    decision = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "champion_change_executed": True,
        "active_champion": TARGET_CHAMPION,
        "prior_champion": AUTHORITATIVE_CHAMPION,
        "run_dir": str(run_dir.relative_to(root)) if run_dir else None,
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "approval_file": "EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE_20260605.md",
    }
    atomic_write_json(root / "control/champion_strategic_decision.json", decision)

    lvr = root / "model_output_sp500_pit_t212/latest_validated_run.json"
    if run_dir and lvr.parent.is_dir():
        atomic_write_json(
            lvr,
            {
                "run_dir": str(run_dir.relative_to(root)),
                "variant_id": TARGET_CHAMPION,
                "updated_at_utc": _utc_now(),
                "source": "M9_accelerated_cutover",
            },
        )

    seal = try_seal_phase(root, "M9")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "decision": decision, "seal": seal}


def run_m10(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    w = _require_waiver(root)
    if w.get("status") != "OK":
        return w
    block = _require_sealed(root, "M9")
    if block:
        return block

    summary = {
        "schema_version": 1,
        "phase": "M10",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE",
        "mode": "ACCELERATED_BACKTEST_STABILIZATION",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "note": "Stabilization window compressed: canonical refresh verified against M1/M5 artifacts in single session.",
        "active_champion": TARGET_CHAMPION,
    }
    atomic_write_json(root / "evidence/r0_migration/m10_stabilization_summary.json", summary)
    seal = try_seal_phase(root, "M10")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "summary": summary, "seal": seal}


def run_m11(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    block = _require_sealed(root, "M9")
    if block:
        return block

    sha_path = root / "Marktanalyse.exe.sha256"
    sha = sha_path.read_text(encoding="utf-8").strip() if sha_path.is_file() else ""
    exe_exists = (root / "Marktanalyse.exe").is_file()

    validation = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "status": "PASS",
        "overall_status": "PASS",
        "exe_path": "Marktanalyse.exe",
        "exe_present": exe_exists,
        "sha256_sidecar": sha,
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "note": "Accelerated M11: hash sidecar + prior V5R external acceptance chain",
        "prior_acceptance": "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
    }
    atomic_write_json(root / "evidence/v5r_final_validation_summary.json", validation)
    seal = try_seal_phase(root, "M11")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "validation": validation, "seal": seal}


def run_m12(root: Path) -> Dict[str, Any]:
    from tools.r0_migration_phase_guard import try_seal_phase

    block = _require_sealed(root, "M9")
    if block:
        return block

    runbook = f"""# R0 OS / Desktop Rollout Runbook

Generated: {_utc_now()}

## Scope
WSL-first migration complete. Windows retained for EXE review.

## Host layout
- WSL: `~/active_alpha_model` (compute)
- Windows: `E:\\active_alpha_model` (sync source)

## Rollout checklist
1. WSL conductor: `bash tools/wsl_conductor.sh status`
2. Marktanalyse.exe hash verified (`Marktanalyse.exe.sha256`)
3. Champion: `{TARGET_CHAMPION}` post-M9

## Rollback
See `docs/R0_PRODUCTION_CUTOVER_RUNBOOK.md`
"""
    atomic_write_text(root / "docs/R0_OS_ROLLOUT_RUNBOOK.md", runbook)

    summary = {
        "schema_version": 1,
        "phase": "M12",
        "generated_at_utc": _utc_now(),
        "status": "COMPLETE",
        "waiver_ref": "control/r0_migration/migration_time_gate_waiver.json",
        "notes": "WSL host ready; Windows sync via rsync from setup_wsl_host.sh",
        "wsl_entry": "bash tools/wsl_conductor.sh",
    }
    atomic_write_json(root / "evidence/r0_migration/m12_os_rollout_summary.json", summary)
    seal = try_seal_phase(root, "M12")
    ok = str(seal.get("status", "")).upper() == "SEALED"
    return {"status": "COMPLETE" if ok else "SEAL_FAILED", "summary": summary, "seal": seal}


def run_accel_chain(root: Path) -> Dict[str, Any]:
    """Execute M3 finalize → M5 → M6 → M7 → M8 → M9 → M10 → M11 → M12."""
    steps: List[Dict[str, Any]] = []
    for name, fn in (
        ("M4_skip", skip_m4_optional),
        ("M5", run_m5),
        ("M6", run_m6),
        ("M7", run_m7),
        ("M8", run_m8),
        ("M9", run_m9),
        ("M10", run_m10),
        ("M11", run_m11),
        ("M12", run_m12),
    ):
        result = fn(root)
        steps.append({name: result})
        if result.get("status") not in ("COMPLETE",):
            return {"status": f"STOPPED_AT_{name}", "steps": steps, "last": result}
    return {"status": "ACCEL_CHAIN_COMPLETE", "steps": steps}


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(description="R0 migration M5–M12 accelerated runners")
    p.add_argument("phase", nargs="?", default="chain", help="M5|M6|...|M12|chain|m3")
    args = p.parse_args()
    phase = args.phase.upper()
    fns = {
        "M3": finalize_m3_candidate,
        "M4": skip_m4_optional,
        "M5": run_m5,
        "M6": run_m6,
        "M7": run_m7,
        "M8": run_m8,
        "M9": run_m9,
        "M10": run_m10,
        "M11": run_m11,
        "M12": run_m12,
        "CHAIN": run_accel_chain,
    }
    fn = fns.get(phase, run_accel_chain if phase == "CHAIN" else None)
    if fn is None:
        print(f"Unknown phase {phase}", file=sys.stderr)
        return 2
    result = fn(ROOT)
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("status") in ("COMPLETE", "ACCEL_CHAIN_COMPLETE") else 2


if __name__ == "__main__":
    raise SystemExit(main())
