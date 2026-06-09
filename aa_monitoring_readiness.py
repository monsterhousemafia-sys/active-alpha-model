"""Forward monitoring readiness and data requirements (V3 — read-only)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from aa_forward_monitor_schema import (
    CANDIDATE_VARIANT,
    CHAMPION_VARIANT,
    CONTROL_VARIANT,
    MODE,
    OBSERVATION_TYPES,
    base_monitoring_fields,
)
from aa_safe_io import atomic_write_json

READINESS_PATH = Path("control") / "evidence" / "forward_monitoring_readiness_status.json"
REQUIREMENTS_PATH = Path("control") / "evidence" / "forward_monitoring_data_requirements.json"

BASELINE_COST_REPORTS = (
    "model_output_sp500_pit_t212/backtest_report.txt",
    "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/backtest_report.txt",
)

FORWARD_BLOCKERS = (
    "CHALLENGER_TURNOVER_NOT_VERIFIED",
    "DSR_BELOW_REQUIRED_CONFIDENCE",
    "ROBUSTNESS_NOT_PASSED",
    "P9_NOT_EXTERNALLY_REVIEWED",
    "FORWARD_MONITORING_NOT_EXTERNALLY_APPROVED",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def file_sha256(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _collect_evidence_blockers(root: Path) -> List[str]:
    root = Path(root)
    blockers: List[str] = list(FORWARD_BLOCKERS)
    evidence = _read_json(root / "control" / "evidence" / "current_evidence_status.json")
    for b in evidence.get("current_active_blockers") or evidence.get("blockers") or []:
        if b and b not in blockers:
            blockers.append(str(b))
    cost = _read_json(root / "control" / "evidence" / "cost_stress_status.json")
    for b in (cost.get("COST_STRESS_GATE") or {}).get("blockers") or []:
        if b and b not in blockers:
            blockers.append(str(b))
    mt = _read_json(root / "control" / "evidence" / "multiple_testing_status.json")
    mt_blocker = (mt.get("MULTIPLE_TESTING_EVIDENCE") or {}).get("blocker")
    if mt_blocker and mt_blocker not in blockers:
        blockers.append(str(mt_blocker))
    return sorted(set(blockers))


def _baseline_cost_report_status(root: Path) -> Dict[str, Any]:
    root = Path(root)
    entries: List[Dict[str, Any]] = []
    missing: List[str] = []
    for rel in BASELINE_COST_REPORTS:
        path = root / rel
        if path.is_file():
            entries.append({"path": rel, "sha256": file_sha256(path), "present": True})
        else:
            missing.append(rel)
            entries.append({"path": rel, "sha256": "", "present": False})
    note = None
    if missing:
        note = "BASELINE_COST_REPORT_NOT_EXTERNALLY_INCLUDED"
    return {"reports": entries, "missing_paths": missing, "external_inclusion_note": note}


def _available_inputs(root: Path) -> tuple[List[str], List[str]]:
    root = Path(root)
    available: List[str] = []
    missing: List[str] = []
    candidates = [
        "model_output_sp500_pit_t212/strategy_daily_returns.csv",
        "model_output_sp500_pit_t212/backtest_decisions.csv",
        "validation_runs/20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS/mom_blend_matched_controls_daily_returns.csv",
        "control/challenger_report.json",
        "control/evidence/cost_stress_status.json",
        "control/evidence/robustness_status.json",
        "control/evidence/multiple_testing_status.json",
    ]
    for rel in candidates:
        if (root / rel).is_file():
            available.append(rel)
        else:
            missing.append(rel)
    return available, missing


def build_forward_monitoring_readiness(root: Path) -> Dict[str, Any]:
    root = Path(root)
    blockers = _collect_evidence_blockers(root)
    available, missing = _available_inputs(root)
    baseline = _baseline_cost_report_status(root)
    if baseline.get("external_inclusion_note"):
        if baseline["external_inclusion_note"] not in blockers:
            blockers.append(str(baseline["external_inclusion_note"]))
        blockers = sorted(set(blockers))

    payload = base_monitoring_fields(observation_type="FORWARD_MONITORING")
    payload.update(
        {
            "generated_at_utc": _utc_now(),
            "activation_status": "BLOCKED",
            "required_inputs": [
                "challenger_specific_turnover_or_position_change_evidence",
                "externally_approved_forward_monitoring_activation",
                "verified_dsr_evidence",
                "full_robustness_evidence",
                "externally_reviewed_p9_classification",
            ],
            "available_inputs": available,
            "missing_inputs": missing + ["challenger_specific_turnover_or_position_change_evidence"],
            "active_blockers": blockers,
            "baseline_cost_reports": baseline,
            "source_artifacts": [
                {"path": "control/evidence/current_evidence_status.json", "role": "unified_evidence"},
                {"path": "control/evidence/cost_stress_status.json", "role": "cost_stress"},
            ],
            "display_messages": [
                "Forward monitoring foundation is read-only; no observation jobs started.",
                "Activation requires separate external approval after V3.",
                "Cost stress remains blocked without verified Challenger turnover.",
            ],
        }
    )
    return payload


def build_forward_monitoring_data_requirements(root: Path) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "mode": MODE,
        "description": "Data requirements for future V3S/V3P activation — does not trigger activation.",
        "V3S_SHADOW_OBSERVATION": {
            "minimum_required": [
                "externally approved activation artifact",
                "challenger-specific signal ledger",
                "challenger-specific turnover or position-change evidence",
                "immutable prediction timestamps before outcome maturity",
                "data-quality evidence source",
                "outcome maturity rule",
                "incident/stop conditions",
                "no-order guarantee",
            ],
            "activation_triggers_jobs": False,
        },
        "V3P_PAPER_SIMULATION": {
            "minimum_required": [
                "externally reviewed Shadow evidence",
                "simulated order schema",
                "simulated fill/slippage model",
                "verified cost-treatment model",
                "paper-only storage isolation",
                "explicit no-broker-connectivity guarantee",
            ],
            "additional_to_v3s": True,
            "activation_triggers_jobs": False,
        },
        "observation_types": list(OBSERVATION_TYPES),
        "champion_variant_id": CHAMPION_VARIANT,
        "candidate_variant_id": CANDIDATE_VARIANT,
        "control_variant_id": CONTROL_VARIANT,
    }


def export_forward_monitoring_readiness(root: Path) -> Path:
    root = Path(root)
    path = root / READINESS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_forward_monitoring_readiness(root))
    return path


def export_forward_monitoring_data_requirements(root: Path) -> Path:
    root = Path(root)
    path = root / REQUIREMENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_forward_monitoring_data_requirements(root))
    return path
