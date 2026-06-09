"""König-Bau-Pipeline — Routing, Plan, pytest-Ziele."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.king_bau_pipeline import (
    build_bau_plan,
    load_bau_policy,
    pytest_targets_from_mandate,
    resolve_bau_route,
)


def test_resolve_bau_route_gui(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/king_bau_pipeline.json").write_text(
        json.dumps({"topic_routes": {"gui": "gui-rebuild", "": "r3-bau"}}),
        encoding="utf-8",
    )
    assert resolve_bau_route(tmp_path, "gui") == "gui-rebuild"
    assert resolve_bau_route(tmp_path, "") == "r3-bau"


def test_pytest_targets_fallback(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/king_bau_pipeline.json").write_text(
        json.dumps({"safe_pytest_de": ["tests/test_king_stufe_a.py"]}),
        encoding="utf-8",
    )
    paths = pytest_targets_from_mandate(tmp_path)
    assert "tests/test_king_stufe_a.py" in paths


def test_build_bau_plan(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "control/king_bau_pipeline.json").write_text("{}", encoding="utf-8")
    plan = build_bau_plan(tmp_path, topic="prognose", prep_stufe_a=True)
    assert plan.get("prep_stufe_a") is True
    assert len(plan.get("steps_planned") or []) >= 5


def test_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    pol = load_bau_policy(root)
    assert pol.get("enabled") is True
