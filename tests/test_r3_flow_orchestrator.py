"""R3 Flow-Orchestrator — Hard/Soft fließt visuell in R3."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_flow_orchestrator import (
    build_r3_flow_status,
    load_flow_policy,
    render_r3_flow_strip,
    sync_r3_flow,
)


def test_flow_policy_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_flow_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"
    assert "R3" in str(policy.get("headline_de") or "")


def test_build_flow_status(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_flow_orchestrator_policy.json").write_text(
        json.dumps({"fluidity_stable_min_pct": 60}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"ok": True, "phase": "ready", "active_layer": "bash", "handoff_to": "python", "beat": 3}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_hardware_latest.json").write_text(
        json.dumps(
            {
                "gpu_returns": {"enabled": True},
                "memory_available_gb": 16.0,
                "nvme_mounted": True,
                "benchmark": {},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05", "profile_used": "daily_alpha_h1"}),
        encoding="utf-8",
    )
    doc = build_r3_flow_status(tmp_path, persist=True)
    assert doc.get("channels_total", 0) == 6
    assert "fluidity_pct" in doc
    assert (tmp_path / "evidence/r3_flow_latest.json").is_file()


def test_render_flow_strip_on_desktop() -> None:
    root = Path(__file__).resolve().parents[1]
    strip = render_r3_flow_strip(root)
    assert 'id="r3-flow"' in strip
    assert "R3" in strip
    assert "r3-flow-node" in strip


def test_desktop_page_has_status_bar_not_flow_strip(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    for name, body in (
        ("r3_flow_orchestrator_policy.json", {"fluidity_stable_min_pct": 50}),
        (
            "prediction_readiness.json",
            {"ok": True, "signal_date": "2026-06-05", "top_picks": [{"ticker": "A", "target_weight": 0.1}]},
        ),
    ):
        (tmp_path / "control" / name).write_text(json.dumps(body), encoding="utf-8")
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_hardware_latest.json").write_text("{}", encoding="utf-8")
    from analytics.preview_hub_page import render_desktop_shell_page

    html_out = render_desktop_shell_page(tmp_path, port=17890).decode("utf-8")
    assert "r3-trading-functions" in html_out or "r3-freigabe-btn" in html_out
    assert "r3-panels-stack" in html_out
    assert "r3-fact-row" in html_out
    assert 'id="r3-central"' not in html_out
    assert 'id="desktop-blockers"' not in html_out


def test_sync_r3_flow_does_not_cascade_t212(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_flow_orchestrator_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"ok": True, "phase": "sync"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_hardware_latest.json").write_text(
        json.dumps({"nvme_mounted": True, "benchmark": {}}),
        encoding="utf-8",
    )
    from unittest.mock import patch

    with patch("analytics.r3_t212_api_bond.sync_r3_t212_api_bond") as mock_t212:
        sync_r3_flow(tmp_path, warm_cache=False, persist=True)
    mock_t212.assert_not_called()


def test_sync_r3_flow_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/r3_flow_orchestrator_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"ok": True, "phase": "sync"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_hardware_latest.json").write_text(
        json.dumps({"nvme_mounted": True, "benchmark": {}}),
        encoding="utf-8",
    )
    doc = sync_r3_flow(tmp_path, warm_cache=False, persist=True)
    assert doc.get("channels")
    assert (tmp_path / "evidence/r3_flow_latest.json").is_file()
