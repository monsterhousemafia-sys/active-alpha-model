"""M1-only active scope gates."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_assert_m2_blocked_when_m1_not_sealed(monkeypatch):
    from tools.r0_migration_active_scope import assert_m1_sealed_for_phase

    monkeypatch.setattr(
        "tools.r0_migration_phase_guard.is_phase_sealed",
        lambda _root, phase: phase == "M0",
    )
    gate = assert_m1_sealed_for_phase(ROOT, "M2")
    assert gate.get("allowed") is False
    assert gate.get("reason") == "M1_NOT_SEALED"


def test_sync_program_focus_m1_in_progress(monkeypatch, tmp_path):
    from tools.r0_migration_active_scope import sync_program_focus

    monkeypatch.setattr(
        "tools.r0_migration_phase_guard.is_phase_sealed",
        lambda _root, phase: phase == "M0",
    )
    prog = sync_program_focus(tmp_path)
    assert prog.get("execution_focus") == "M1_IN_PROGRESS"
    assert "M2" in (prog.get("blocked_until_m1_sealed") or [])


def test_orchestrator_returns_m1_only_when_unsealed(monkeypatch):
    from tools.run_r0_migration_phase_orchestrator import run_orchestrator

    monkeypatch.setattr(
        "tools.r0_migration_phase_guard.is_phase_sealed",
        lambda _root, phase: phase == "M0",
    )
    out = run_orchestrator(ROOT)
    assert out.get("status") == "M1_ONLY_COMPLETE_M1_FIRST"
    from tools.r0_migration_m1_control import M1_ENTRY

    assert out.get("next_action") == M1_ENTRY
