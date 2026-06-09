"""Build and load read-only Decision Cockpit review snapshots (V5R)."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from aa_authorization_policy import apply_governance_display_to_cockpit
from aa_decision_cockpit_viewmodel import load_decision_cockpit

SNAPSHOT_REL = Path("control") / "review_snapshot" / "v5r_decision_cockpit_snapshot.json"
G0R_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r_decision_cockpit_snapshot.json"
G0R2_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r2_decision_cockpit_snapshot.json"
G0R3_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r3_decision_cockpit_snapshot.json"
G0R4_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r4_decision_cockpit_snapshot.json"
G0R4R_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r4r_decision_cockpit_snapshot.json"
G0R4R2_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r4r2_decision_cockpit_snapshot.json"
G0R4R3_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g0r4r3_decision_cockpit_snapshot.json"
G1_INDEPENDENT_SNAPSHOT_REL = Path("control") / "review_snapshot" / "g1_independent_research_snapshot.json"
AUTONOMOUS_RESEARCH_SNAPSHOT_REL = Path("control") / "review_snapshot" / "autonomous_research_snapshot.json"
P10_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p10_research_evidence_integration_snapshot.json"
P11_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p11_statistical_research_validation_snapshot.json"
P12A_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p12a_online_market_data_ingestion_snapshot.json"
P12B_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p12b_virtual_execution_engine_snapshot.json"
P12C_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p12c_forward_paper_trading_snapshot.json"
P13_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p13_broker_readiness_snapshot.json"
P14_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p14_paper_forward_snapshot.json"
P15_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p15_paper_runtime_validation_snapshot.json"
P16_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16_forward_observation_scaling_snapshot.json"
P16B_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16b_continuous_forward_runtime_snapshot.json"
P16C_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16c_forward_runtime_correction_snapshot.json"
P16D_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16d_validated_forward_runtime_snapshot.json"
P16E_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16e_fast_track_manual_live_readiness_snapshot.json"
P16F_SNAPSHOT_REL = Path("control") / "review_snapshot" / "p16f_manual_ticket_risk_remediation_snapshot.json"
BUILD_RELEASE_SNAPSHOT = Path("build") / "decision_cockpit" / "v5r_release_embed_snapshot.json"
BUILD_FAIL_CLOSED_SNAPSHOT = Path("build") / "decision_cockpit" / "v5r_fail_closed_test_embed_snapshot.json"
EMBEDDED_NAME = "v5r_decision_cockpit_snapshot.json"
EMBEDDED_RELEASE_NAME = "v5r_release_embed_snapshot.json"
EMBEDDED_FAIL_CLOSED_NAME = "v5r_fail_closed_test_embed_snapshot.json"
RELEASE_SNAPSHOT_SCOPE = "V5R_READ_ONLY_NEUTRAL"

V5R_NEUTRAL_BLOCKERS = [
    "V5R_EXTERNAL_REVIEW_PENDING",
    "NO_OPERATIONAL_AUTHORIZATION",
    "PROMOTION_NOT_ELIGIBLE",
    "PAPER_NOT_ELIGIBLE",
    "REAL_MONEY_NOT_ELIGIBLE",
    "FORWARD_MONITORING_NOT_EXTERNALLY_APPROVED",
    "SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED",
    "PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED",
]

BLOCKERS = [
    "CHALLENGER_TURNOVER_NOT_VERIFIED",
    "COST_STRESS_GATE_NOT_PASSED",
    "DSR_BELOW_REQUIRED_CONFIDENCE",
    "ROBUSTNESS_NOT_PASSED",
    "P9_NOT_EXTERNALLY_REVIEWED",
    "SHADOW_ACTIVATION_NOT_EXTERNALLY_APPROVED",
    "PAPER_ACTIVATION_NOT_EXTERNALLY_APPROVED",
]


def live_cockpit_requested() -> bool:
    """Live project data instead of neutral V5R submission embed."""
    env = os.environ.get("AA_V5R_LIVE_COCKPIT", "auto").strip().lower()
    if env in {"0", "false", "off", "neutral", "submission"}:
        return False
    if env in {"1", "true", "on", "live", "yes"}:
        return True
    return not getattr(sys, "frozen", False)


def is_neutral_release_snapshot(snapshot: Dict[str, Any]) -> bool:
    return snapshot.get("v5r_release_scope") == "NEUTRAL_READ_ONLY_REVIEW_ONLY"


def refresh_live_review_snapshot(root: Path) -> Path:
    """Rebuild review snapshot from current control/model sources."""
    return write_review_snapshot(root)


def load_live_review_snapshot(root: Path) -> Dict[str, Any]:
    path = Path(root) / SNAPSHOT_REL
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = build_review_snapshot(root)
    data["v5r_live_mode"] = True
    data["v5r_data_source"] = "live_project_sources"
    return data


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_review_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cockpit = apply_governance_display_to_cockpit(load_decision_cockpit(root), root)
    snap = _wrap_snapshot_envelope(cockpit)
    executed = str((cockpit.get("controller_state") or {}).get("current_executed_phase") or "")
    operational = str((cockpit.get("controller_state") or {}).get("execution_status") or "")
    if executed == "COMPLETE_AWAITING_OPERATIONAL_DECISION":
        snap["build_status"] = "MANUAL_READ_ONLY_REVIEW_ONLY"
        snap["v5r_external_acceptance"] = "APPROVED_FOR_MANUAL_READ_ONLY_REVIEW"
        snap["operational_authorization"] = "NONE"
        snap["live_trading_allowed"] = False
        snap["auto_promotion_allowed"] = False
        snap["forward_monitoring_status"] = "NOT_AUTHORIZED"
        snap["shadow_monitoring_status"] = "NOT_AUTHORIZED"
        snap["paper_monitoring_status"] = "NOT_AUTHORIZED"
        snap["blockers"] = list(V5R_NEUTRAL_BLOCKERS)
        snap["banners"] = [
            "READ-ONLY DECISION COCKPIT",
            "NO OPERATIONAL AUTHORIZATION",
            "MANUAL READ-ONLY REVIEW ONLY",
        ]
        return snap
    snap["build_status"] = "V5R_EXTERNAL_ACCEPTANCE_COMPLETE"
    snap["v5r_external_acceptance"] = "APPROVED_FOR_NEXT_PHASE"
    return snap


def build_v5r_neutral_release_cockpit_data() -> Dict[str, Any]:
    """Scope-isolated cockpit payload for V5R release EXE — no champion/challenger disclosure."""
    return {
        "schema_version": 4,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_DECISION_COCKPIT",
        "banners": [
            "READ-ONLY DECISION COCKPIT",
            "NO LIVE TRADING",
            "NO AUTO PROMOTION",
            "NO OPERATIONAL AUTHORIZATION",
        ],
        "executive_overview": {
            "active_champion": "NOT_DISCLOSED_IN_V5R_RELEASE",
            "champion_status": "WITHHELD_PENDING_EXTERNAL_REVIEW",
            "champion_blocked_for_safety": True,
            "expected_champion": "NOT_DISCLOSED_IN_V5R_RELEASE",
            "candidate": "NOT_IN_V5R_RELEASE_SCOPE",
            "control_reference": "NOT_IN_V5R_RELEASE_SCOPE",
            "manifest_status": "NOT_IN_V5R_RELEASE_SCOPE",
            "manifest_blocked_for_safety": True,
            "evidence_stage": "BACKTESTED",
            "evidence_stage_summary": (
                "Current verified stage: BACKTESTED. "
                "V5R external acceptance: PENDING_EXTERNAL_REVIEW."
            ),
            "source_classification": "V5R_RELEASE_REVIEW_ONLY",
            "promotion_eligible_display": "NO",
            "paper_eligible_display": "NO",
            "real_money_eligible_display": "NO",
            "v5r_external_acceptance": "PENDING_EXTERNAL_REVIEW",
        },
        "controller_state": {
            "display": "READ_ONLY_REVIEW",
            "blocked_for_safety": True,
            "block_reasons": ["V5R_EXTERNAL_REVIEW_PENDING"],
            "lifecycle_message": "V5R read-only standalone EXE — awaiting external review.",
            "current_executed_phase": "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR",
            "expected_next_phase": "COMPLETE_AWAITING_OPERATIONAL_DECISION",
            "authorized_phase": "",
            "current_running_phase": None,
            "execution_status": "AWAITING_EXTERNAL_REVIEW",
            "next_phase_authorized": False,
            "next_phase_authorized_display": "NO",
        },
        "safety_automation": {
            "AUTO_RESEARCH": "DISABLED",
            "AUTO_PROMOTE_PAPER": "DISABLED",
            "AUTO_PROMOTE_SIGNAL": "DISABLED",
            "AUTO_EXECUTE_REAL_MONEY": "DISABLED",
            "hooks_status": "DISABLED",
            "hooks_schema_valid": True,
            "system_health": "OK",
            "last_known_good_available": False,
            "controller_status": "AWAITING_EXTERNAL_REVIEW",
            "current_executed_phase": "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR",
            "safety_banner": "V5R READ-ONLY RELEASE — NO OPERATIONAL AUTHORIZATION",
            "safety_warnings": [],
            "automation_blocked_for_safety": True,
            "hooks_blocked_for_safety": False,
        },
        "evidence_ladder": {
            "stages": [
                {"stage": "IDEA", "status": "REACHED", "blocker": None},
                {"stage": "BACKTESTED", "status": "CURRENT", "blocker": None},
                {"stage": "ROBUSTNESS_CHECKED", "status": "NOT_REACHED", "blocker": "V5R_EXTERNAL_REVIEW_PENDING"},
            ],
            "summary": "Current verified stage: BACKTESTED. V5R external acceptance: PENDING_EXTERNAL_REVIEW.",
        },
        "why_not_promoted": {
            "explanatory_reasons": [
                "V5R external review pending.",
                "No operational authorization.",
                "Automatic promotion is disabled.",
                "Real-money execution is disabled.",
            ],
            "current_active_blockers": list(V5R_NEUTRAL_BLOCKERS),
        },
        "cost_stress_robustness": {},
        "monitoring": {
            "forward": {"status": "BLOCKED", "display": "BLOCKED", "evidence_missing": True},
            "shadow": {"status": "UNKNOWN — BLOCKED FOR SAFETY", "display": "UNKNOWN — BLOCKED FOR SAFETY", "evidence_missing": True},
            "paper": {"status": "UNKNOWN — BLOCKED FOR SAFETY", "display": "UNKNOWN — BLOCKED FOR SAFETY", "evidence_missing": True},
            "data_requirements_present": False,
        },
        "experiment_registry": {
            "blocked_for_safety": True,
            "status_message": "NOT_IN_V5R_RELEASE_SCOPE",
            "candidate": "NOT_IN_V5R_RELEASE_SCOPE",
            "control_reference": "NOT_IN_V5R_RELEASE_SCOPE",
        },
        "audit_review_chain": {"chain": [], "reviews": [], "pending_external_branch_options": []},
        "source_health": {
            "critical_sources": {},
            "missing_sources": ["V5R_RELEASE_USES_NEUTRAL_EMBEDDED_SNAPSHOT"],
            "unparseable_sources": [],
            "conflicts": [],
            "fail_closed": True,
            "blocked_for_safety": True,
            "champion_source_policy": [],
        },
        "manifest_validation": {
            "manifest_file_status": "NOT_IN_V5R_RELEASE_SCOPE",
            "validation_pass": False,
            "validation_errors": ["NOT_IN_V5R_RELEASE_SCOPE"],
            "validation_checks": {},
        },
        "gui_read_only": True,
        "operative_ui_actions_allowed": False,
    }


def build_v5r_fail_closed_test_cockpit_data() -> Dict[str, Any]:
    """Invalid/inconsistent evidence payload for fail-closed test-only EXE."""
    data = build_v5r_neutral_release_cockpit_data()
    data["executive_overview"] = dict(data["executive_overview"])
    data["executive_overview"]["active_champion"] = "UNKNOWN"
    data["executive_overview"]["champion_status"] = "CHAMPION STATUS MISSING OR CONFLICTING"
    data["executive_overview"]["champion_blocked_for_safety"] = True
    data["safety_automation"] = dict(data["safety_automation"])
    data["safety_automation"]["safety_banner"] = "SAFETY STATUS UNKNOWN OR CONFLICTING"
    data["source_health"] = {
        "critical_sources": {},
        "missing_sources": ["control/evidence/current_evidence_status.json"],
        "unparseable_sources": [],
        "conflicts": ["ECONOMIC_VALUE_GATE: auto_promotion=True promotion_status=False"],
        "fail_closed": True,
        "blocked_for_safety": True,
        "champion_source_policy": [],
    }
    return data


def _wrap_snapshot_envelope(cockpit: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "mode": "READ_ONLY_REVIEW_SNAPSHOT",
        "build_status": "EXE_BUILD_COMPLETE_PENDING_EXTERNAL_REVIEW",
        "operational_authorization": "NONE",
        "live_trading_allowed": False,
        "auto_promotion_allowed": False,
        "evidence_stage": "BACKTESTED",
        "forward_monitoring_status": "BLOCKED",
        "shadow_monitoring_status": "BLOCKED",
        "paper_monitoring_status": "BLOCKED",
        "blockers": list(BLOCKERS),
        "banners": [
            "READ-ONLY REVIEW SNAPSHOT",
            "NO LIVE TRADING",
            "NO AUTO PROMOTION",
            "NO OPERATIONAL AUTHORIZATION",
        ],
        "cockpit_data": cockpit,
    }


def build_v5r_neutral_release_snapshot(*, provenance: Dict[str, Any] | None = None) -> Dict[str, Any]:
    snap = _wrap_snapshot_envelope(build_v5r_neutral_release_cockpit_data())
    snap["blockers"] = list(V5R_NEUTRAL_BLOCKERS)
    snap["v5r_release_scope"] = "NEUTRAL_READ_ONLY_REVIEW_ONLY"
    snap["release_snapshot_scope"] = RELEASE_SNAPSHOT_SCOPE
    if provenance:
        snap["build_provenance"] = dict(provenance)
        snap["release_snapshot_scope"] = provenance.get("release_snapshot_scope", RELEASE_SNAPSHOT_SCOPE)
    return snap


def build_v5r_fail_closed_test_snapshot() -> Dict[str, Any]:
    snap = _wrap_snapshot_envelope(build_v5r_fail_closed_test_cockpit_data())
    snap["build_status"] = "FAIL_CLOSED_TEST_ONLY_NOT_FOR_RELEASE"
    snap["v5r_release_scope"] = "FAIL_CLOSED_NEGATIVE_TEST_ONLY"
    return snap


def write_v5r_neutral_release_snapshot(root: Path, *, provenance: Dict[str, Any] | None = None) -> Path:
    root = Path(root)
    path = root / BUILD_RELEASE_SNAPSHOT
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_v5r_neutral_release_snapshot(provenance=provenance)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_v5r_fail_closed_test_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / BUILD_FAIL_CLOSED_SNAPSHOT
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_v5r_fail_closed_test_snapshot()
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R submission snapshot — R3 champion, blocked-for-safety displays."""
    root = Path(root)
    cockpit = apply_governance_display_to_cockpit(load_decision_cockpit(root), root)
    snap = _wrap_snapshot_envelope(cockpit)
    overview = cockpit.get("executive_overview") or {}
    auth = cockpit.get("authorization_status") or {}
    snap["g0r_submission_scope"] = "G0R_AUTHORIZATION_AND_CHAMPION_LINEAGE_REMEDIATION_RESUBMISSION"
    snap["build_status"] = "MANUAL_READ_ONLY_REVIEW_ONLY"
    snap["operational_authorization"] = "NONE"
    snap["live_trading_allowed"] = False
    snap["auto_promotion_allowed"] = False
    snap["forward_monitoring_status"] = "NOT_AUTHORIZED"
    snap["shadow_monitoring_status"] = "NOT_AUTHORIZED"
    snap["paper_monitoring_status"] = "NOT_AUTHORIZED"
    snap["authoritative_champion"] = overview.get("expected_champion") or overview.get("active_champion")
    snap["authorization_status_display"] = auth.get("operational_status") or "BLOCKED_FOR_SAFETY"
    snap["g1_execution_authorized"] = False
    snap["review_zip_sha256"] = "PENDING_EXTERNAL_SEAL"
    snap["external_sealed"] = False
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R REMEDIATION — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        | {
            "G1_NOT_AUTHORIZED_UNTIL_G0R_EXTERNAL_SEAL",
            "NO_OPERATIONAL_AUTHORIZATION",
            "CHAMPION_CHANGE_NOT_AUTHORIZED",
        }
    )
    return snap


def build_g0r2_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R2 submission snapshot — evidence completeness remediation."""
    snap = build_g0r_review_snapshot(root)
    snap["g0r2_submission_scope"] = "G0R2_CLEAN_CHECKPOINT_AND_EVIDENCE_COMPLETENESS_REMEDIATION"
    snap["g0r_submission_scope"] = snap.get("g0r_submission_scope")
    overview = (snap.get("cockpit_data") or {}).get("executive_overview") or {}
    snap["authoritative_champion"] = overview.get("active_champion") or overview.get("expected_champion")
    snap["authorized_usage"] = "MANUAL_READ_ONLY_REVIEW_ONLY"
    snap["authorization_status"] = "BLOCKED_FOR_SAFETY"
    snap["g1_authorized"] = False
    snap["g1_execution_started"] = False
    snap["shadow_monitoring_activated"] = False
    snap["paper_monitoring_activated"] = False
    snap["promotion_executed"] = False
    snap["champion_changed"] = False
    snap["real_money_executed"] = False
    snap["review_zip_sha256"] = "PENDING_EXTERNAL_SEAL"
    snap["detached_sidecar_sha256"] = "GENERATED_AFTER_FINAL_ZIP_CREATION"
    snap["external_sealed"] = False
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R2 EVIDENCE COMPLETENESS — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R2_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r2_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R2_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r2_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r3_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R3 submission snapshot — commit-bound package remediation."""
    snap = build_g0r2_review_snapshot(root)
    snap["g0r3_submission_scope"] = "G0R3_FINAL_COMMIT_BOUND_PACKAGE_AND_MANIFEST_REMEDIATION"
    snap["g0r2_submission_scope"] = snap.get("g0r2_submission_scope")
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R3 COMMIT-BOUND PACKAGE — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        - {"G1_NOT_AUTHORIZED_UNTIL_G0R2_EXTERNAL_SEAL"}
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R3_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r3_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R3_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r3_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r4_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R4 submission snapshot — exact-byte detached attestation."""
    snap = build_g0r3_review_snapshot(root)
    snap["g0r4_submission_scope"] = "G0R4_DETACHED_ATTESTATION_AND_EXACT_BYTE_PACKAGE_BINDING_REMEDIATION"
    snap["review_zip_sha256"] = "DETACHED_ATTESTATION_ONLY"
    snap["detached_sidecar_sha256"] = "DETACHED_ATTESTATION_ONLY"
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R4 EXACT-BYTE PACKAGE — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        - {"G1_NOT_AUTHORIZED_UNTIL_G0R3_EXTERNAL_SEAL"}
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R4_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r4_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R4_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r4_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r4r_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R4R submission snapshot — verbatim external review chain."""
    snap = build_g0r4_review_snapshot(root)
    snap["g0r4r_submission_scope"] = "G0R4R_VERBATIM_EXTERNAL_REVIEW_CHAIN_RESUBMISSION"
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R4R VERBATIM REVIEW CHAIN — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        - {"G1_NOT_AUTHORIZED_UNTIL_G0R4_EXTERNAL_SEAL"}
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R4R_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r4r_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R4R_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r4r_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r4r2_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R4R2 submission snapshot — verbatim authoritative baseline."""
    snap = build_g0r4r_review_snapshot(root)
    snap["g0r4r2_submission_scope"] = "G0R4R2_VERBATIM_AUTHORITATIVE_BASELINE_RESUBMISSION"
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R4R2 AUTHORITATIVE BASELINE — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        - {"G1_NOT_AUTHORIZED_UNTIL_G0R4R_EXTERNAL_SEAL", "G1_NOT_AUTHORIZED_UNTIL_G0R4R2_EXTERNAL_SEAL"}
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R4R2_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r4r2_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R4R2_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r4r2_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g0r4r3_review_snapshot(root: Path) -> Dict[str, Any]:
    """Fail-closed G0R4R3 submission snapshot — final blob-zip verbatim remediation."""
    snap = build_g0r4r2_review_snapshot(root)
    snap["g0r4r3_submission_scope"] = "G0R4R3_FINAL_BLOB_ZIP_VERBATIM_AND_AUDIT_INPUT_COMPLETENESS_REMEDIATION"
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "NO OPERATIONAL AUTHORIZATION",
        "MANUAL READ-ONLY REVIEW ONLY",
        "G0R4R3 FINAL BLOB-ZIP VERBATIM — AWAITING EXTERNAL REVIEW",
    ]
    snap["blockers"] = sorted(
        set(snap.get("blockers") or [])
        - {
            "G1_NOT_AUTHORIZED_UNTIL_G0R4R_EXTERNAL_SEAL",
            "G1_NOT_AUTHORIZED_UNTIL_G0R4R2_EXTERNAL_SEAL",
            "G1_NOT_AUTHORIZED_UNTIL_G0R4R3_EXTERNAL_SEAL",
        }
        | {"G1_NOT_AUTHORIZED_UNTIL_G0R4R3_EXTERNAL_SEAL"}
    )
    return snap


def write_g0r4r3_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R4R3_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r4r3_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def build_g1_independent_research_snapshot(root: Path) -> Dict[str, Any]:
    """Research-only G1 independent development snapshot (not operational authorization)."""
    root = Path(root)
    snap = build_review_snapshot(root)
    gap_path = root / "evidence" / "g1_independent_next_level" / "comparison" / "evidence_gap_status.json"
    gap_status = "UNKNOWN"
    turnover_verified = False
    if gap_path.is_file():
        try:
            gap_payload = json.loads(gap_path.read_text(encoding="utf-8"))
            gap_status = str(gap_payload.get("CHALLENGER_TURNOVER_NOT_VERIFIED", "UNKNOWN"))
            turnover_verified = gap_status == "CLOSED"
        except Exception:
            pass
    snap["g1_independent_track"] = {
        "authority_basis": "DIRECT_USER_INSTRUCTION_IN_CURRENT_CONVERSATION",
        "research_status": "DEVELOPMENT_EVIDENCE_AVAILABLE" if turnover_verified else "PARTIAL",
        "operational_status": "NOT_AUTHORIZED",
        "live_trading": "NOT_AUTHORIZED",
        "external_sealed": False,
        "challenger_turnover_verified": turnover_verified,
        "target_gap_status": gap_status,
        "evidence_root": "evidence/g1_independent_next_level",
    }
    snap["banners"] = [
        "READ-ONLY DECISION COCKPIT",
        "G1 INDEPENDENT RESEARCH EVIDENCE — NOT OPERATIONAL AUTHORIZATION",
        "RESEARCH EVIDENCE ≠ PROMOTION ≠ LIVE AUTHORIZATION",
    ]
    return snap


def write_g1_independent_research_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G1_INDEPENDENT_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g1_independent_research_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_autonomous_research_snapshot(
    root: Path,
    *,
    gate: Dict[str, Any] | None = None,
    manifests: Dict[str, Any] | None = None,
) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    gate = gate or {}
    snap["autonomous_research"] = {
        "research_autonomy": "ACTIVE",
        "offline_experimentation": "AUTHORIZED",
        "operational_trading": "NOT_AUTHORIZED",
        "real_money": "NOT_AUTHORIZED",
        "evidence_gate_status": gate.get("evidence_status"),
        "challenger_turnover_gap_status": gate.get("challenger_turnover_gap_status"),
        "variants_remediated": sorted((manifests or {}).keys()),
        "evidence_root": "evidence/autonomous_research",
    }
    snap["banners"] = [
        "AUTONOMOUS OFFLINE RESEARCH ACTIVE",
        "NOT OPERATIONAL AUTHORIZATION",
        "RESEARCH EVIDENCE ≠ PROMOTION ≠ LIVE AUTHORIZATION",
    ]
    path = root / AUTONOMOUS_RESEARCH_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p10_research_evidence_snapshot(root: Path, p10_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    identity = p10_result.get("legacy_identity") or {}
    snap["p10_integration"] = {
        "current_integration_phase": "P10_RESEARCH_EVIDENCE_INTEGRATION_AND_STRATEGY_IDENTITY_RESOLUTION",
        "p10_status": p10_result.get("p10_status"),
        "research_autonomy": "ACTIVE",
        "operational_trading": "NOT_AUTHORIZED",
        "active_champion": "R3_w075_q065_noexit",
        "promotion_eligible": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "legacy_mom_63_top12_identity": identity.get("verdict"),
        "mom_63_top12_strict_status": p10_result.get("variant_validation", {}).get("MOM_63_TOP12_STRICT"),
        "mom_63_top15_reconstructed_status": p10_result.get("variant_validation", {}).get("MOM_63_TOP15_RECONSTRUCTED"),
        "return_cost_reconciliation": p10_result.get("return_cost_reconciliation"),
        "next_flowchart_work_unit": "P11_COST_STRESS_AND_STATISTICAL_RESEARCH_VALIDATION",
        "p11_enqueued": p10_result.get("p11_enqueue"),
    }
    snap["banners"] = [
        "P10 RESEARCH EVIDENCE INTEGRATION — READ ONLY",
        "RESEARCH AUTONOMY = ACTIVE",
        "OPERATIONAL TRADING = NOT AUTHORIZED",
    ]
    path = root / P10_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p11_statistical_research_snapshot(root: Path, p11_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    ranking = p11_result.get("research_ranking") or {}
    paper = p11_result.get("paper_practicality") or {}
    snap["p11_validation"] = {
        "current_integration_phase": "P11_COST_STRESS_AND_STATISTICAL_RESEARCH_VALIDATION",
        "p11_status": p11_result.get("p11_status"),
        "research_autonomy": "ACTIVE",
        "operational_trading": "NOT_AUTHORIZED",
        "active_champion": "R3_w075_q065_noexit",
        "promotion_eligible": False,
        "paper_eligible": False,
        "real_money_eligible": False,
        "initial_paper_capital_eur": 500.0,
        "real_money_capital_eur": 0.0,
        "simulation_only": True,
        "cost_stress": p11_result.get("cost_stress_summary"),
        "dsr_overall_status": (p11_result.get("dsr") or {}).get("overall_status"),
        "pbo_status": (p11_result.get("pbo_cscv") or {}).get("status"),
        "robustness_status": (p11_result.get("robustness") or {}).get("overall_status"),
        "paper_practicality": paper,
        "research_ranking": ranking.get("ranking"),
        "next_flowchart_work_unit": "P12A_READ_ONLY_ONLINE_MARKET_DATA_INGESTION",
        "p12a_enqueued": p11_result.get("p12a_enqueue"),
    }
    snap["banners"] = [
        "P11 STATISTICAL RESEARCH VALIDATION — READ ONLY",
        "SIMULATION_ONLY = YES | REAL_MONEY = NO",
        "RESEARCH CANDIDATES ≠ PROMOTION ≠ LIVE AUTHORIZATION",
    ]
    path = root / P11_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p12a_online_market_data_snapshot(root: Path, p12a_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    ing = p12a_result.get("ingestion") or {}
    health = ing.get("health") or {}
    snap["p12a_online_data"] = {
        "current_integration_phase": "P12A_READ_ONLY_ONLINE_MARKET_DATA_INGESTION",
        "p12a_status": p12a_result.get("p12a_status"),
        "active_provider": ing.get("provider"),
        "data_quality_status": ing.get("quality_status"),
        "last_capture_id": ing.get("capture_id"),
        "last_received_at_utc": health.get("last_received_at_utc"),
        "feed_latency_note": health.get("feed_latency_note"),
        "stale_missing_outlier_gate": ing.get("quality_status"),
        "replay_available": health.get("replay_available"),
        "simulation_only": True,
        "real_money": False,
        "broker_order_sent": False,
        "not_live_authorized": True,
        "initial_paper_capital_eur": 500.0,
        "real_money_capital_eur": 0.0,
        "next_flowchart_work_unit": "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE",
        "p12b_enqueued": p12a_result.get("p12b_enqueue"),
    }
    snap["banners"] = [
        "P12A ONLINE DATA INGESTION — READ ONLY",
        "SIMULATION_ONLY = YES | REAL_MONEY = NO | BROKER_ORDER_SENT = NO",
        "DATA INGESTION ≠ TRADING ≠ PROMOTION",
    ]
    path = root / P12A_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p12b_virtual_execution_snapshot(root: Path, p12b_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    cycle = p12b_result.get("engine_cycle") or {}
    metrics = cycle.get("metrics") or {}
    snap["p12b_paper_portfolio"] = {
        "current_integration_phase": "P12B_VIRTUAL_EXECUTION_AND_PAPER_PORTFOLIO_ENGINE",
        "p12b_status": p12b_result.get("p12b_status"),
        "initial_paper_capital_eur": 500.0,
        "real_money_capital_eur": 0.0,
        "portfolio_value_eur": metrics.get("portfolio_value_eur"),
        "cash_eur": metrics.get("cash_eur"),
        "position_count": metrics.get("position_count"),
        "net_pnl_eur": metrics.get("net_pnl_eur"),
        "total_costs_eur": metrics.get("total_costs_eur"),
        "virtual_orders_filled": len((cycle.get("execution") or {}).get("fills") or []),
        "non_executable_orders": len((cycle.get("execution") or {}).get("non_executable") or []),
        "simulation_only": True,
        "real_money": False,
        "broker_order_sent": False,
        "not_live_authorized": True,
        "paper_leverage_enabled": False,
        "paper_shorting_enabled": False,
        "next_flowchart_work_unit": "P12C_PROSPECTIVE_FORWARD_PAPER_TRADING_EVALUATION",
        "p12c_enqueued": p12b_result.get("p12c_enqueue"),
    }
    snap["banners"] = [
        "P12B VIRTUAL PAPER PORTFOLIO — SIMULATION ONLY",
        "INITIAL CAPITAL = 500 EUR | REAL_MONEY = NO",
        "VIRTUAL EXECUTION ≠ BROKER ORDERS ≠ PROMOTION",
    ]
    path = root / P12B_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p12c_forward_paper_snapshot(root: Path, p12c_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    fwd = p12c_result.get("forward_evaluation") or {}
    ev = fwd.get("evaluation") or {}
    scaling = fwd.get("capital_scaling") or {}
    snap["p12c_forward_paper"] = {
        "current_integration_phase": "P12C_PROSPECTIVE_FORWARD_PAPER_TRADING_EVALUATION",
        "p12c_status": p12c_result.get("p12c_status"),
        "paper_trading_status": fwd.get("paper_trading_status"),
        "initial_paper_capital_eur": 500.0,
        "current_portfolio_value_eur": ev.get("current_portfolio_value_eur"),
        "cumulative_net_performance_eur": ev.get("cumulative_net_performance_eur"),
        "max_drawdown_eur": ev.get("max_drawdown_eur"),
        "total_costs_eur": ev.get("total_costs_eur"),
        "virtual_orders_executed": ev.get("virtual_orders_executed"),
        "non_executable_orders": ev.get("non_executable_orders"),
        "vs_cash_benchmark_eur": ev.get("vs_cash_benchmark_eur"),
        "data_quality_status": ev.get("data_quality_status"),
        "paper_capital_tier_eur": scaling.get("current_tier_eur"),
        "simulation_only": True,
        "real_money": False,
        "broker_order_sent": False,
        "lookahead_verified": fwd.get("lookahead_verified"),
        "next_flowchart_work_unit": "P13_CAPITAL_SCALING_READINESS_AND_DISABLED_BROKER_ADAPTER",
        "p13_enqueued": p12c_result.get("p13_enqueue"),
    }
    snap["banners"] = [
        "P12C FORWARD PAPER EVALUATION — SIMULATION ONLY",
        "500 EUR VIRTUAL CAPITAL | REAL_MONEY = NO",
        "FORWARD PERFORMANCE ≠ LIVE AUTHORIZATION",
    ]
    path = root / P12C_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p13_broker_readiness_snapshot(root: Path, p13_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    rd = p13_result.get("readiness") or {}
    scaling = rd.get("capital_scaling") or {}
    adapter = rd.get("adapter_status") or {}
    snap["p13_broker_readiness"] = {
        "current_integration_phase": "P13_CAPITAL_SCALING_READINESS_AND_DISABLED_BROKER_ADAPTER",
        "p13_status": p13_result.get("p13_status"),
        "broker_adapter_implemented": adapter.get("broker_adapter_implemented"),
        "broker_adapter_enabled": adapter.get("broker_adapter_enabled"),
        "real_order_routing_enabled": adapter.get("real_order_routing_enabled"),
        "real_money_enabled": adapter.get("real_money_enabled"),
        "kill_switch_active": (rd.get("kill_switch") or {}).get("active"),
        "credential_isolation_ok": (rd.get("credential_isolation") or {}).get("isolated_by_default"),
        "paper_capital_ladder_eur": scaling.get("paper_capital_ladder_eur"),
        "current_tier_eur": scaling.get("current_tier_eur"),
        "real_capital_scale_up": scaling.get("real_capital_scale_up"),
        "simulation_only": True,
        "real_money": False,
        "not_live_authorized": True,
        "pipeline_spine_p11_p13_complete": p13_result.get("p13_status", "").startswith("PASS"),
        "trading212": (p13_result.get("readiness") or {}).get("trading212_connection"),
    }
    snap["banners"] = [
        "P13 BROKER READINESS — ADAPTER DISABLED BY DEFAULT",
        "REAL_MONEY = NO | REAL_ORDER_ROUTING = NO",
        "CAPITAL SCALE-UP REQUIRES EXPLICIT USER DECISION",
    ]
    path = root / P13_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p14_paper_forward_snapshot(root: Path, p14_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    fwd = p14_result.get("forward") or {}
    frac = fwd.get("model_a_fractional") or {}
    pred = p14_result.get("predecessor_verification") or {}
    snap["p14_paper_forward"] = {
        "current_integration_phase": "P14_PAPER_FORWARD_500_EUR_WITH_TRADING212_DEMO_READONLY_OBSERVATION",
        "p14_status": p14_result.get("p14_status"),
        "p10_p13_verification": pred.get("all_predecessors_verified"),
        "initial_paper_capital_eur": 500.0,
        "reference_source": "USER_PROVIDED_SCREENSHOT_REFERENCE",
        "screenshot_verified_as_broker_ledger": False,
        "mapped_instruments": fwd.get("mapped_instruments"),
        "portfolio_value_eur": frac.get("portfolio_value_eur"),
        "virtual_cash_eur": frac.get("cash_eur"),
        "invested_eur": frac.get("invested_eur"),
        "net_pnl_eur": frac.get("net_pnl_eur"),
        "simulated_costs_eur": frac.get("total_costs_eur"),
        "trading212_sync_status": (fwd.get("trading212_sync") or {}).get("status"),
        "runtime_status": fwd.get("runtime_status"),
        "simulation_only": True,
        "real_money": False,
        "broker_order_routing": "DISABLED",
        "active_champion": "R3_w075_q065_noexit",
        "next_flowchart_work_unit": "P15_PAPER_PERFORMANCE_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT",
        "p15_enqueued": p14_result.get("p15_enqueue"),
    }
    snap["banners"] = [
        "P14 PAPER FORWARD — SIMULATION ONLY",
        "500 EUR USER REFERENCE ALLOCATION | REAL_MONEY = NO",
        "TRADING212 = DEMO READ-ONLY ONLY",
    ]
    path = root / P14_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p15_paper_runtime_snapshot(root: Path, p15_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p15_result.get("runtime") or {}
    frac = runtime.get("model_a_fractional") or {}
    mapping = runtime.get("instrument_mapping") or {}
    p14_adj = runtime.get("p14_adjudication") or {}
    t212 = runtime.get("trading212_sync") or {}
    scaling = runtime.get("virtual_scaling") or {}
    snap["p14_adjudication"] = {
        "initialization_simulation": p14_adj.get("p14_initialization_simulation", "COMPLETED"),
        "validated_forward_runtime": p14_adj.get("p14_validated_forward_observation_runtime", "NOT_YET_PROVEN"),
        "acceptance_classification": p14_adj.get("p14_acceptance_classification"),
        "static_price_classified_initialization_only": p14_adj.get("p14_static_price_usage_classified"),
    }
    snap["p15_paper_runtime"] = {
        "current_integration_phase": "P15_PAPER_RUNTIME_VALIDATION_AND_VIRTUAL_CAPITAL_SCALING_DECISION_SUPPORT",
        "p15_status": p15_result.get("p15_status"),
        "initial_paper_capital_eur": 500.0,
        "data_mode": runtime.get("data_mode"),
        "market_data_runtime_status": runtime.get("market_data_runtime_status"),
        "paper_observation_status": runtime.get("paper_observation_status"),
        "observation_count": runtime.get("observation_count"),
        "performance_assessment_status": runtime.get("performance_assessment_status"),
        "virtual_portfolio_value_eur": frac.get("portfolio_value_eur"),
        "virtual_cash_eur": frac.get("cash_eur"),
        "net_pnl_eur": frac.get("net_pnl_eur"),
        "net_pnl_pct": frac.get("net_pnl_pct"),
        "total_simulated_costs_eur": frac.get("total_costs_eur"),
        "maximum_drawdown": frac.get("maximum_drawdown"),
        "turnover": frac.get("turnover"),
        "fractional_model_status": "SIMULATED",
        "whole_unit_model_status": "SIMULATED",
        "static_mapping_candidates": mapping.get("static_mapping_candidates"),
        "provider_verified_instrument_mappings": mapping.get("provider_verified_instrument_mappings"),
        "scaling_engine_implemented": scaling.get("scaling_engine_implemented"),
        "scaling_decision_permitted_by_observation_gate": scaling.get("scaling_decision_permitted_by_observation_gate"),
        "virtual_tiers_evaluated": scaling.get("virtual_tiers_evaluated"),
        "trading212_environment": "DEMO_ONLY",
        "trading212_credentials_configured": t212.get("connected", False),
        "trading212_demo_read_only_sync_active": t212.get("status") == "DEMO_READ_ONLY_SYNC_ACTIVE",
        "trading212_live_host_blocked": True,
        "trading212_write_methods_blocked": True,
        "trading212_order_endpoints_blocked": True,
        "simulation_only": True,
        "real_money": False,
        "real_money_capital_eur": 0.0,
        "broker_order_routing": "DISABLED",
        "live_trading": "NOT_AUTHORIZED",
        "automatic_promotion": "DISABLED",
        "active_champion": "R3_w075_q065_noexit",
        "next_flowchart_work_unit": "P16_VIRTUAL_SCALING_EVALUATION_AND_REAL_MONEY_DECISION_DOSSIER",
        "p16_enqueued": p15_result.get("p16_enqueue"),
        "test_evidence": p15_result.get("tests"),
    }
    snap["banners"] = [
        "P15 PAPER RUNTIME — SIMULATION ONLY",
        "500 EUR VIRTUAL REFERENCE | REAL_MONEY = NO",
        "TRADING212 = DEMO READ-ONLY ONLY | NO ORDERS",
    ]
    path = root / P15_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16_forward_observation_snapshot(root: Path, p16_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16_result.get("runtime") or {}
    paper = runtime.get("paper_observation") or {}
    scaling = runtime.get("virtual_scaling") or {}
    t212 = runtime.get("trading212_sync") or {}
    snap["p16_forward_observation_scaling"] = {
        "current_integration_phase": "P16_READ_ONLY_FORWARD_OBSERVATION_AND_VIRTUAL_SCALING_EVIDENCE",
        "p16_scope_classification": runtime.get("p16_scope_classification"),
        "p15_status": runtime.get("p15_status_inherited"),
        "p16_implementation_status": p16_result.get("p16_status"),
        "p16_forward_observation_status": runtime.get("p16_forward_observation_status"),
        "p16_scaling_evidence_status": runtime.get("p16_scaling_evidence_status"),
        "p16_real_money_dossier_status": runtime.get("p16_real_money_dossier_status"),
        "data_mode": runtime.get("data_mode"),
        "forward_feed_validated": runtime.get("forward_feed_validated"),
        "observation_start_utc": runtime.get("observation_start_utc"),
        "valid_observation_count": runtime.get("valid_observation_count"),
        "data_quality_gate": runtime.get("data_quality_gate"),
        "initial_paper_capital_eur": 500.0,
        "virtual_portfolio_value_eur": paper.get("portfolio_value_eur"),
        "virtual_cash_eur": paper.get("cash_eur"),
        "net_pnl_eur": paper.get("net_pnl_eur"),
        "net_pnl_pct": paper.get("net_pnl_pct"),
        "simulated_costs_eur": paper.get("simulated_costs_eur"),
        "maximum_drawdown": paper.get("maximum_drawdown"),
        "turnover": paper.get("turnover"),
        "virtual_orders": paper.get("virtual_orders"),
        "virtual_fills": paper.get("virtual_fills"),
        "non_executable_orders": paper.get("non_executable_orders"),
        "performance_evidence_class": runtime.get("performance_evidence_class"),
        "primary_provider": (runtime.get("primary_market_data") or {}).get("provider"),
        "primary_mappings_verified": (runtime.get("primary_market_data") or {}).get("instrument_mappings_verified"),
        "t212_provider_verified_mappings": runtime.get("t212_provider_verified_mappings"),
        "trading212_environment": "DEMO_ONLY",
        "trading212_credentials_configured": t212.get("connected", False),
        "trading212_demo_sync_active": t212.get("status") == "DEMO_READ_ONLY_SYNC_ACTIVE",
        "trading212_live_host_blocked": True,
        "trading212_redirect_guard_hardened": True,
        "trading212_query_policy_hardened": True,
        "scaling_engine_implemented": scaling.get("scaling_engine_implemented"),
        "scaling_evidence_class": runtime.get("p16_scaling_evidence_status"),
        "virtual_tiers_evaluated": scaling.get("virtual_tiers_evaluated"),
        "real_money_dossier_readiness": runtime.get("p16_real_money_dossier_status"),
        "simulation_only": True,
        "real_money": False,
        "broker_order_routing": "DISABLED",
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16_result.get("next_work_unit"),
        "test_evidence": p16_result.get("tests"),
    }
    snap["banners"] = [
        "P16 FORWARD OBSERVATION — SIMULATION ONLY",
        "REAL_MONEY DOSSIER NOT DECISION READY",
        "TRADING212 DEMO READ-ONLY | NO ORDERS",
    ]
    path = root / P16_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16b_continuous_forward_snapshot(root: Path, p16b_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16b_result.get("runtime") or {}
    win = runtime.get("observation_window") or {}
    primary = runtime.get("primary_mapping") or {}
    mtm = runtime.get("mark_to_market") or {}
    snap["p16b_continuous_forward"] = {
        "p16_conditional_status": runtime.get("p16_conditional_classification"),
        "p16b_status": p16b_result.get("p16b_status"),
        "p16b_runtime_status": runtime.get("p16b_runtime_status"),
        "observation_start_utc": win.get("observation_start_utc"),
        "observation_batches": win.get("observation_batches"),
        "independent_portfolio_marks": win.get("independent_portfolio_marks"),
        "valid_instrument_observations": win.get("valid_instrument_observations"),
        "elapsed_observation_hours": win.get("elapsed_observation_hours"),
        "data_quality_gate": (runtime.get("forward_batch") or {}).get("data_quality_gate"),
        "fx_quality_gate": (runtime.get("forward_batch") or {}).get("fx_quality_gate"),
        "initial_allocation_executed_once": runtime.get("initial_allocation_executed_once"),
        "portfolio_value_eur": mtm.get("portfolio_value_eur"),
        "cash_eur": mtm.get("cash_eur"),
        "initial_execution_cost_impact_eur": runtime.get("initial_execution_cost_impact_eur"),
        "subsequent_market_pnl_eur": runtime.get("subsequent_market_pnl_eur"),
        "total_net_pnl_eur": runtime.get("total_net_pnl_eur"),
        "primary_static_mapping_count": primary.get("primary_static_ticker_mapping_count"),
        "primary_quote_retrieval_count": primary.get("primary_quote_retrieval_success_count"),
        "scaling_evidence_status": win.get("scaling_evidence_status"),
        "simulation_only": True,
        "real_money": False,
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16b_result.get("next_work_unit"),
    }
    snap["banners"] = ["P16B CONTINUOUS FORWARD — SIMULATION ONLY", "REAL_MONEY DOSSIER NOT READY"]
    path = root / P16B_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16c_forward_runtime_correction_snapshot(root: Path, p16c_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16c_result.get("runtime") or {}
    win = runtime.get("observation_window") or {}
    state = runtime.get("portfolio_state") or {}
    identity = runtime.get("instrument_identity") or {}
    primary = identity.get("primary") or {}
    snap["p16c_forward_runtime_correction"] = {
        "p16b_conditional_status": runtime.get("p16b_conditional_classification"),
        "p16c_status": p16c_result.get("p16c_status"),
        "fx_runtime_gate": runtime.get("fx_runtime_gate"),
        "currency_reconciliation": runtime.get("currency_reconciliation"),
        "validated_observation_epoch_start_utc": win.get("validated_observation_epoch_start_utc"),
        "validated_observation_batches": win.get("validated_observation_batches"),
        "independent_portfolio_marks": win.get("independent_portfolio_marks"),
        "observation_window_status": win.get("status"),
        "initial_allocation_executed_once": state.get("initial_allocation_executed"),
        "initial_execution_cost_eur": state.get("initial_execution_cost_eur"),
        "subsequent_market_price_pnl_eur": state.get("subsequent_market_price_pnl_eur"),
        "portfolio_value_eur": state.get("last_mark_value_eur"),
        "primary_identity_bound_count": primary.get("primary_provider_identity_bound_count"),
        "performance_evidence_classification": runtime.get("performance_evidence_classification"),
        "scaling_gate_status": win.get("scaling_gate_status"),
        "simulation_only": True,
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16c_result.get("next_work_unit"),
    }
    snap["banners"] = ["P16C RUNTIME CORRECTION — SIMULATION ONLY", "REAL_MONEY DOSSIER NOT READY"]
    path = root / P16C_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16d_validated_forward_runtime_snapshot(root: Path, p16d_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16d_result.get("runtime") or {}
    win = runtime.get("observation_window") or {}
    state = runtime.get("portfolio_state") or {}
    pid = runtime.get("portfolio_identity") or {}
    identity = runtime.get("instrument_identity") or {}
    primary = identity.get("primary") or {}
    t212 = runtime.get("trading212") or {}
    snap["p16d_validated_forward_runtime"] = {
        "p16c_conditional_status": runtime.get("p16c_conditional_classification"),
        "p16d_status": p16d_result.get("p16d_status"),
        "multi_currency_runtime_gate": runtime.get("multi_currency_runtime_gate"),
        "validated_performance_window_start_utc": win.get("validated_performance_window_start_utc"),
        "baseline_batches": win.get("p16c_baseline_batch_count", 1),
        "post_baseline_validated_batches": win.get("post_baseline_validated_batches"),
        "independent_post_baseline_portfolio_marks": win.get("independent_post_baseline_portfolio_marks"),
        "observation_window_status": win.get("status"),
        "reference_portfolio_positions": pid.get("reference_positions", 8),
        "executable_portfolio_positions": pid.get("executable_positions", 6),
        "full_reference_claimed_as_executed": pid.get("full_reference_claimed_as_executed", False),
        "performance_evidence_classification": runtime.get("performance_evidence_classification"),
        "portfolio_value_eur": state.get("last_mark_value_eur"),
        "subsequent_market_price_pnl_eur": state.get("subsequent_market_price_pnl_eur"),
        "scaling_gate_status": win.get("scaling_gate_status"),
        "trading212_sync_status": t212.get("sync_status"),
        "simulation_only": True,
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16d_result.get("next_work_unit"),
    }
    snap["banners"] = ["P16D RUNTIME HARDENING — SIMULATION ONLY", "REAL_MONEY DOSSIER NOT READY"]
    path = root / P16D_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16e_fast_track_manual_live_readiness_snapshot(root: Path, p16e_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16e_result.get("runtime") or {}
    pnl = runtime.get("pnl_reconciliation") or {}
    tickets = runtime.get("manual_tickets") or {}
    t212 = runtime.get("trading212") or {}
    snap["p16e_fast_track_manual_live_readiness"] = {
        "p16d_conditional_status": runtime.get("p16d_conditional_classification"),
        "p16e_status": p16e_result.get("p16e_status"),
        "pnl_reconciliation_gate": pnl.get("pnl_reconciliation_gate"),
        "max_real_capital_eur": 500.0,
        "manual_execution_only": True,
        "automated_real_order_routing": "DISABLED",
        "ready_manual_tickets": tickets.get("ready_for_user_manual_review", 0),
        "real_capital_deployed_by_cursor_eur": 0.0,
        "trading212_live_readonly_status": t212.get("live_read_only_observation_status"),
        "credentials_configured": t212.get("credentials_configured", False),
        "order_endpoints_blocked": True,
        "simulation_only": False,
        "real_money_pilot_status": runtime.get("real_money_pilot_status"),
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16e_result.get("next_work_unit"),
    }
    snap["banners"] = [
        "P16E MANUAL LIVE PILOT — USER MUST EXECUTE ORDERS IN BROKER APP",
        "AUTOMATED REAL ORDER ROUTING = DISABLED",
        "BROKER ORDER SUBMISSION BY CURSOR = FORBIDDEN",
    ]
    path = root / P16E_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_p16f_manual_ticket_risk_remediation_snapshot(root: Path, p16f_result: Dict[str, Any]) -> Path:
    root = Path(root)
    snap = build_review_snapshot(root)
    runtime = p16f_result.get("runtime") or {}
    safety = runtime.get("safety_semantics") or {}
    cash = runtime.get("real_cash_state") or {}
    tickets = runtime.get("manual_tickets") or {}
    t212 = runtime.get("trading212") or {}
    snap["p16f_manual_ticket_risk_remediation"] = {
        "p16e_conditional_status": runtime.get("p16e_conditional_classification"),
        "p16f_status": p16f_result.get("p16f_status"),
        "p16e_tickets_superseded": safety.get("p16e_tickets_superseded", 0),
        "p16e_ticket_execution_allowed": False,
        "max_real_capital_eur": 500.0,
        "minimum_cash_reserve_eur": 50.0,
        "readonly_broker_cash_verified": cash.get("readonly_broker_cash_verified", False),
        "available_ticket_budget_eur": cash.get("available_real_manual_ticket_budget_eur", 0),
        "ready_manual_tickets": tickets.get("ready_for_user_manual_review", 0),
        "draft_tickets": tickets.get("draft_tickets", 0),
        "simulation_only": safety.get("simulation_only", True),
        "automated_real_order_routing": "DISABLED",
        "real_capital_deployed_by_cursor_eur": 0.0,
        "active_champion": "R3_w075_q065_noexit",
        "next_work_unit": p16f_result.get("next_work_unit"),
    }
    snap["banners"] = [
        "P16F MANUAL TICKETS — USER MUST EXECUTE IN BROKER APP",
        "P16E TICKETS SUPERSEDED DO NOT EXECUTE",
        "BROKER ORDER SUBMISSION BY CURSOR = FORBIDDEN",
    ]
    path = root / P16F_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")
    return path


def write_g0r_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / G0R_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_g0r_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def write_review_snapshot(root: Path) -> Path:
    root = Path(root)
    path = root / SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    data = build_review_snapshot(root)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def _meipass_snapshot() -> Optional[Path]:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    for name in (EMBEDDED_RELEASE_NAME, EMBEDDED_FAIL_CLOSED_NAME, EMBEDDED_NAME):
        candidate = Path(base) / name
        if candidate.is_file():
            return candidate
    return None


def load_review_snapshot(root: Path) -> Dict[str, Any]:
    root = Path(root)
    if live_cockpit_requested():
        return load_live_review_snapshot(root)

    embedded = _meipass_snapshot()
    if embedded is not None:
        return json.loads(embedded.read_text(encoding="utf-8"))

    path = root / SNAPSHOT_REL
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "mode": "READ_ONLY_REVIEW_SNAPSHOT",
        "build_status": "UNKNOWN",
        "cockpit_data": None,
        "missing_snapshot": True,
    }


def cockpit_data_from_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    if snapshot.get("missing_snapshot") or snapshot.get("cockpit_data") is None:
        return {
            "banners": ["UNKNOWN — BLOCKED FOR SAFETY"],
            "executive_overview": {
                "active_champion": "UNKNOWN",
                "evidence_stage": "UNKNOWN",
                "champion_blocked_for_safety": True,
            },
            "controller_state": {
                "blocked_for_safety": True,
                "lifecycle_message": "UNKNOWN — BLOCKED FOR SAFETY",
            },
            "safety_automation": {"hooks_status": "UNKNOWN"},
            "monitoring": {},
            "why_not_promoted": {"explanatory_reasons": [], "active_blockers": BLOCKERS},
        }
    data = dict(snapshot["cockpit_data"])
    extra_banners = list(snapshot.get("banners") or [])
    existing = list(data.get("banners") or [])
    data["banners"] = extra_banners + [b for b in existing if b not in extra_banners]
    return data
