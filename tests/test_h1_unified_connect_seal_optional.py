"""H1 unified connect — Seal optional, kein Benchmark-Autostart."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_connect_skips_benchmark_when_seal_optional(monkeypatch, tmp_path: Path) -> None:
    from analytics import h1_unified_connect as mod

    monkeypatch.setattr(
        mod,
        "unified_h1_status",
        lambda r: {
            "h1_backtest": {"status": "COMPLETE"},
            "mom_1_benchmark_lane": {"unified_state": "missing"},
            "sealed": False,
            "generating_live": False,
        },
    )
    monkeypatch.setattr(
        "analytics.h1_seal_policy.is_h1_benchmark_required",
        lambda r: False,
    )
    monkeypatch.setattr(
        "analytics.h1_seal_policy.is_h1_seal_required",
        lambda r: False,
    )
    monkeypatch.setattr(mod, "atomic_write_json", lambda path, doc: None)

    doc = mod.connect_h1_pipeline(tmp_path, auto_execute=True)
    actions = doc.get("actions_taken") or []
    assert any(a.get("id") == "seal_optional_sync" for a in actions)
    assert doc.get("generating_live") is False
    assert "Seal optional" in str(doc.get("next_step_de") or "")


def test_next_step_seal_optional_complete() -> None:
    from analytics.h1_unified_connect import _next_step_de

    step = _next_step_de(
        h1_status="COMPLETE",
        bench_state="missing",
        sealed=False,
        generating_live=False,
        root=ROOT,
    )
    assert "Seal optional" in step
