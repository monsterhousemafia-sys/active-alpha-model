"""Autopilot delegates to finish_push (no duplicate matrix launcher)."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_autopilot_delegates_finish_push(monkeypatch):
    from tools.run_r0_migration_autopilot import run_autopilot

    calls = []

    def _fake_push(_root):
        calls.append("push")
        return {"verdict": "HOLD_LIVE_MATRIX"}

    monkeypatch.setattr(
        "tools.r0_migration_finish_push.run_finish_push",
        _fake_push,
    )
    monkeypatch.setattr(
        "tools.r0_migration_active_scope.sync_program_focus",
        lambda _root: {"execution_focus": "M1_IN_PROGRESS"},
    )
    out = run_autopilot(ROOT)
    assert calls == ["push"]
    assert "FINISH_PUSH" in str(out.get("status", ""))
