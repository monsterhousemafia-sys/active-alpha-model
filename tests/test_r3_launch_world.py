"""R3 Weltneuheit Launch."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_launch_world import (
    enrich_launch_world,
    render_world_launch_page,
    render_world_launch_section,
    world_launch_kernel_gate,
)


def test_enrich_launch_world(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_launch_world.json").write_text(
        json.dumps({"world_novelty_de": "Weltneuheit", "milestone_labels": {"h1": "Validierung"}}),
        encoding="utf-8",
    )
    doc = enrich_launch_world(
        {"milestones": [{"id": "h1", "label_de": "old", "done": False}], "phase": "h1_running", "h1": {"progress_pct": 50}},
        tmp_path,
    )
    assert doc["milestones"][0]["label_de"] == "Validierung"
    assert doc.get("world_headline_de")
    assert doc["world"]["novelty_de"] == "Weltneuheit"


def test_render_world_launch_section(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: True,
    )
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_launch_world.json").write_text(
        json.dumps(
            {
                "world_novelty_de": "Weltneuheit",
                "title_de": "R3 Test",
                "pillars": [{"icon": "◆", "title_de": "Ein Kern", "body_de": "Test"}],
            }
        ),
        encoding="utf-8",
    )
    html = render_world_launch_section(
        enrich_launch_world({"overall_pct": 42, "milestones": [], "tiles": [], "h1": {}}, tmp_path),
        tmp_path,
    )
    assert "Weltneuheit" in html
    assert "wl-hero" in html
    assert "wl-pillar" in html
    assert "wl-reveal" not in html
    assert "Willkommen bei R3" not in html


def test_render_world_launch_page(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: True,
    )
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_surface_identity.json").write_text(
        json.dumps({"product": "R3", "nav": []}),
        encoding="utf-8",
    )
    (tmp_path / "control/r3_launch_world.json").write_text(
        json.dumps({"world_novelty_de": "Weltneuheit", "title_de": "R3"}),
        encoding="utf-8",
    )
    body = render_world_launch_page(
        enrich_launch_world({"overall_pct": 10, "milestones": [], "tiles": [], "h1": {}}, tmp_path),
        tmp_path,
    ).decode("utf-8")
    assert "Weltneuheit" in body
    assert "Linux" not in body


def test_world_launch_blocked_without_kernel(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/r3_launch_world.json").write_text(
        json.dumps({"world_novelty_de": "Weltneuheit", "title_de": "R3"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.linux_runtime_unified.kernel_is_authoritative",
        lambda _root: False,
    )
    gate = world_launch_kernel_gate(tmp_path)
    assert gate.get("allowed") is False
    html = render_world_launch_section(
        enrich_launch_world({"overall_pct": 10, "milestones": [], "tiles": [], "h1": {}}, tmp_path),
        tmp_path,
    )
    assert "gesperrt" in html
    assert "wl-gate" in html
    assert "wl-hero" not in html
