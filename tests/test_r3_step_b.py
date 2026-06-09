"""Schritt B Freigabe und H1-Migration parallel."""
from __future__ import annotations

from pathlib import Path

from analytics.r3_step_a import evaluate_step_a
from analytics.r3_step_b import (
    build_phase_b_ollama_prompt,
    evaluate_step_b,
    h1_migration_status,
    is_phase_b_active,
    is_step_b_released,
    render_step_b_progress,
)


def test_step_b_released_operator() -> None:
    root = Path(__file__).resolve().parents[1]
    assert is_step_b_released(root)


def test_step_a_ready_without_h1_seal_when_b_released() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = evaluate_step_a(root)
    if doc.get("step_b_released") and doc.get("step_a_code_complete"):
        assert doc.get("step_a_ready_for_b") is True


def test_h1_migration_parallel_status() -> None:
    root = Path(__file__).resolve().parents[1]
    mig = h1_migration_status(root)
    if is_step_b_released(root):
        assert "parallel" in str(mig.get("note_de") or "").lower() or mig.get("migrates_on_seal")
    assert "h1_status" in mig


def test_evaluate_step_b_active() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = evaluate_step_b(root)
    assert doc.get("phase") == "B"
    if doc.get("released"):
        assert doc.get("h1_migration")
        assert len(doc.get("milestones_de") or []) >= 3


def test_phase_b_active() -> None:
    root = Path(__file__).resolve().parents[1]
    if is_step_b_released(root):
        assert is_phase_b_active(root) is True


def test_render_phase_b_panel() -> None:
    root = Path(__file__).resolve().parents[1]
    html = render_step_b_progress(root)
    assert "r3-stepb" in html
    assert "Phase B" in html


def test_phase_b_ollama_master_prompt() -> None:
    root = Path(__file__).resolve().parents[1]
    if not is_phase_b_active(root):
        return
    prompt = build_phase_b_ollama_prompt(root)
    assert "Phase B" in prompt
    assert "Meilensteine" in prompt or "Meilenstein" in prompt
    assert "Login" in prompt
