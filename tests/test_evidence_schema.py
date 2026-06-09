"""Tests for aa_evidence_schema."""
from __future__ import annotations

from aa_evidence_schema import (
    EVIDENCE_STAGES,
    SOURCE_CLASSIFICATIONS,
    compute_evidence_stage,
    validate_evidence_stage,
    validate_source_classification,
)


def test_valid_evidence_stages_accepted():
    for stage in EVIDENCE_STAGES:
        assert validate_evidence_stage(stage)


def test_unknown_stage_rejected():
    assert not validate_evidence_stage("NOT_A_STAGE")


def test_valid_source_classifications_accepted():
    for cls in SOURCE_CLASSIFICATIONS:
        assert validate_source_classification(cls)


def test_unknown_source_classification_rejected():
    assert not validate_source_classification("MYSTERY")


def test_backtested_never_eligible():
    r = compute_evidence_stage(
        proposed_stage="BACKTESTED",
        p9_unreviewed=False,
        cost_stress_pass=True,
        economic_value_pass=True,
        risk_gate_pass=True,
        data_quality_pass=True,
    )
    assert r["promotion_eligible"] is False
    assert r["paper_eligible"] is False
    assert r["real_money_eligible"] is False


def test_cost_stress_null_caps_backtested():
    r = compute_evidence_stage(proposed_stage="ROBUSTNESS_CHECKED", cost_stress_pass=None)
    assert r["current_evidence_stage"] == "BACKTESTED"


def test_p9_unreviewed_blocks_shadow_stages():
    r = compute_evidence_stage(
        proposed_stage="PAPER_CANDIDATE",
        p9_unreviewed=True,
        cost_stress_pass=True,
        economic_value_pass=True,
        risk_gate_pass=True,
        data_quality_pass=True,
    )
    assert r["current_evidence_stage"] == "BACKTESTED"
    assert "P9_NOT_EXTERNALLY_REVIEWED" in r["blockers"]


def test_missing_data_quality_blocks_later_stages():
    r = compute_evidence_stage(
        proposed_stage="SHADOW_RUNNING",
        data_quality_evidence_missing=True,
        cost_stress_pass=True,
        economic_value_pass=True,
        risk_gate_pass=True,
        p9_unreviewed=False,
    )
    assert r["current_evidence_stage"] == "BACKTESTED"


def test_conflicting_sources_do_not_elevate():
    r = compute_evidence_stage(
        proposed_stage="PAPER_CANDIDATE",
        cost_stress_pass=True,
        economic_value_pass=True,
        risk_gate_pass=True,
        data_quality_pass=True,
        p9_unreviewed=False,
        source_conflicts=["gate mismatch"],
    )
    assert r["current_evidence_stage"] != "PAPER_CANDIDATE"
