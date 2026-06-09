"""Erhaltungsprogramm — Bash-Welt-Konsolidierung."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.erhaltungsprogramm import (
    consolidate_bash_weltweit,
    load_erhaltungsprogramm_plan,
    start_erhaltungsprogramm,
)


def test_plan_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    plan = load_erhaltungsprogramm_plan(root)
    assert plan.get("title_de")
    assert "king_ops" in str(plan.get("operator_command_de") or "")


def test_consolidate_layers(tmp_path: Path) -> None:
    src = Path(__file__).resolve().parents[1]
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/ERHALTUNGSPROGRAMM.json").write_text(
        (src / "control/ERHALTUNGSPROGRAMM.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "control/h1_orchestrator_model.json").write_text(
        '{"bash_role_de":"test","orchestrator_de":"König"}',
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "evidence/world_spread_latest.json").write_text(
        json.dumps({"ok": True, "join_url": "https://x.example/join", "tunnel_stable": False}),
        encoding="utf-8",
    )
    doc = consolidate_bash_weltweit(tmp_path, persist=True)
    assert len(doc.get("layers") or []) >= 4
    assert (tmp_path / "evidence/bash_weltweit_consolidation_latest.json").is_file()
    assert "spread_map_de" in doc


def test_start_marks_active(tmp_path: Path, monkeypatch) -> None:
    src = Path(__file__).resolve().parents[1]
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/ERHALTUNGSPROGRAMM.json").write_text(
        (src / "control/ERHALTUNGSPROGRAMM.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(parents=True)
    monkeypatch.setattr(
        "analytics.erhaltungsprogramm._run_bash_step",
        lambda *_a, **_k: {"ok": True, "returncode": 0},
    )
    monkeypatch.setattr(
        "analytics.community_spread_plan.scan_community_spread",
        lambda *_a, **_k: {"ok": True, "gates_ok": 6, "gates_total": 6},
    )
    monkeypatch.setattr(
        "analytics.glasfaser_offline_plan.scan_glasfaser_offline",
        lambda *_a, **_k: {"ok": False, "active_phase_id": "before_offline"},
    )
    monkeypatch.setattr(
        "analytics.series_readiness.scan_series_readiness",
        lambda *_a, **_k: {"series_ready": True, "readiness_pct": 100},
    )
    doc = start_erhaltungsprogramm(tmp_path, repair=True, persist=True)
    state = json.loads((tmp_path / "control/erhaltungsprogramm_state.json").read_text(encoding="utf-8"))
    assert state.get("status") == "ACTIVE"
    assert doc.get("consolidation")
