"""Schritt A Fortschritt."""
from __future__ import annotations

from pathlib import Path

from analytics.r3_step_a import evaluate_step_a, render_step_a_progress


def test_evaluate_step_a_project() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = evaluate_step_a(root)
    assert doc.get("phase") == "A"
    assert len(doc.get("milestones") or []) == 6
    assert int(doc.get("step_a_code_percent") or 0) >= 80
    if doc.get("step_b_released") and doc.get("step_a_code_complete"):
        assert doc.get("step_a_ready_for_b") is True


def test_render_step_a() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_step_a_progress(root)
    assert "r3-stepa" in html
    assert "Schritt A" in html
