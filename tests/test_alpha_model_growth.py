from __future__ import annotations

from pathlib import Path

from analytics.alpha_model_growth import (
    agent_chamber_label,
    load_growth_config,
    product_name,
    runtime_label,
    wm_class,
)


def test_growth_config_project() -> None:
    root = Path(__file__).resolve().parents[1]
    cfg = load_growth_config(root)
    assert cfg.get("product_name") == "Alpha Model"
    assert cfg.get("variant") == "growth_v1"
    surfaces = cfg.get("surfaces") or {}
    assert "runtime" in surfaces
    assert "agent_chamber" in surfaces
    assert "workshop" not in surfaces


def test_surface_labels() -> None:
    root = Path(__file__).resolve().parents[1]
    assert product_name(root) == "Alpha Model"
    assert runtime_label(root) == "Alpha Model"
    assert "Entfaltungsraum" in agent_chamber_label(root)
    assert wm_class(root, "agent_chamber") == "AlphaModelAgent"
