"""Forward monitoring schema definitions (V3 foundation — read-only)."""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, Tuple

from aa_evidence_schema import LOCKED_CHAMPION

SCHEMA_VERSION = 1
MODE = "READ_ONLY_MONITORING_FOUNDATION"

CHAMPION_VARIANT = LOCKED_CHAMPION
CANDIDATE_VARIANT = "MOM_63_TOP12"
CONTROL_VARIANT = "M1_MOM_BLEND_MATCHED_CONTROLS"

MONITORING_MODES: Tuple[str, ...] = (
    "NOT_CONFIGURED",
    "BLOCKED",
    "READY_FOR_EXTERNAL_ACTIVATION_REVIEW",
    "ACTIVE_READ_ONLY_OBSERVATION",
    "INSUFFICIENT_EVIDENCE",
    "INCIDENT_BLOCKED",
)

V3_ALLOWED_MONITORING_MODES: FrozenSet[str] = frozenset(
    {"BLOCKED", "READY_FOR_EXTERNAL_ACTIVATION_REVIEW", "INSUFFICIENT_EVIDENCE"}
)

V3_FORBIDDEN_MONITORING_MODES: FrozenSet[str] = frozenset({"ACTIVE_READ_ONLY_OBSERVATION"})

OBSERVATION_TYPES: Tuple[str, ...] = (
    "FORWARD_MONITORING",
    "SHADOW_OBSERVATION",
    "PAPER_SIMULATION",
)


def base_monitoring_fields(*, observation_type: str) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": MODE,
        "observation_type": observation_type,
        "activation_status": "BLOCKED",
        "activation_externally_approved": False,
        "operative_jobs_started": False,
        "promotion_allowed": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "champion_variant_id": CHAMPION_VARIANT,
        "candidate_variant_id": CANDIDATE_VARIANT,
        "control_variant_id": CONTROL_VARIANT,
        "required_inputs": [],
        "available_inputs": [],
        "missing_inputs": [],
        "active_blockers": [],
        "source_artifacts": [],
        "display_messages": [],
    }


def validate_v3_activation_status(status: str) -> bool:
    return status in V3_ALLOWED_MONITORING_MODES


def validate_monitoring_payload(payload: Dict[str, Any]) -> Tuple[bool, list[str]]:
    errors: list[str] = []
    for field in (
        "schema_version",
        "mode",
        "observation_type",
        "activation_status",
        "activation_externally_approved",
        "operative_jobs_started",
        "promotion_allowed",
        "paper_eligible",
        "real_money_eligible",
        "champion_variant_id",
    ):
        if field not in payload:
            errors.append(f"missing_field:{field}")
    if payload.get("activation_status") in V3_FORBIDDEN_MONITORING_MODES:
        errors.append("forbidden_activation_status_in_v3")
    if payload.get("activation_status") not in V3_ALLOWED_MONITORING_MODES:
        if payload.get("activation_status") not in MONITORING_MODES:
            errors.append("unknown_activation_status")
        else:
            errors.append("activation_status_not_allowed_in_v3")
    if payload.get("operative_jobs_started") is True:
        errors.append("operative_jobs_started_true")
    if payload.get("promotion_allowed") is True:
        errors.append("promotion_allowed_true")
    if payload.get("paper_eligible") is True:
        errors.append("paper_eligible_true")
    if payload.get("real_money_eligible") is True:
        errors.append("real_money_eligible_true")
    if payload.get("activation_externally_approved") is True:
        errors.append("activation_externally_approved_true")
    return len(errors) == 0, errors
