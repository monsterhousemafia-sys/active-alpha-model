"""Phase E — strategic champion decision evaluation (read-only, no auto-switch)."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_champion_governance import load_champion_change_criteria
from aa_evidence_schema import AUTHORITATIVE_CHAMPION, resolve_locked_champion

CANONICAL_PATH = Path("evidence") / "canonical_model_comparison.json"

DECISION_OPTIONS = (
    "E1_RETAIN_R3",
    "E2_SWITCH_M1",
    "E3_SWITCH_R0_OR_R2",
    "E4_MOM_63_CHALLENGER_TRACK",
    "E5_R5_REVALIDATE",
)

def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "MISSING"
    try:
        return json.loads(path.read_text(encoding="utf-8")), "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def _external_champion_change_approved(root: Path) -> bool:
    for path in sorted(root.glob("EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE*.md")):
        if "TEMPLATE" in path.name.upper():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\b(APPROVED|AUTHORIZED|SEALED)\b", text, re.I):
            return True
    return False


def _gate_checklist(root: Path, criteria: Dict[str, Any]) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)
    canonical, _ = _read_json(root / CANONICAL_PATH)
    cost_stress, cs_st = _read_json(root / Path(str(criteria.get("cost_stress", {}).get("evidence", ""))))
    mt, mt_st = _read_json(root / Path(str(criteria.get("multiple_testing", {}).get("evidence", ""))))
    robust, rob_st = _read_json(root / Path(str(criteria.get("robustness", {}).get("evidence", ""))))

    headline = canonical.get("headline") or {}
    rankings = canonical.get("rankings") or {}
    matrix_rank = rankings.get("sharpe_matrix_embedded") or []
    leader = headline.get("matrix_embedded_sharpe_leader")
    champ_rank = headline.get("champion_sharpe_rank_matrix")

    cost_gate = (cost_stress.get("COST_STRESS_GATE") or {}) if cs_st == "OK" else {}
    dsr = (mt.get("deflated_sharpe") or {}) if mt_st == "OK" else {}
    rob_ev = (robust.get("ROBUSTNESS_EVIDENCE") or {}) if rob_st == "OK" else {}

    min_delta = float((criteria.get("matrix_comparison") or {}).get("min_sharpe_delta_vs_champion") or 0.02)
    champ_sharpe = None
    for row in canonical.get("variants") or []:
        if row.get("variant_id") == locked:
            champ_sharpe = (row.get("metrics") or {}).get("sharpe_0rf")
            break

    candidate_beats = {}
    for vid in ("R0_LEGACY_ENSEMBLE", "M1_MOM_BLEND_MATCHED_CONTROLS", "R2_MOM_BLEND_REPLACE", "MOM_63_TOP12"):
        for row in matrix_rank:
            if row.get("variant_id") != vid:
                continue
            sh = float(row.get("sharpe_0rf") or 0)
            candidate_beats[vid] = {
                "sharpe_0rf": sh,
                "beats_champion_sharpe": bool(champ_sharpe is not None and sh > float(champ_sharpe) + min_delta),
                "rank": row.get("rank"),
            }

    contaminated = (root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv").is_file()
    if contaminated:
        import hashlib

        sha = hashlib.sha256(
            (root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv").read_bytes()
        ).hexdigest()
        bad_sha = str((criteria.get("integrity") or {}).get("contaminated_returns_sha256") or "")
        contaminated = sha == bad_sha

    checks = {
        "external_champion_change_approval": _external_champion_change_approved(root),
        "canonical_comparison_present": (root / CANONICAL_PATH).is_file(),
        "matrix_sharpe_leader": leader,
        "champion_matrix_rank": champ_rank,
        "candidate_sharpe_vs_champion": candidate_beats,
        "cost_stress_pass": bool(cost_gate.get("pass")) if cs_st == "OK" else False,
        "cost_stress_status": cost_gate.get("evaluation_status") or cs_st,
        "cost_stress_blockers": cost_gate.get("blockers") or [],
        "dsr_status": dsr.get("status") or mt_st,
        "robustness_pass": bool(rob_ev.get("pass")) if rob_st == "OK" else None,
        "validation_runs_present": bool(canonical.get("validation_runs_present")),
        "champion_returns_contaminated_in_model_output": contaminated,
        "auto_promotion_allowed": bool(criteria.get("auto_promotion_allowed")),
    }
    switch_eligible = (
        checks["external_champion_change_approval"]
        and checks["canonical_comparison_present"]
        and not checks["champion_returns_contaminated_in_model_output"]
        and checks["cost_stress_pass"]
        and checks.get("robustness_pass") is True
        and not bool(criteria.get("auto_promotion_allowed"))
    )
    checks["switch_gates_all_pass"] = switch_eligible
    return checks


def evaluate_strategic_options(root: Path) -> Dict[str, Any]:
    root = Path(root)
    locked = resolve_locked_champion(root)
    criteria, crit_st = load_champion_change_criteria(root)
    gates = _gate_checklist(root, criteria) if crit_st == "OK" else {}

    options: List[Dict[str, Any]] = []

    options.append(
        {
            "option_id": "E1_RETAIN_R3",
            "label_de": "R3 behalten (Risk-off Rescue, Governance-Stabilität)",
            "recommended": True,
            "eligible": True,
            "rationale_de": [
                "Externe Freigabe FINAL seal auf R3; Zielfunktion = Risk-off, nicht Max-Sharpe.",
                "Wechsel-Gates (Cost-Stress, DSR, Forward) nicht vollständig PASS.",
                "Matrix-Rang 4/7 ist dokumentiert und im Charter als akzeptierter Trade-off.",
            ],
        }
    )

    m1_ok = (gates.get("candidate_sharpe_vs_champion") or {}).get("M1_MOM_BLEND_MATCHED_CONTROLS", {}).get(
        "beats_champion_sharpe"
    )
    options.append(
        {
            "option_id": "E2_SWITCH_M1",
            "label_de": "Wechsel zu M1 (matched controls)",
            "recommended": False,
            "eligible": bool(gates.get("switch_gates_all_pass") and m1_ok),
            "rejected_reasons_de": [
                "Kein EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE.",
                "Cost-Stress NOT_EVALUABLE / blockiert.",
                "Kein Auto-Switch — würde ökonomische Produktiv-Logik ändern.",
            ],
        }
    )

    r0_ok = (gates.get("candidate_sharpe_vs_champion") or {}).get("R0_LEGACY_ENSEMBLE", {}).get("beats_champion_sharpe")
    options.append(
        {
            "option_id": "E3_SWITCH_R0_OR_R2",
            "label_de": "Wechsel zu R0/R2 (höherer Matrix-Sharpe)",
            "recommended": False,
            "eligible": bool(gates.get("switch_gates_all_pass") and r0_ok),
            "rejected_reasons_de": [
                "Sharpe höher, aber Risk-off-Rescue-Hypothese entfällt.",
                "Gleiche Gate-Blocker wie E2; validation_runs lokal fehlen für vollständiges Re-Align.",
            ],
        }
    )

    options.append(
        {
            "option_id": "E4_MOM_63_CHALLENGER_TRACK",
            "label_de": "MOM_63 als Challenger-Pfad (nicht sofortiger Champion)",
            "recommended": False,
            "eligible": False,
            "rationale_de": [
                "Höchster Sharpe auf intersection-aligned CSVs — nur Research.",
                "CHALLENGER_TURNOVER_NOT_VERIFIED; erst F-Phase Gates, dann Shadow/Paper.",
            ],
        }
    )

    options.append(
        {
            "option_id": "E5_R5_REVALIDATE",
            "label_de": "R5 quarantiniert lassen",
            "recommended": True,
            "eligible": False,
            "rationale_de": [
                "Unauthorized champion claim; kein operativer Wechsel ohne externes Seal und einheitlichen Kalender.",
            ],
        }
    )

    selected = "E1_RETAIN_R3"
    champion_change_executed = False

    return {
        "schema_version": 1,
        "phase": "E",
        "generated_at_utc": _utc_now(),
        "authoritative_champion": locked,
        "selected_option": selected,
        "champion_variant_after_decision": locked,
        "champion_change_executed": champion_change_executed,
        "decision_summary_de": (
            "R3_w075_q065_noexit bleibt produktiver Champion. "
            "Sharpe-Optimum (R0/M1) rechtfertigt keinen Wechsel ohne erfüllte Wechsel-Gates und neue externe Freigabe."
        ),
        "options": options,
        "gate_checklist": gates,
        "criteria_status": crit_st,
        "references": {
            "charter": "control/champion_decision_charter.md",
            "criteria": "control/champion_change_criteria.yaml",
            "canonical": str(CANONICAL_PATH).replace("\\", "/"),
            "adr": "docs/CHAMPION_STRATEGIC_DECISION_RECORD.md",
        },
    }


def apply_e1_retention(root: Path, decision: Dict[str, Any]) -> Dict[str, Any]:
    """Operationalize E1: reaffirm R3 pointers/registry, refresh reports, record rejected alternatives."""
    root = Path(root)
    locked = str(decision.get("champion_variant_after_decision") or resolve_locked_champion(root))
    steps: Dict[str, Any] = {}
    conflicts: List[str] = []

    if locked != AUTHORITATIVE_CHAMPION:
        conflicts.append(f"code_locked_champion={AUTHORITATIVE_CHAMPION} != decision={locked}")

    try:
        from tools.run_champion_evidence_phase_b import (
            patch_champion_registry_to_r3,
            rebuild_reports,
            repair_latest_validated_run,
        )

        steps["B1_pointer_repair"] = repair_latest_validated_run(root)
        steps["B3c_champion_registry"] = patch_champion_registry_to_r3(root)
        steps["B5_reports"] = rebuild_reports(root)
        report_champ = (steps.get("B5_reports") or {}).get("champion_variant_id")
        if report_champ and report_champ != locked:
            conflicts.append(f"challenger_report_champion={report_champ}")
    except Exception as exc:
        steps["phase_b_refresh_error"] = str(exc)
        conflicts.append("phase_b_refresh_failed")

    canonical_path = root / CANONICAL_PATH
    if not canonical_path.is_file():
        try:
            from tools.build_canonical_model_comparison import main as build_canonical_main
            import sys

            argv = sys.argv
            sys.argv = ["build_canonical_model_comparison.py", "--root", str(root)]
            try:
                build_canonical_main()
            finally:
                sys.argv = argv
            steps["phase_c_built"] = True
        except Exception as exc:
            steps["phase_c_build_error"] = str(exc)
            conflicts.append("canonical_comparison_missing")

    rejected = [
        {
            "option_id": o.get("option_id"),
            "eligible": o.get("eligible"),
            "recommended": o.get("recommended"),
            "rejected_reasons_de": o.get("rejected_reasons_de") or o.get("rationale_de"),
        }
        for o in decision.get("options") or []
        if o.get("option_id") != "E1_RETAIN_R3"
    ]
    from aa_safe_io import atomic_write_json

    atomic_write_json(
        root / "control" / "champion_rejected_alternatives.json",
        {
            "schema_version": 1,
            "generated_at_utc": _utc_now(),
            "selected_option": "E1_RETAIN_R3",
            "authoritative_champion": locked,
            "rejected": rejected,
        },
    )
    steps["rejected_alternatives"] = "control/champion_rejected_alternatives.json"

    operational = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "phase": "E",
        "operational_champion": locked,
        "strategic_decision": "E1_RETAIN_R3",
        "auto_promotion": "DISABLED",
        "champion_change_forbidden_until": "EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE + champion_change_criteria.yaml PASS",
        "decision_record": "docs/CHAMPION_STRATEGIC_DECISION_RECORD.md",
        "next_phases": ["F_STATISTICAL_EVIDENCE", "G_LIVE_OPS"],
        "conflicts": conflicts,
    }
    atomic_write_json(root / "control" / "champion_operational_status.json", operational)
    steps["operational_status"] = "control/champion_operational_status.json"

    policy_path = root / "control" / "champion_lineage_policy.json"
    policy: Dict[str, Any] = {}
    if policy_path.is_file():
        try:
            policy = json.loads(policy_path.read_text(encoding="utf-8"))
        except Exception:
            policy = {}
    policy["phase_e_executed_at_utc"] = _utc_now()
    policy["phase_e_selected_option"] = "E1_RETAIN_R3"
    policy["phase_e_champion_after_decision"] = locked
    policy["strategic_decision_status"] = "EXECUTED_E1_RETAIN_R3"
    atomic_write_json(policy_path, policy)
    steps["lineage_policy_updated"] = True

    return {
        "applied": True,
        "option": "E1_RETAIN_R3",
        "champion_variant": locked,
        "steps": steps,
        "conflicts": conflicts,
        "status": "COMPLETE" if not conflicts else "COMPLETE_WITH_WARNINGS",
    }


def apply_strategic_decision(root: Path, decision: Dict[str, Any], *, allow_champion_change: bool = False) -> Dict[str, Any]:
    """Apply strategic decision: E1 operational retention (default) or blocked champion switch."""
    root = Path(root)
    selected = str(decision.get("selected_option") or "")

    if selected == "E1_RETAIN_R3":
        return apply_e1_retention(root, decision)

    if not allow_champion_change:
        return {"applied": False, "reason": "champion_change_requires_allow_flag_and_external_approval"}

    gates = decision.get("gate_checklist") or {}
    if not gates.get("switch_gates_all_pass"):
        return {"applied": False, "reason": "switch_gates_not_pass", "blockers": gates}

    if not gates.get("external_champion_change_approval"):
        return {"applied": False, "reason": "missing_EXTERNAL_REVIEW_APPROVAL_CHAMPION_CHANGE"}

    return {
        "applied": False,
        "reason": "champion_code_change_not_implemented_use_dedicated_publish_pipeline",
        "requested_option": selected,
    }
