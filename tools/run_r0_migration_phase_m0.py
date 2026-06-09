#!/usr/bin/env python3
"""Phase M0 — R0 migration mandate: write docs + control artifacts (no champion change)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aa_safe_io import atomic_write_json  # noqa: E402

MANDATE_MD = ROOT / "docs" / "R0_MIGRATION_MANDATE.md"
CHARTER_DRAFT = ROOT / "control" / "champion_decision_charter_r0_target_draft.md"
CONTROL_DIR = ROOT / "control" / "r0_migration"
EVIDENCE_DIR = ROOT / "evidence" / "r0_migration"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_mandate_payload(*, approved_at_utc: str) -> dict:
    return {
        "schema_version": 1,
        "phase": "M0",
        "status": "COMPLETE",
        "approved_at_utc": approved_at_utc,
        "approval_mode": "PROGRAM_MANDATE_CURSOR_SESSION",
        "program_doc": "docs/R0_LONG_TERM_MIGRATION_PLAN.md",
        "mandate_doc": "docs/R0_MIGRATION_MANDATE.md",
        "charter_target_draft": "control/champion_decision_charter_r0_target_draft.md",
        "authoritative_champion_until_m9": "R3_w075_q065_noexit",
        "target_champion_primary": "R0_LEGACY_ENSEMBLE",
        "target_champion_research": "R0_STAR",
        "objective_function": {
            "primary": ["aligned_sharpe_0rf", "aligned_cagr"],
            "secondary": ["max_drawdown_vs_champion", "beat_m1_control"],
            "stability_optional": ["subperiod_segment_2_sharpe_min_0.5"],
            "gates_required": [
                "matrix_comparison",
                "cost_stress_plus_25_bps",
                "dsr",
                "robustness",
                "shadow",
                "paper_forward",
                "external_champion_change_approval",
            ],
        },
        "thresholds": {
            "min_sharpe_delta_vs_champion": 0.02,
            "max_drawdown_degradation_vs_champion": 0.02,
            "paper_forward_min_days": 60,
            "shadow_min_outcomes": 30,
            "criteria_yaml": "control/champion_change_criteria.yaml",
        },
        "decisions": {
            "primary_track": "R0_LEGACY_ENSEMBLE",
            "tuning_track": "R0_STAR_validation_runs_only",
            "hybrid_mom_track": "DEFERRED_M4",
            "excluded_variants": ["R5_rank_only_train5", "rank_only_production"],
            "risk_off_episode_tradeoff_accepted": "CONDITIONAL_ON_M2",
            "paper_forward_required": True,
            "shadow_required": True,
            "exe_os_rollout": "POST_M9_SEPARATE",
            "auto_promotion": False,
        },
        "stop_rules": [
            "M2_risk_off_episode_catastrophic_for_R0",
            "M0_mandate_revoked",
            "switch_gates_not_all_pass",
        ],
        "next_phase": "M1",
        "next_phase_doc": "docs/R0_LONG_TERM_MIGRATION_PLAN.md#m1--evidenz-baseline--sanierung-1-2-wochen",
    }


def run_m0(*, dry_run: bool = False) -> dict:
    approved_at = _utc_now()
    payload = build_mandate_payload(approved_at_utc=approved_at)

    if dry_run:
        return {"dry_run": True, "mandate": payload}

    if not MANDATE_MD.is_file():
        raise FileNotFoundError(f"Missing mandate doc (run after creating docs): {MANDATE_MD}")
    if not CHARTER_DRAFT.is_file():
        raise FileNotFoundError(f"Missing charter draft: {CHARTER_DRAFT}")

    CONTROL_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    atomic_write_json(CONTROL_DIR / "mandate.json", payload)
    atomic_write_json(
        CONTROL_DIR / "phase_status.json",
        {
            "schema_version": 1,
            "program": "R0_LONG_TERM_MIGRATION",
            "phases": {
                "M0": {"status": "COMPLETE", "completed_at_utc": approved_at},
                "M1": {"status": "PENDING", "blocked_by": None},
            },
            "mandate_ref": "control/r0_migration/mandate.json",
        },
    )
    atomic_write_json(
        EVIDENCE_DIR / "m0_completion_summary.json",
        {
            "phase": "M0",
            "status": "COMPLETE",
            "completed_at_utc": approved_at,
            "deliverables": [
                "docs/R0_MIGRATION_MANDATE.md",
                "control/r0_migration/mandate.json",
                "control/r0_migration/phase_status.json",
                "control/champion_decision_charter_r0_target_draft.md",
            ],
            "authoritative_champion_unchanged": "R3_w075_q065_noexit",
        },
    )

    program_status = ROOT / "control" / "r0_migration_program.json"
    atomic_write_json(
        program_status,
        {
            "schema_version": 1,
            "program": "R0_LONG_TERM_MIGRATION",
            "plan_doc": "docs/R0_LONG_TERM_MIGRATION_PLAN.md",
            "mandate_doc": "docs/R0_MIGRATION_MANDATE.md",
            "current_phase": "M1",
            "last_completed_phase": "M0",
            "updated_at_utc": approved_at,
        },
    )

    from tools.r0_migration_phase_guard import seal_phase

    seal_result = seal_phase(ROOT, "M0")
    return {
        "status": "COMPLETE",
        "approved_at_utc": approved_at,
        "mandate_path": str(CONTROL_DIR / "mandate.json"),
        "m0_seal": seal_result.get("status"),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Execute R0 migration phase M0 (mandate artifacts only).")
    p.add_argument("--dry-run", action="store_true", help="Build payload without writing control files.")
    args = p.parse_args()
    try:
        result = run_m0(dry_run=args.dry_run)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
