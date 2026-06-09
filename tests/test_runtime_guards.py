"""Tests for aa_runtime_guards loophole closures."""
from __future__ import annotations

import os

import pytest


def test_multi_instance_bypass_blocked_without_test_flag(monkeypatch: pytest.MonkeyPatch):
    from aa_runtime_guards import AUTOMATED_TEST_FLAGS, multi_instance_bypass_allowed

    for name in AUTOMATED_TEST_FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    assert multi_instance_bypass_allowed() is False


def test_multi_instance_bypass_allowed_in_matrix(monkeypatch: pytest.MonkeyPatch):
    from aa_runtime_guards import multi_instance_bypass_allowed

    monkeypatch.setenv("AA_INTERACTIVE_COCKPIT_FULL_FUNCTION_TEST", "1")
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    assert multi_instance_bypass_allowed() is True


def test_record_subsystem_error_dedupes():
    from aa_runtime_guards import record_subsystem_error

    state: dict = {}
    record_subsystem_error(state, code="X", message="boom", subsystem="t")
    record_subsystem_error(state, code="X", message="boom", subsystem="t")
    assert len(state["subsystem_errors"]) == 1


def test_acquire_single_instance_ignores_allow_multi_in_production(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from aa_runtime_guards import AUTOMATED_TEST_FLAGS
    from aa_single_instance import acquire_single_instance

    for name in AUTOMATED_TEST_FLAGS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AA_SINGLE_INSTANCE", "1")
    monkeypatch.setenv("AA_SINGLE_INSTANCE_MUTEX", "0")
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    guard = acquire_single_instance(tmp_path.resolve())
    assert guard is not None
    lock = tmp_path / ".marktanalyse_app.lock"
    assert lock.is_file()
    guard.release()


def test_failure_state_surfaces_learning_error():
    from ui.interactive_cockpit.services.failure_state_service import classify_system_state

    fs = classify_system_state(
        {
            "broker": {"status": "NOT_CONFIGURED"},
            "learning_readiness": {"learning_collection_active": True, "error": "EOD failed", "capture_errors": ["EOD failed"]},
        }
    )
    codes = {i["code"] for i in fs["issues"]}
    assert "LEARNING_CAPTURE_ERROR" in codes
