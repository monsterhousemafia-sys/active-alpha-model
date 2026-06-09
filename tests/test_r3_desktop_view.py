"""R3 Desktop — read-only Status aus Evidence, Hintergrund-Refresh getrennt."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_desktop_view import (
    load_desktop_status,
    render_r3_desktop_status,
    run_r3_background_refresh,
)


def test_load_desktop_status_evidence_only(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/r3_local_first_latest.json").write_text(
        json.dumps({"ok": True, "confirmation_de": "Lokal OK"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True, "confirmation_de": "T212 OK"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/alpha_model_background_engine_latest.json").write_text(
        json.dumps({"ok": True, "confirmation_de": "Engine OK", "r3_display": {"ok": True}}),
        encoding="utf-8",
    )
    doc = load_desktop_status(tmp_path)
    assert doc.get("read_only") is True
    assert doc.get("chips_total") == 3
    assert doc.get("chips_ok") == 3


def test_render_status_bar_no_sync(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/alpha_model_background_engine_latest.json").write_text(
        json.dumps({"ok": True, "confirmation_de": "Active Alpha · Test"}),
        encoding="utf-8",
    )
    with patch("analytics.r3_t212_api_bond.sync_r3_t212_api_bond") as mock_t212, patch(
        "analytics.r3_flow_orchestrator.sync_r3_flow"
    ) as mock_flow, patch(
        "analytics.alpha_model_background_engine.tick_alpha_model_background"
    ) as mock_tick:
        html_out = render_r3_desktop_status(tmp_path)
    mock_t212.assert_not_called()
    mock_flow.assert_not_called()
    mock_tick.assert_not_called()
    assert 'id="r3-status-bar"' in html_out
    assert "Modell" in html_out


def test_background_refresh_runs_steps(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/r3_t212_api_bond_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/r3_flow_orchestrator_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text(
        json.dumps({"ok": True, "phase": "ready"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_hardware_latest.json").write_text(
        json.dumps({"nvme_mounted": True, "benchmark": {}}),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_trading_cycle.run_trading_cycle",
        return_value={
            "run_ok": True,
            "closed": True,
            "steps": [{"id": "internet", "ok": True}],
            "confirmation_de": "✓ Trading-Kreislauf geschlossen",
        },
    ):
        result = run_r3_background_refresh(tmp_path)
    assert result.get("ok") is True
    assert result.get("closed") is True
