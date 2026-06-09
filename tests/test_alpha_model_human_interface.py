from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_human_interface import load_human_interface, verify_unfold_parity


def test_human_interface_config() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_human_interface(root)
    assert cfg.get("primary_channel") == "agent_chamber"
    assert cfg.get("entry_points")


def test_verify_returns_checks() -> None:
    root = Path(__file__).resolve().parents[1]
    doc = verify_unfold_parity(root)
    assert doc.get("checks_total", 0) >= 8
    assert "parity_matrix_de" in doc
