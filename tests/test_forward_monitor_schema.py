"""Tests for aa_forward_monitor_schema."""
from __future__ import annotations

from aa_forward_monitor_schema import (
    V3_ALLOWED_MONITORING_MODES,
    V3_FORBIDDEN_MONITORING_MODES,
    base_monitoring_fields,
    validate_monitoring_payload,
    validate_v3_activation_status,
)


def test_v3_allowed_modes():
    assert validate_v3_activation_status("BLOCKED")
    assert validate_v3_activation_status("READY_FOR_EXTERNAL_ACTIVATION_REVIEW")
    assert validate_v3_activation_status("INSUFFICIENT_EVIDENCE")
    assert not validate_v3_activation_status("ACTIVE_READ_ONLY_OBSERVATION")


def test_active_read_only_forbidden_in_v3():
    assert "ACTIVE_READ_ONLY_OBSERVATION" in V3_FORBIDDEN_MONITORING_MODES
    assert "ACTIVE_READ_ONLY_OBSERVATION" not in V3_ALLOWED_MONITORING_MODES


def test_base_fields_include_safety():
    payload = base_monitoring_fields(observation_type="FORWARD_MONITORING")
    for field in (
        "activation_externally_approved",
        "operative_jobs_started",
        "promotion_allowed",
        "paper_eligible",
        "real_money_eligible",
        "champion_variant_id",
    ):
        assert field in payload
    assert payload["activation_externally_approved"] is False
    assert payload["operative_jobs_started"] is False
    assert payload["promotion_allowed"] is False
    assert payload["paper_eligible"] is False
    assert payload["real_money_eligible"] is False


def test_validate_blocked_payload_ok():
    payload = base_monitoring_fields(observation_type="SHADOW_OBSERVATION")
    payload["activation_status"] = "BLOCKED"
    ok, errors = validate_monitoring_payload(payload)
    assert ok, errors


def test_validate_forbidden_status_fails():
    payload = base_monitoring_fields(observation_type="SHADOW_OBSERVATION")
    payload["activation_status"] = "ACTIVE_READ_ONLY_OBSERVATION"
    ok, errors = validate_monitoring_payload(payload)
    assert not ok
    assert "forbidden_activation_status_in_v3" in errors
