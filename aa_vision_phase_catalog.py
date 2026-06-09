"""Vision phase catalog loader and validation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

DEFAULT_CATALOG_PATH = Path("control") / "vision_automation" / "phase_catalog.json"


def catalog_path(root: Path) -> Path:
    return Path(root) / DEFAULT_CATALOG_PATH


def load_phase_catalog(root: Path) -> Dict[str, Any]:
    path = catalog_path(root)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return dict(data) if isinstance(data, dict) else {}
    except Exception:
        return {}


def get_phase(root: Path, phase_id: str) -> Optional[Dict[str, Any]]:
    catalog = load_phase_catalog(root)
    for phase in catalog.get("phases") or []:
        if isinstance(phase, dict) and phase.get("phase_id") == phase_id:
            return phase
    return None


def list_phase_ids(root: Path) -> List[str]:
    catalog = load_phase_catalog(root)
    return [str(p.get("phase_id")) for p in (catalog.get("phases") or []) if isinstance(p, dict) and p.get("phase_id")]


def allowed_next_phases(root: Path, phase_id: str) -> List[str]:
    phase = get_phase(root, phase_id)
    if not phase:
        return []
    structured = phase.get("allowed_next_phases_after_external_review")
    if isinstance(structured, list) and structured:
        return [str(p).strip() for p in structured if str(p).strip()]
    raw = phase.get("allowed_next_after_external_review") or []
    if isinstance(raw, str):
        return [p.strip() for p in raw.replace(" OR ", "|").split("|") if p.strip()]
    if isinstance(raw, list):
        out: List[str] = []
        for item in raw:
            if isinstance(item, str):
                out.extend([p.strip() for p in item.replace(" OR ", "|").split("|") if p.strip()])
        return out
    return []


def pending_branch_options(root: Path, phase_id: str) -> List[str]:
    opts = allowed_next_phases(root, phase_id)
    if len(opts) > 1:
        return opts
    return []


def is_transition_allowed(root: Path, from_phase: str, to_phase: str) -> bool:
    if to_phase == "NONE":
        return False
    allowed = allowed_next_phases(root, from_phase)
    return to_phase in allowed


def build_default_catalog() -> Dict[str, Any]:
    return {
        "schema_version": 9,
        "program": "MARKTANALYSE_DECISION_COCKPIT",
        "review_chain": "V1 -> V1R -> V1R2 -> V1R3 -> V2 -> V2R -> V3 -> V4 -> V4R -> V4R2 -> V4R3 -> V5 -> V5R -> COMPLETE_AWAITING_OPERATIONAL_DECISION",
        "phases": [
            {
                "phase_id": "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
                "phase_key": "V1",
                "type": "DEVELOPMENT_ONLY",
                "review_zip": "codex_v1_evidence_and_cascade_review.zip",
                "allowed_next_after_external_review": "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
                "phase_key": "V1R",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V1R.md",
                "review_zip": "codex_v1r_evidence_controller_review.zip",
                "allowed_next_after_external_review": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
                "phase_key": "V1R2",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V1R2.md",
                "review_zip": "codex_v1r2_review_chain_review.zip",
                "allowed_next_after_external_review": "V1R3_AUTHORIZED_COMPLETION_GATE",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V1R3_AUTHORIZED_COMPLETION_GATE",
                "phase_key": "V1R3",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V1R3.md",
                "review_zip": "codex_v1r3_authorized_completion_review.zip",
                "allowed_next_after_external_review": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
                "phase_key": "V2",
                "type": "READ_ONLY_HISTORICAL_EVIDENCE_COMPUTATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V2.md",
                "review_zip": "codex_v2_robustness_review.zip",
                "allowed_next_after_external_review": "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION",
                "operative_jobs_allowed": False,
                "existing_artifact_postprocessing_allowed": True,
                "historical_backtest_regeneration_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION",
                "phase_key": "V2R",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V2R.md",
                "review_zip": "codex_v2r_statistical_validity_review.zip",
                "allowed_next_after_external_review": "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
                "phase_key": "V3",
                "type": "DEVELOPMENT_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V3.md",
                "review_zip": "codex_v3_monitor_foundation_review.zip",
                "allowed_next_phases_after_external_review": [
                    "V3S_SHADOW_OBSERVATION_ACTIVATION",
                    "V4_DECISION_COCKPIT_GUI_INTEGRATION",
                ],
                "allowed_next_after_external_review": "V3S_SHADOW_OBSERVATION_ACTIVATION OR V4_DECISION_COCKPIT_GUI_INTEGRATION",
                "automatic_selection_allowed": False,
                "operative_jobs_allowed": False,
                "shadow_collection_allowed": False,
                "paper_simulation_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V3S_SHADOW_OBSERVATION_ACTIVATION",
                "phase_key": "V3S",
                "type": "OPTIONAL_FORWARD_SHADOW_ACTIVATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V3S.md",
                "review_zip": "codex_v3s_shadow_activation_review.zip",
                "allowed_next_after_external_review": "V3P_PAPER_SIMULATION_ACTIVATION OR V4_DECISION_COCKPIT_GUI_INTEGRATION",
                "automatic_selection_allowed": False,
                "operative_jobs_allowed": True,
                "shadow_collection_allowed": True,
                "paper_simulation_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V3P_PAPER_SIMULATION_ACTIVATION",
                "phase_key": "V3P",
                "type": "OPTIONAL_PAPER_SIMULATION_ACTIVATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V3P.md",
                "review_zip": "codex_v3p_paper_activation_review.zip",
                "allowed_next_after_external_review": "V4_DECISION_COCKPIT_GUI_INTEGRATION",
                "automatic_selection_allowed": False,
                "operative_jobs_allowed": True,
                "shadow_collection_allowed": True,
                "paper_simulation_allowed": True,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V4_DECISION_COCKPIT_GUI_INTEGRATION",
                "phase_key": "V4",
                "type": "READ_ONLY_GUI_IMPLEMENTATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V4.md",
                "review_zip": "codex_v4_gui_review.zip",
                "allowed_next_after_external_review": "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
            },
            {
                "phase_id": "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
                "phase_key": "V4R",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V4R.md",
                "review_zip": "codex_v4r_gui_safety_review.zip",
                "allowed_next_after_external_review": "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
                "phase_key": "V4R2",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V4R2.md",
                "review_zip": "codex_v4r2_final_gui_gate_review.zip",
                "allowed_next_after_external_review": "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
                "phase_key": "V4R3",
                "type": "REMEDIATION_ONLY",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V4R3.md",
                "review_zip": "codex_v4r3_final_build_gate_review.zip",
                "allowed_next_after_external_review": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
                "phase_key": "V5",
                "type": "BUILD_AND_STATIC_VERIFICATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V5.md",
                "review_zip": "codex_v5_exe_build_review.zip",
                "allowed_next_after_external_review": "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR",
                "operative_jobs_allowed": False,
                "exe_build_allowed": True,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR",
                "phase_key": "V5R",
                "type": "BUILD_REMEDIATION_AND_STATIC_VERIFICATION",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_V5R.md",
                "review_zip": "codex_v5r_standalone_exe_review.zip",
                "allowed_next_after_external_review": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
                "operative_jobs_allowed": False,
                "exe_build_allowed": True,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
            {
                "phase_id": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
                "phase_key": "FINAL",
                "type": "TERMINAL_REVIEW_STATE",
                "approval_file": "EXTERNAL_REVIEW_APPROVAL_FINAL.md",
                "allowed_next_after_external_review": "NONE",
                "operative_jobs_allowed": False,
                "exe_build_allowed": False,
                "exe_execution_allowed": False,
                "promotion_allowed": False,
                "real_money_execution_allowed": False,
            },
        ],
    }


def ensure_phase_catalog(root: Path) -> Path:
    root = Path(root)
    path = catalog_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_phase_catalog(root)
    target = build_default_catalog()
    needs_sync = (
        not path.is_file()
        or int(current.get("schema_version", 0) or 0) < int(target["schema_version"])
        or int(current.get("schema_version", 0) or 0) < int(target["schema_version"])
        or get_phase(root, "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION") is None
        or not (get_phase(root, "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION") or {}).get(
            "allowed_next_phases_after_external_review"
        )
        or get_phase(root, "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION") is None
        or (get_phase(root, "V4_DECISION_COCKPIT_GUI_INTEGRATION") or {}).get(
            "allowed_next_after_external_review"
        )
        != "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION"
        or get_phase(root, "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE") is None
        or (get_phase(root, "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION") or {}).get(
            "allowed_next_after_external_review"
        )
        != "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE"
        or get_phase(root, "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE") is None
        or (get_phase(root, "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE") or {}).get(
            "allowed_next_after_external_review"
        )
        != "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE"
    )
    if needs_sync:
        atomic_write_json(path, target)
    return path


def sync_phase_catalog(root: Path) -> Path:
    """Force-write current catalog definition (used during remediation upgrades)."""
    root = Path(root)
    path = catalog_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, build_default_catalog())
    return path
