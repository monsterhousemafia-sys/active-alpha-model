"""Read-only Decision Cockpit view model (V4R2 / V4R3 — fail-closed, no writes)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from aa_champion_cockpit_phase_h import build_operator_transparency_de
from aa_champion_governance import build_champion_governance_de
from aa_evidence_schema import EVIDENCE_STAGES, LOCKED_CHAMPION, resolve_locked_champion
from aa_authorization_policy import (
    is_authorization_governance_blocked,
    is_operational_blocked,
    resolve_authorization_status,
    resolve_governance_automation_display,
)
from aa_evidence_manifest import compose_evidence_manifest, load_evidence_manifest, validate_evidence_manifest

EXPERIMENT_ID = "EXP_INITIAL_MOM_63_TOP12"
EXPECTED_CANDIDATE = "MOM_63_TOP12"
EXPECTED_CONTROL = "M1_MOM_BLEND_MATCHED_CONTROLS"

EVIDENCE_LADDER = list(EVIDENCE_STAGES)
REVIEW_CHAIN = "V1 -> V1R -> V1R2 -> V1R3 -> V2 -> V2R -> V3 -> V4 -> V4R -> V4R2 -> V4R3 -> V5 -> V5R"

READ_ONLY_BANNERS = (
    "NO LIVE TRADING",
    "NO AUTO PROMOTION",
    "READ-ONLY DECISION COCKPIT",
)

WHY_NOT_PROMOTED_EXPLANATORY = (
    "Challenger-specific turnover is not verified.",
    "Cost Stress Gate is not passed.",
    "Deflated Sharpe Ratio is below required confidence.",
    "Robustness evidence is partial only.",
    "P9 is not externally reviewed as Shadow/Paper readiness.",
    "Shadow activation has not been externally approved.",
    "Paper activation has not been externally approved.",
    "Automatic promotion is disabled.",
    "Real-money execution is disabled.",
)

CRITICAL_SOURCES = (
    "promotion_gate_config.yaml",
    "control/auto_promotion_status.json",
    "control/promotion_status.json",
    "control/system_health.json",
    "control/last_known_good_state.json",
    "control/evidence/current_evidence_status.json",
    "control/evidence/cost_stress_status.json",
    "control/evidence/robustness_status.json",
    "control/evidence/multiple_testing_status.json",
    "control/evidence/forward_monitoring_readiness_status.json",
    "control/evidence/shadow_monitor_status.json",
    "control/evidence/paper_monitor_status.json",
    f"control/experiments/{EXPERIMENT_ID}.yaml",
)

AUTOMATION_CFG_KEYS = (
    ("AUTO_RESEARCH", "auto_research_enabled"),
    ("AUTO_PROMOTE_PAPER", "auto_promote_paper_enabled"),
    ("AUTO_PROMOTE_SIGNAL", "auto_promote_signal_enabled"),
    ("AUTO_EXECUTE_REAL_MONEY", "auto_execute_real_money_enabled"),
)

SHADOW_REQUIRED_FIELDS = (
    "activation_status",
    "activation_externally_approved",
    "operative_jobs_started",
    "shadow_collection_started",
    "promotion_allowed",
    "paper_eligible",
    "real_money_eligible",
)

PAPER_REQUIRED_FIELDS = (
    "activation_status",
    "activation_externally_approved",
    "operative_jobs_started",
    "paper_simulation_started",
    "promotion_allowed",
    "paper_eligible",
    "real_money_eligible",
)

CHAMPION_SOURCE_POLICY = (
    "control/evidence/current_evidence_status.json",
    "control/last_known_good_state.json",
    "control/auto_promotion_status.json",
    "model_output_sp500_pit_t212/latest_validated_run.json",
)

CONTROLLER_REQUIRED_FIELDS = (
    "current_executed_phase",
    "expected_next_phase",
    "authorized_phase",
    "execution_status",
    "next_phase_authorized",
)

EXPECTED_MANIFEST_FIELDS = {
    "experiment_id": EXPERIMENT_ID,
    "candidate_variant": EXPECTED_CANDIDATE,
    "champion_reference": LOCKED_CHAMPION,
    "control_reference": EXPECTED_CONTROL,
    "decision_status": "RESEARCH_ONLY",
    "current_evidence_stage": "BACKTESTED",
}

VALID_HOOKS_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "MISSING"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return (dict(data) if isinstance(data, dict) else {}), "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def _read_yaml(path: Path) -> Tuple[Dict[str, Any], str]:
    if not path.is_file():
        return {}, "MISSING"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return (dict(data) if isinstance(data, dict) else {}), "OK"
    except Exception:
        return {}, "UNPARSEABLE"


def _validate_hooks_schema(root: Path) -> Dict[str, Any]:
    path = root / ".cursor" / "hooks.json"
    if not path.is_file():
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "missing_file",
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "unparseable",
        }
    if not isinstance(raw, dict):
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "not_object",
        }
    if raw.get("version") != VALID_HOOKS_VERSION:
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "invalid_version",
        }
    if "hooks" not in raw:
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "hooks_field_missing",
        }
    hooks = raw.get("hooks")
    if not isinstance(hooks, dict):
        return {
            "hooks_status": "UNKNOWN",
            "schema_valid": False,
            "blocked_for_safety": True,
            "schema_error": "hooks_not_dict",
        }
    if hooks:
        return {
            "hooks_status": "ACTIVE",
            "schema_valid": True,
            "blocked_for_safety": True,
            "schema_error": None,
        }
    return {
        "hooks_status": "DISABLED",
        "schema_valid": True,
        "blocked_for_safety": False,
        "schema_error": None,
    }


def _hooks_status(root: Path) -> str:
    return str(_validate_hooks_schema(root)["hooks_status"])


def _automation_flag(cfg: Dict[str, Any], key: str) -> str:
    if not cfg:
        return "UNKNOWN"
    val = cfg.get(key)
    if val is True:
        return "ENABLED"
    if val is False:
        return "DISABLED"
    return "UNKNOWN"


def _safe_bool(val: Any) -> Optional[bool]:
    if val is True:
        return True
    if val is False:
        return False
    return None


def _eligibility_display(val: Any, *, source_ok: bool) -> str:
    if not source_ok:
        return "UNKNOWN — BLOCKED FOR SAFETY"
    b = _safe_bool(val)
    if b is True:
        return "YES"
    if b is False:
        return "NO"
    return "UNKNOWN — BLOCKED FOR SAFETY"


def _read_only_blocked_for_safety(auth_status: Dict[str, Any]) -> bool:
    if not auth_status:
        return True
    if auth_status.get("operational_authorized"):
        return False
    return auth_status.get("operational_status") == "BLOCKED_FOR_SAFETY" or auth_status.get("status") in (
        "MANUAL_READ_ONLY_ONLY",
        "CONFLICT_BLOCKED_FOR_SAFETY",
        "BLOCKED_FOR_SAFETY",
    )


def _governance_eligibility_display(val: Any, *, source_ok: bool, auth_status: Dict[str, Any]) -> str:
    if _read_only_blocked_for_safety(auth_status):
        return "NO"
    if auth_status.get("conflicting_sources"):
        return "NO"
    return _eligibility_display(val, source_ok=source_ok)


def _extract_champion_from_source(source: str, data: Dict[str, Any], ok: bool) -> Tuple[Optional[str], str]:
    if not ok:
        return None, "SOURCE_UNAVAILABLE"
    if source == "control/evidence/current_evidence_status.json":
        val = data.get("champion_variant_id")
    elif source == "control/last_known_good_state.json":
        val = data.get("validated_variant_id") or data.get("variant_id")
    elif source == "control/auto_promotion_status.json":
        val = data.get("champion_variant_id")
        if not val:
            val = (data.get("gate_evaluation") or {}).get("champion_variant_id")
    elif source == "model_output_sp500_pit_t212/latest_validated_run.json":
        val = data.get("variant_id")
    else:
        return None, "UNKNOWN_SOURCE"
    if not val:
        return None, "FIELD_MISSING"
    return str(val), "OK"


def _resolve_champion(
    *,
    expected_champion: str,
    evidence: Dict[str, Any],
    evidence_ok: bool,
    lkg: Dict[str, Any],
    lkg_ok: bool,
    auto_status: Dict[str, Any],
    auto_ok: bool,
    validated_run: Dict[str, Any],
    validated_ok: bool,
) -> Dict[str, Any]:
    """Minimal authoritative champion policy: all four sources must agree."""
    source_data = {
        "control/evidence/current_evidence_status.json": (evidence, evidence_ok),
        "control/last_known_good_state.json": (lkg, lkg_ok),
        "control/auto_promotion_status.json": (auto_status, auto_ok),
        "model_output_sp500_pit_t212/latest_validated_run.json": (validated_run, validated_ok),
    }
    observed: List[str] = []
    policy_errors: List[str] = []
    for src in CHAMPION_SOURCE_POLICY:
        data, ok = source_data[src]
        val, reason = _extract_champion_from_source(src, data, ok)
        if reason != "OK" or not val:
            policy_errors.append(f"{src}:{reason}")
            continue
        observed.append(val)

    if policy_errors or len(observed) != len(CHAMPION_SOURCE_POLICY):
        return {
            "active_champion": "UNKNOWN",
            "champion_status": "CHAMPION STATUS MISSING OR CONFLICTING",
            "blocked_for_safety": True,
            "expected_champion": expected_champion,
            "sources_agree": False,
            "policy_errors": policy_errors,
        }

    unique = sorted(set(observed))
    if len(unique) > 1:
        return {
            "active_champion": "UNKNOWN",
            "champion_status": "CHAMPION STATUS MISSING OR CONFLICTING",
            "blocked_for_safety": True,
            "expected_champion": expected_champion,
            "sources_agree": False,
            "conflicting_values": unique,
        }
    return {
        "active_champion": unique[0],
        "champion_status": "VERIFIED_FROM_SOURCES" if unique[0] == expected_champion else "UNEXPECTED_CHAMPION",
        "blocked_for_safety": unique[0] != expected_champion,
        "expected_champion": expected_champion,
        "sources_agree": True,
        "policy_validated": True,
    }


def _resolve_manifest_refs(experiment: Dict[str, Any], exp_ok: bool) -> Dict[str, Any]:
    if not exp_ok:
        return {
            "candidate": "UNKNOWN",
            "control_reference": "UNKNOWN",
            "manifest_status": "EXPERIMENT MANIFEST MISSING OR CONFLICTING",
            "blocked_for_safety": True,
        }
    candidate = experiment.get("candidate_variant")
    control = experiment.get("control_reference")
    if not candidate or not control:
        return {
            "candidate": "UNKNOWN",
            "control_reference": "UNKNOWN",
            "manifest_status": "EXPERIMENT MANIFEST MISSING OR CONFLICTING",
            "blocked_for_safety": True,
        }
    return {
        "candidate": str(candidate),
        "control_reference": str(control),
        "manifest_status": "VERIFIED_FROM_MANIFEST",
        "blocked_for_safety": False,
        "expected_candidate": EXPECTED_CANDIDATE,
        "expected_control": EXPECTED_CONTROL,
    }


def _resolve_experiment_panel(experiment: Dict[str, Any], exp_ok: bool) -> Dict[str, Any]:
    if not exp_ok:
        return {
            "experiment_id": EXPERIMENT_ID,
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "status_message": "EXPERIMENT MANIFEST MISSING OR CONFLICTING",
            "blocked_for_safety": True,
            "candidate": None,
            "champion_reference": None,
            "control_reference": None,
            "decision_status": None,
            "current_evidence_stage": None,
        }
    mismatches: List[str] = []
    for field, expected in EXPECTED_MANIFEST_FIELDS.items():
        actual = experiment.get(field)
        if actual is None or str(actual) != str(expected):
            mismatches.append(field)
    if mismatches:
        return {
            "experiment_id": EXPERIMENT_ID,
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "status_message": "EXPERIMENT MANIFEST MISSING OR CONFLICTING",
            "blocked_for_safety": True,
            "mismatches": mismatches,
            "candidate": None,
            "champion_reference": None,
            "control_reference": None,
            "decision_status": None,
            "current_evidence_stage": None,
        }
    return {
        "experiment_id": str(experiment["experiment_id"]),
        "display": "VERIFIED",
        "status_message": "VERIFIED_FROM_MANIFEST",
        "blocked_for_safety": False,
        "candidate": str(experiment["candidate_variant"]),
        "champion_reference": str(experiment["champion_reference"]),
        "control_reference": str(experiment["control_reference"]),
        "decision_status": str(experiment["decision_status"]),
        "current_evidence_stage": str(experiment["current_evidence_stage"]),
    }


def _resolve_controller_state(
    automation: Dict[str, Any],
    automation_ok: bool,
    *,
    auth_status: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not automation_ok:
        return {
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "blocked_for_safety": True,
            "lifecycle_message": "CONTROLLER STATE UNKNOWN OR UNSAFE\nBLOCKED FOR SAFETY",
            "current_executed_phase": None,
            "expected_next_phase": None,
            "authorized_phase": None,
            "current_running_phase": None,
            "execution_status": None,
            "next_phase_authorized_display": "UNKNOWN",
        }
    missing = [f for f in CONTROLLER_REQUIRED_FIELDS if f not in automation]
    running_phase = automation.get("current_running_phase") or ""
    if missing:
        return {
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "blocked_for_safety": True,
            "lifecycle_message": "CONTROLLER STATE UNKNOWN OR UNSAFE\nBLOCKED FOR SAFETY",
            "missing_fields": missing,
            "current_executed_phase": automation.get("current_executed_phase"),
            "expected_next_phase": automation.get("expected_next_phase"),
            "authorized_phase": automation.get("authorized_phase"),
            "current_running_phase": running_phase,
            "execution_status": automation.get("execution_status"),
            "next_phase_authorized_display": "UNKNOWN",
        }
    next_auth = automation.get("next_phase_authorized")
    authorized_phase = automation.get("authorized_phase") or ""
    execution_status = str(automation.get("execution_status") or "")
    executed = str(automation.get("current_executed_phase") or "")
    expected_next = str(automation.get("expected_next_phase") or "")
    blocked = False
    block_reasons: List[str] = []
    if next_auth is True:
        blocked = True
        block_reasons.append("next_phase_authorized_true_before_external_review")
    if execution_status == "AWAITING_EXTERNAL_REVIEW" and authorized_phase:
        blocked = True
        block_reasons.append("authorized_phase_set_while_awaiting_review")
    allowed_expected = {
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
        "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
        "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
        "COMPLETE_AWAITING_OPERATIONAL_DECISION",
        "NONE",
    }
    auth = auth_status or {}
    auth_blocked = is_authorization_governance_blocked(auth)
    if auth_blocked:
        blocked = True
        block_reasons.append("authorization_source_conflict")
    if expected_next and expected_next not in allowed_expected:
        blocked = True
        block_reasons.append("unexpected_expected_next_phase")
    next_display = "YES" if next_auth is True else "NO" if next_auth is False else "UNKNOWN"
    if next_auth not in (True, False):
        blocked = True
        block_reasons.append("next_phase_authorized_not_boolean")

    lifecycle_message = ""
    if not blocked:
        if (
            execution_status == "RUNNING_AUTHORIZED_PHASE"
            and authorized_phase == "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
            and running_phase == "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
        ):
            lifecycle_message = (
                "V5 BUILD IN PROGRESS — NOT EXTERNALLY REVIEWED\n"
                "READ-ONLY / NO OPERATIONAL AUTHORIZATION"
            )
        elif (
            executed == "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
            and expected_next == "COMPLETE_AWAITING_OPERATIONAL_DECISION"
            and execution_status == "AWAITING_EXTERNAL_REVIEW"
            and not authorized_phase
            and not running_phase
            and next_auth is False
        ):
            lifecycle_message = (
                "EXE BUILD COMPLETE — PENDING EXTERNAL REVIEW\n"
                "NO OPERATIONAL AUTHORIZATION\n"
                "NO LIVE TRADING\n"
                "NO AUTO PROMOTION"
            )
        elif executed == "COMPLETE_AWAITING_OPERATIONAL_DECISION" and next_auth is False:
            lifecycle_message = (
                "DECISION COCKPIT AVAILABLE FOR MANUAL REVIEW\n"
                "NO OPERATIONAL AUTHORIZATION\n"
                "Authoritative Review State: Manual read-only review only"
            )
        elif auth_blocked:
            lifecycle_message = (
                "Authorization Status: BLOCKED FOR SAFETY\n"
                "Reason: Conflicting authorization sources\n"
                "Authoritative Review State: Manual read-only review only"
            )
        elif (
            executed == "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE"
            and expected_next == "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION"
            and execution_status == "AWAITING_EXTERNAL_REVIEW"
        ):
            lifecycle_message = "AWAITING V5 AUTHORIZATION — READ-ONLY / NO OPERATIONAL AUTHORIZATION"

    if blocked:
        lifecycle_message = "CONTROLLER STATE UNKNOWN OR UNSAFE\nBLOCKED FOR SAFETY"

    return {
        "display": "UNKNOWN — BLOCKED FOR SAFETY" if blocked else "VERIFIED",
        "blocked_for_safety": blocked,
        "block_reasons": block_reasons,
        "lifecycle_message": lifecycle_message,
        "current_executed_phase": automation.get("current_executed_phase"),
        "expected_next_phase": automation.get("expected_next_phase"),
        "authorized_phase": authorized_phase,
        "current_running_phase": running_phase or None,
        "execution_status": automation.get("execution_status"),
        "next_phase_authorized": next_auth,
        "next_phase_authorized_display": next_display,
    }


def _resolve_evidence_stage(evidence: Dict[str, Any], evidence_ok: bool) -> Dict[str, Any]:
    if not evidence_ok:
        return {
            "stage": "UNKNOWN",
            "summary": "Current verified stage: UNKNOWN. MISSING OR CONFLICTING EVIDENCE.",
            "source_valid": False,
        }
    stage = str(evidence.get("current_evidence_stage") or "UNKNOWN")
    if stage not in EVIDENCE_STAGES:
        return {
            "stage": "UNKNOWN",
            "summary": "Current verified stage: UNKNOWN. MISSING OR CONFLICTING EVIDENCE.",
            "source_valid": False,
        }
    if stage == "BACKTESTED":
        summary = (
            "Current verified stage: BACKTESTED. "
            "No reviewed forward, shadow or paper readiness established."
        )
    else:
        summary = f"Current verified stage: {stage}."
    return {"stage": stage, "summary": summary, "source_valid": True}


def _build_ladder(stage_info: Dict[str, Any], blockers: List[str]) -> List[Dict[str, Any]]:
    if not stage_info.get("source_valid"):
        return [
            {
                "stage": step,
                "status": "UNKNOWN",
                "blocker": "MISSING OR CONFLICTING EVIDENCE",
            }
            for step in EVIDENCE_LADDER
            if step != "REJECTED"
        ]
    stage = stage_info["stage"]
    current_rank = EVIDENCE_LADDER.index(stage) if stage in EVIDENCE_LADDER else -1
    ladder: List[Dict[str, Any]] = []
    for i, step in enumerate(EVIDENCE_LADDER):
        if step == "REJECTED":
            continue
        if i == current_rank:
            ladder.append({"stage": step, "status": "CURRENT", "blocker": None})
        elif current_rank >= 0 and i < current_rank:
            ladder.append({"stage": step, "status": "REACHED", "blocker": None})
        else:
            ladder.append(
                {
                    "stage": step,
                    "status": "NOT_REACHED",
                    "blocker": blockers[0] if blockers else "INSUFFICIENT_EVIDENCE",
                }
            )
    return ladder


def _detect_conflicts(
    auto_status: Dict[str, Any],
    auto_ok: bool,
    promotion_status: Dict[str, Any],
    promo_ok: bool,
    evidence: Dict[str, Any],
    evidence_ok: bool,
) -> List[str]:
    conflicts: List[str] = []
    if auto_ok and promo_ok:
        for mode in ("AUTO_RESEARCH", "AUTO_PROMOTE_PAPER", "AUTO_PROMOTE_SIGNAL", "AUTO_EXECUTE_REAL_MONEY"):
            a = (auto_status.get("automation_modes") or {}).get(mode)
            p = (promotion_status.get("automation_modes") or {}).get(mode)
            if a and p and a != p:
                conflicts.append(f"CONFLICTING SOURCE DATA: {mode} auto={a} promotion={p}")

    if auto_ok and promo_ok:
        auto_gates = (auto_status.get("gate_evaluation") or {}).get("gates") or {}
        promo_gates = promotion_status.get("gates") or {}
        a_econ = (auto_gates.get("ECONOMIC_VALUE_GATE") or {}).get("pass")
        p_econ = (promo_gates.get("ECONOMIC_VALUE_GATE") or {}).get("pass")
        if a_econ is not None and p_econ is not None and a_econ != p_econ:
            conflicts.append(
                f"ECONOMIC_VALUE_GATE source conflict: auto_promotion_status={a_econ}, promotion_status={p_econ}"
            )

    if evidence_ok:
        for c in evidence.get("source_conflicts") or []:
            conflicts.append(str(c))

    return sorted(set(conflicts))


def _monitoring_field(
    data: Dict[str, Any],
    source_ok: bool,
    *,
    required_fields: Tuple[str, ...],
    bool_key: Optional[str] = None,
) -> Dict[str, Any]:
    if not source_ok:
        out: Dict[str, Any] = {
            "status": "UNKNOWN — BLOCKED FOR SAFETY",
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "evidence_missing": True,
        }
        if bool_key:
            out[bool_key] = None
        return out

    missing = [f for f in required_fields if f not in data]
    if missing:
        out = {
            "status": "UNKNOWN — BLOCKED FOR SAFETY",
            "display": "UNKNOWN — BLOCKED FOR SAFETY",
            "evidence_missing": True,
            "missing_fields": missing,
        }
        if bool_key:
            out[bool_key] = None
        return out

    status = data.get("activation_status") or "UNKNOWN"
    out = {
        "status": status,
        "display": status,
        "evidence_missing": False,
    }
    for field in required_fields:
        out[field] = data.get(field)
    if bool_key:
        out[bool_key] = data.get(bool_key)
    return out


def _automation_safety_block(
    cfg_ok: bool,
    flags: Dict[str, str],
    *,
    operational_authorized: bool = False,
) -> Tuple[bool, List[str]]:
    warnings: List[str] = []
    if operational_authorized:
        return False, warnings
    if not cfg_ok:
        warnings.append("UNSAFE OR UNVERIFIED AUTOMATION CONFIGURATION")
        warnings.append("BLOCKED FOR SAFETY")
        return True, warnings
    if any(v in ("ENABLED", "UNKNOWN") for v in flags.values()):
        warnings.append("UNSAFE OR UNVERIFIED AUTOMATION CONFIGURATION")
        warnings.append("BLOCKED FOR SAFETY")
        return True, warnings
    return False, warnings


def _hooks_safety_block(hooks_info: Dict[str, Any]) -> Tuple[bool, List[str]]:
    if hooks_info.get("blocked_for_safety"):
        if hooks_info.get("hooks_status") == "ACTIVE":
            return True, ["CURSOR HOOKS ACTIVE OR UNVERIFIED", "BLOCKED FOR SAFETY"]
        return True, ["CURSOR HOOKS ACTIVE OR UNVERIFIED", "BLOCKED FOR SAFETY"]
    return False, []


def load_decision_cockpit(root: Path) -> Dict[str, Any]:
    root = Path(root)
    source_status: Dict[str, str] = {}

    promo_cfg, st = _read_yaml(root / "promotion_gate_config.yaml")
    source_status["promotion_gate_config.yaml"] = st
    auto_status, st2 = _read_json(root / "control" / "auto_promotion_status.json")
    source_status["control/auto_promotion_status.json"] = st2
    promotion_status, st3 = _read_json(root / "control" / "promotion_status.json")
    source_status["control/promotion_status.json"] = st3
    health, st4 = _read_json(root / "control" / "system_health.json")
    source_status["control/system_health.json"] = st4
    lkg, st5 = _read_json(root / "control" / "last_known_good_state.json")
    source_status["control/last_known_good_state.json"] = st5
    evidence, st6 = _read_json(root / "control" / "evidence" / "current_evidence_status.json")
    source_status["control/evidence/current_evidence_status.json"] = st6
    cost_stress, st7 = _read_json(root / "control" / "evidence" / "cost_stress_status.json")
    source_status["control/evidence/cost_stress_status.json"] = st7
    robustness, st8 = _read_json(root / "control" / "evidence" / "robustness_status.json")
    source_status["control/evidence/robustness_status.json"] = st8
    multiple_testing, st9 = _read_json(root / "control" / "evidence" / "multiple_testing_status.json")
    source_status["control/evidence/multiple_testing_status.json"] = st9
    forward_mon, st10 = _read_json(root / "control" / "evidence" / "forward_monitoring_readiness_status.json")
    source_status["control/evidence/forward_monitoring_readiness_status.json"] = st10
    shadow_mon, st11 = _read_json(root / "control" / "evidence" / "shadow_monitor_status.json")
    source_status["control/evidence/shadow_monitor_status.json"] = st11
    paper_mon, st12 = _read_json(root / "control" / "evidence" / "paper_monitor_status.json")
    source_status["control/evidence/paper_monitor_status.json"] = st12
    data_req, st13 = _read_json(root / "control" / "evidence" / "forward_monitoring_data_requirements.json")
    source_status["control/evidence/forward_monitoring_data_requirements.json"] = st13
    automation, st14 = _read_json(root / "control" / "vision_automation" / "automation_state.json")
    source_status["control/vision_automation/automation_state.json"] = st14
    registry, st15 = _read_json(root / "control" / "vision_automation" / "review_registry" / "review_registry.json")
    source_status["control/vision_automation/review_registry/review_registry.json"] = st15
    validated_run, st17 = _read_json(root / "model_output_sp500_pit_t212" / "latest_validated_run.json")
    source_status["model_output_sp500_pit_t212/latest_validated_run.json"] = st17

    exp_rel = f"control/experiments/{EXPERIMENT_ID}.yaml"
    experiment, st16 = _read_yaml(root / exp_rel)
    source_status[exp_rel] = st16

    conflicts = _detect_conflicts(auto_status, st2 == "OK", promotion_status, st3 == "OK", evidence, st6 == "OK")

    expected_champion = resolve_locked_champion(root)
    champion_info = _resolve_champion(
        expected_champion=expected_champion,
        evidence=evidence,
        evidence_ok=st6 == "OK",
        lkg=lkg,
        lkg_ok=st5 == "OK",
        auto_status=auto_status,
        auto_ok=st2 == "OK",
        validated_run=validated_run,
        validated_ok=st17 == "OK",
    )
    manifest_refs = _resolve_manifest_refs(experiment, st16 == "OK")
    experiment_panel = _resolve_experiment_panel(experiment, st16 == "OK")
    auth_status = resolve_authorization_status(root)
    controller_state = _resolve_controller_state(automation, st14 == "OK", auth_status=auth_status)
    stage_info = _resolve_evidence_stage(evidence, st6 == "OK")

    blockers = sorted(
        set(evidence.get("current_active_blockers") or evidence.get("blockers") or [])
        | set(forward_mon.get("active_blockers") or [])
        | set(shadow_mon.get("active_blockers") or [])
        | set(paper_mon.get("active_blockers") or [])
    )

    cost_gate = cost_stress.get("COST_STRESS_GATE") or {} if st7 == "OK" else {}
    mt_ev = multiple_testing.get("MULTIPLE_TESTING_EVIDENCE") or {} if st9 == "OK" else {}
    dsr = multiple_testing.get("deflated_sharpe") or {} if st9 == "OK" else {}
    robust_ev = robustness.get("ROBUSTNESS_EVIDENCE") or {} if st8 == "OK" else {}
    sub_screen = robustness.get("SUBPERIOD_STABILITY_SCREEN") or {} if st8 == "OK" else {}

    forward_m = _monitoring_field(forward_mon, st10 == "OK", required_fields=("activation_status",))
    shadow_m = _monitoring_field(
        shadow_mon,
        st11 == "OK",
        required_fields=SHADOW_REQUIRED_FIELDS,
        bool_key="shadow_collection_started",
    )
    paper_m = _monitoring_field(
        paper_mon,
        st12 == "OK",
        required_fields=PAPER_REQUIRED_FIELDS,
        bool_key="paper_simulation_started",
    )

    missing = [k for k in CRITICAL_SOURCES if source_status.get(k) == "MISSING"]
    unparseable = [k for k in CRITICAL_SOURCES if source_status.get(k) == "UNPARSEABLE"]

    config_automation_flags = {
        label: (_automation_flag(promo_cfg, key) if st == "OK" else "UNKNOWN")
        for label, key in AUTOMATION_CFG_KEYS
    }
    automation_flags = resolve_governance_automation_display(
        root,
        promo_flags=config_automation_flags,
        auth_status=auth_status,
    )
    automation_blocked, automation_warnings = _automation_safety_block(
        st == "OK",
        config_automation_flags,
        operational_authorized=bool(auth_status.get("operational_authorized")),
    )
    if auth_status.get("conflicting_sources"):
        automation_blocked = True
        automation_warnings.extend(
            ["AUTHORIZATION SOURCE CONFLICT", "BLOCKED FOR SAFETY"]
        )

    hooks_info = _validate_hooks_schema(root)
    hooks = str(hooks_info["hooks_status"])
    hooks_blocked, hooks_warnings = _hooks_safety_block(hooks_info)

    prod_out = root / "model_output_sp500_pit_t212"
    ev_manifest, ev_manifest_status = load_evidence_manifest(root, prod_out)
    if not ev_manifest and prod_out.is_dir():
        ev_manifest = compose_evidence_manifest(
            root,
            prod_out,
            variant=str(validated_run.get("variant_id") or expected_champion),
            run_id=str(validated_run.get("run_id") or ""),
        )
    manifest_ok, manifest_errors, manifest_checks = validate_evidence_manifest(root, ev_manifest)

    manifest_fail = prod_out.is_dir() and not manifest_ok

    safety_warnings = automation_warnings + hooks_warnings

    reviews_out: List[Dict[str, Any]] = []
    for entry in registry.get("reviews") or []:
        if isinstance(entry, dict):
            reviews_out.append(
                {
                    "phase_id": entry.get("phase_id"),
                    "review_zip": entry.get("review_zip"),
                    "review_zip_sha256": entry.get("review_zip_sha256"),
                    "external_sealed": bool(entry.get("external_sealed")),
                    "sealed_by": entry.get("external_sealed_by_approval"),
                }
            )

    exp_ok = st16 == "OK"
    experiment_view = {
        "experiment_id": experiment_panel.get("experiment_id", EXPERIMENT_ID),
        "candidate": experiment_panel.get("candidate"),
        "champion_reference": experiment_panel.get("champion_reference"),
        "control_reference": experiment_panel.get("control_reference"),
        "status": experiment_panel.get("decision_status"),
        "evidence_stage": experiment_panel.get("current_evidence_stage"),
        "display": experiment_panel.get("display"),
        "status_message": experiment_panel.get("status_message"),
        "provenance_blockers": experiment.get("blockers") or [] if exp_ok else [],
        "source_status": st16,
        "blocked_for_safety": experiment_panel.get("blocked_for_safety", True),
    }

    operator_transparency = build_operator_transparency_de(root)
    pointer_drift = bool(operator_transparency.get("pointer_drift_active"))

    fail_closed = bool(
        missing
        or unparseable
        or conflicts
        or champion_info.get("blocked_for_safety")
        or manifest_refs.get("blocked_for_safety")
        or experiment_panel.get("blocked_for_safety")
        or controller_state.get("blocked_for_safety")
        or not stage_info.get("source_valid")
        or shadow_m.get("evidence_missing")
        or paper_m.get("evidence_missing")
        or automation_blocked
        or hooks_blocked
        or manifest_fail
        or auth_status.get("conflicting_sources")
        or pointer_drift
    )

    banners = list(READ_ONLY_BANNERS)
    failsafe_banner = operator_transparency.get("failsafe_banner_de")
    if failsafe_banner:
        banners.append(failsafe_banner)

    return {
        "schema_version": 4,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_DECISION_COCKPIT",
        "authorization_status": auth_status,
        "banners": banners,
        "champion_governance_de": build_champion_governance_de(root),
        "operator_transparency_de": operator_transparency,
        "executive_overview": {
            "active_champion": champion_info["active_champion"],
            "champion_status": champion_info.get("champion_status"),
            "champion_blocked_for_safety": champion_info.get("blocked_for_safety", False),
            "expected_champion": expected_champion,
            "candidate": experiment_panel.get("candidate")
            if not experiment_panel.get("blocked_for_safety")
            else "UNKNOWN",
            "control_reference": experiment_panel.get("control_reference")
            if not experiment_panel.get("blocked_for_safety")
            else "UNKNOWN",
            "manifest_status": experiment_panel.get("status_message"),
            "manifest_blocked_for_safety": experiment_panel.get("blocked_for_safety", False),
            "evidence_stage": stage_info["stage"],
            "evidence_stage_summary": stage_info["summary"],
            "source_classification": evidence.get("source_classification") if st6 == "OK" else "UNKNOWN",
            "promotion_eligible_display": _governance_eligibility_display(
                evidence.get("promotion_eligible"), source_ok=st6 == "OK", auth_status=auth_status
            ),
            "paper_eligible_display": _governance_eligibility_display(
                evidence.get("paper_eligible"), source_ok=st6 == "OK", auth_status=auth_status
            ),
            "real_money_eligible_display": _governance_eligibility_display(
                evidence.get("real_money_eligible"), source_ok=st6 == "OK", auth_status=auth_status
            ),
        },
        "controller_state": controller_state,
        "safety_automation": {
            **automation_flags,
            "hooks_status": hooks,
            "hooks_schema_valid": hooks_info.get("schema_valid"),
            "hooks_schema_error": hooks_info.get("schema_error"),
            "system_health": health.get("operational_health") if st4 == "OK" else "UNKNOWN",
            "last_known_good_available": st5 == "OK",
            "controller_status": automation.get("execution_status") if st14 == "OK" else "UNKNOWN",
            "current_executed_phase": automation.get("current_executed_phase") if st14 == "OK" else None,
            "last_sealed_review": next((r for r in reversed(reviews_out) if r.get("external_sealed")), None),
            "safety_banner": "SAFETY STATUS UNKNOWN OR CONFLICTING" if fail_closed else None,
            "safety_warnings": safety_warnings,
            "automation_blocked_for_safety": automation_blocked,
            "hooks_blocked_for_safety": hooks_blocked,
        },
        "evidence_ladder": {
            "stages": _build_ladder(stage_info, blockers),
            "summary": stage_info["summary"],
        },
        "why_not_promoted": {
            "explanatory_reasons": list(WHY_NOT_PROMOTED_EXPLANATORY),
            "current_active_blockers": blockers,
            "source_conflicts": conflicts,
        },
        "cost_stress_robustness": {
            "cost_stress_status": cost_gate.get("evaluation_status") or ("UNKNOWN" if st7 != "OK" else "UNKNOWN"),
            "cost_stress_pass": _safe_bool(cost_gate.get("pass")) if st7 == "OK" else None,
            "cost_stress_blocker": (cost_gate.get("blockers") or ["UNKNOWN"])[0] if st7 == "OK" else "MISSING EVIDENCE",
            "proxy_label": (cost_stress.get("sensitivity_analysis") or {}).get("label", "NOT_GATE_EVIDENCE")
            if st7 == "OK"
            else "UNKNOWN",
            "dsr_probability": dsr.get("dsr_probability"),
            "dsr_required_probability": dsr.get("dsr_required_probability", 0.95),
            "dsr_status": mt_ev.get("status") or dsr.get("status") or ("UNKNOWN" if st9 != "OK" else "UNKNOWN"),
            "pbo_status": multiple_testing.get("PBO_STATUS") if st9 == "OK" else "UNKNOWN",
            "subperiod_screen_pass": sub_screen.get("pass") if st8 == "OK" else None,
            "robustness_status": robust_ev.get("status") if st8 == "OK" else "UNKNOWN",
            "robustness_pass": _safe_bool(robust_ev.get("pass")) if st8 == "OK" else None,
        },
        "monitoring": {
            "forward": forward_m,
            "shadow": shadow_m,
            "paper": paper_m,
            "data_requirements_present": st13 == "OK",
        },
        "experiment_registry": experiment_view,
        "audit_review_chain": {
            "chain": REVIEW_CHAIN,
            "reviews": reviews_out,
            "pending_external_branch_options": automation.get("pending_external_branch_options") or [],
        },
        "source_health": {
            "critical_sources": {k: source_status.get(k, "MISSING") for k in CRITICAL_SOURCES},
            "missing_sources": missing,
            "unparseable_sources": unparseable,
            "conflicts": conflicts,
            "fail_closed": fail_closed,
            "blocked_for_safety": fail_closed,
            "champion_source_policy": list(CHAMPION_SOURCE_POLICY),
        },
        "manifest_validation": {
            "manifest_file_status": ev_manifest_status,
            "validation_pass": manifest_ok,
            "validation_errors": manifest_errors,
            "validation_checks": manifest_checks,
            "latest_verified_run_id": ev_manifest.get("run_id"),
            "variant": ev_manifest.get("variant"),
            "evidence_stage": ev_manifest.get("evidence_stage"),
            "stale_or_inconsistent": bool(manifest_errors),
        },
        "gui_read_only": True,
        "operative_ui_actions_allowed": False,
    }
