"""Pilot preflight verification tests."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_pilot_verification_governance_and_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    root = tmp_path
    shutil.copytree(
        Path(__file__).resolve().parents[1] / "paper" / "config",
        root / "paper" / "config",
    )
    shutil.copy(Path(__file__).resolve().parents[1] / "promotion_gate_config.yaml", root / "promotion_gate_config.yaml")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    monkeypatch.setenv("AA_OFFLINE_COCKPIT_TEST", "1")

    from tools.run_pilot_live_verification import verify_governance, verify_pilot_config

    gov = verify_governance(root)
    assert gov["pass"] is True
    cfg = verify_pilot_config(root)
    assert cfg["pass"] is True
    assert cfg["initial_capital_eur"] == 500.0


def test_pilot_verification_t212_not_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.run_pilot_live_verification import verify_t212_live

    monkeypatch.setattr(
        "integrations.trading212.t212_credentials_loader.load_credentials",
        lambda: type("C", (), {"configured": False})(),
    )
    monkeypatch.setattr(
        "integrations.trading212.t212_readonly_connection_service.connection_status_summary",
        lambda *a, **k: type("S", (), {"credentials_configured": False, "status": "NOT_CONFIGURED"})(),
    )
    step = verify_t212_live(tmp_path, force_sync=False)
    assert step["name"] == "t212_live"
    assert step["pass"] is False
    assert step["mode"] == "awaiting_user_setup"
    assert step["user_action"]
