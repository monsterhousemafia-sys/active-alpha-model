"""Tests for aa_vision_phase_catalog."""
from __future__ import annotations

from pathlib import Path

from aa_vision_phase_catalog import (
    allowed_next_phases,
    build_default_catalog,
    ensure_phase_catalog,
    get_phase,
    is_transition_allowed,
    sync_phase_catalog,
)


def test_catalog_contains_v1r3_and_v2r():
    catalog = build_default_catalog()
    assert catalog.get("review_chain") == (
        "V1 -> V1R -> V1R2 -> V1R3 -> V2 -> V2R -> V3 -> V4 -> V4R -> V4R2 -> V4R3 -> V5 -> V5R -> COMPLETE_AWAITING_OPERATIONAL_DECISION"
    )
    ids = [p["phase_id"] for p in catalog["phases"]]
    assert "V1R3_AUTHORIZED_COMPLETION_GATE" in ids
    assert "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION" in ids
    assert "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION" in ids


def test_review_chain_v1_v1r_v1r2_v1r3_v2(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
        "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
    )
    assert is_transition_allowed(
        tmp_path,
        "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
        "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
    )
    assert is_transition_allowed(
        tmp_path,
        "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
        "V1R3_AUTHORIZED_COMPLETION_GATE",
    )
    assert is_transition_allowed(
        tmp_path,
        "V1R3_AUTHORIZED_COMPLETION_GATE",
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
    )


def test_v1r2_cannot_go_directly_to_v2(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert not is_transition_allowed(
        tmp_path,
        "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
    )


def test_v2_accepts_only_v1r3_as_predecessor(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V1R3_AUTHORIZED_COMPLETION_GATE",
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V1R2_REVIEW_CHAIN_AND_FAIL_CLOSED_SEALING",
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
    )


def test_v2_next_is_v2r_not_v3(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
        "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
        "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION",
    )


def test_v2r_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V2R_COST_STRESS_AND_STATISTICAL_VALIDITY_REMEDIATION")
    assert phase is not None
    assert phase["phase_key"] == "V2R"
    assert phase["type"] == "REMEDIATION_ONLY"
    assert phase["approval_file"] == "EXTERNAL_REVIEW_APPROVAL_V2R.md"
    assert phase["review_zip"] == "codex_v2r_statistical_validity_review.zip"
    assert phase["operative_jobs_allowed"] is False
    assert phase["promotion_allowed"] is False


def test_v1_to_v1r_not_direct_v2(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
        "V1R_EVIDENCE_AND_CONTROLLER_HARDENING",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V1_EVIDENCE_DATA_CONTRACTS_AND_GATED_CASCADE_FOUNDATION",
        "V2_COST_STRESS_AND_ROBUSTNESS_ENGINE",
    )


def test_v1r3_phase_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V1R3_AUTHORIZED_COMPLETION_GATE")
    assert phase is not None
    assert phase["phase_key"] == "V1R3"
    assert phase["type"] == "REMEDIATION_ONLY"
    assert phase["approval_file"] == "EXTERNAL_REVIEW_APPROVAL_V1R3.md"
    assert phase["review_zip"] == "codex_v1r3_authorized_completion_review.zip"
    assert phase["operative_jobs_allowed"] is False
    assert phase["promotion_allowed"] is False


def test_v3_branching_options(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION")
    assert phase is not None
    opts = phase.get("allowed_next_phases_after_external_review") or []
    assert "V3S_SHADOW_OBSERVATION_ACTIVATION" in opts
    assert "V4_DECISION_COCKPIT_GUI_INTEGRATION" in opts
    assert phase.get("automatic_selection_allowed") is False


def test_v3_branching_via_allowed_next(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    nxt = allowed_next_phases(tmp_path, "V3_CONTROLLED_FORWARD_MONITORING_FOUNDATION")
    assert len(nxt) == 2
    assert "V3S_SHADOW_OBSERVATION_ACTIVATION" in nxt
    assert "V4_DECISION_COCKPIT_GUI_INTEGRATION" in nxt


def test_ensure_phase_catalog_upgrades_to_v3(tmp_path: Path):
    path = ensure_phase_catalog(tmp_path)
    catalog = path.read_text(encoding="utf-8")
    assert "V1R3_AUTHORIZED_COMPLETION_GATE" in catalog
    assert "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION" in catalog


def test_v4_next_is_v4r_not_v5(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V4_DECISION_COCKPIT_GUI_INTEGRATION",
        "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V4_DECISION_COCKPIT_GUI_INTEGRATION",
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
    )


def test_v4r_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION")
    assert phase is not None
    assert phase["phase_key"] == "V4R"
    assert phase["type"] == "REMEDIATION_ONLY"
    assert phase["approval_file"] == "EXTERNAL_REVIEW_APPROVAL_V4R.md"
    assert phase["review_zip"] == "codex_v4r_gui_safety_review.zip"
    assert phase["operative_jobs_allowed"] is False
    assert phase["exe_build_allowed"] is False


def test_v4r_next_is_v5(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
        "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V4R_FAIL_CLOSED_GUI_AND_REVIEW_EVIDENCE_REMEDIATION",
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
    )


def test_v4r2_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE")
    assert phase is not None
    assert phase["phase_key"] == "V4R2"
    assert phase["review_zip"] == "codex_v4r2_final_gui_gate_review.zip"


def test_v4r2_next_is_v4r3(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
        "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V4R2_FINAL_FAIL_CLOSED_BUILD_GATE",
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
    )


def test_v4r3_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE")
    assert phase is not None
    assert phase["phase_key"] == "V4R3"
    assert phase["review_zip"] == "codex_v4r3_final_build_gate_review.zip"


def test_v4r3_next_is_v5(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V4R3_FINAL_UI_STATE_AND_HOOK_SCHEMA_GATE",
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
    )


def test_v5_next_is_v5r(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    assert is_transition_allowed(
        tmp_path,
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
        "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR",
    )
    assert not is_transition_allowed(
        tmp_path,
        "V5_WINDOWS_EXE_BUILD_AND_VERIFICATION",
        "COMPLETE_AWAITING_OPERATIONAL_DECISION",
    )


def test_v5r_metadata(tmp_path: Path):
    sync_phase_catalog(tmp_path)
    phase = get_phase(tmp_path, "V5R_READ_ONLY_STANDALONE_EXE_REBUILD_AND_AUDIT_REPAIR")
    assert phase is not None
    assert phase["phase_key"] == "V5R"
    assert phase["review_zip"] == "codex_v5r_standalone_exe_review.zip"
    assert phase["exe_build_allowed"] is True
