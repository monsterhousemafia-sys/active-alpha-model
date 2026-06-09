"""Phase S5 — Interactive cockpit sector reference display."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from aa_sector_reference import clear_reference_cache, write_sector_reference_status
from ui.interactive_cockpit.services.cockpit_state_service import _attach_sector_reference_state


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    clear_reference_cache()
    yield
    clear_reference_cache()


def test_attach_sector_status_read_only(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    write_sector_reference_status(tmp_path, {"status": "OK", "source": "test"})
    state: dict = {}
    _attach_sector_reference_state(tmp_path, state, full_remediation=False)
    assert "sector_status" in state
    assert "Sektoren" in state["sector_status"]["summary_de"]
    assert state["sector_refresh"] == {}


def test_full_remediation_calls_sector_refresh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    def _fake(root: Path, env: dict) -> dict:
        called.append(True)
        return {"refreshed": True, "message_de": "Sektoren OK"}

    monkeypatch.setattr("aa_sector_reference.ensure_sector_reference_fresh", _fake)
    monkeypatch.setattr("aa_config_env.load_aa_env", lambda r: {"AA_PROJECT_ROOT": str(tmp_path)})
    state: dict = {}
    _attach_sector_reference_state(tmp_path, state, full_remediation=True)
    assert called == [True]
    assert state["sector_refresh"]["refreshed"] is True
    assert "sector_status" in state


@pytest.fixture
def cockpit_win(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AA_ALLOW_MULTI_INSTANCE", "1")
    monkeypatch.setenv("AA_OFFLINE_COCKPIT_TEST", "1")
    monkeypatch.setenv("AA_P17_REVIEW_MODE_NO_LIVE_NETWORK_SUBMISSION", "1")
    monkeypatch.setenv("AA_NO_LIVE_ORDER_SUBMISSION", "1")
    from PySide6.QtWidgets import QApplication
    from ui.interactive_cockpit.main_window import InteractiveCockpitWindow

    QApplication.instance() or QApplication([])
    return InteractiveCockpitWindow(tmp_path)


def test_market_tab_shows_sector_label(cockpit_win) -> None:
    cockpit_win.state["sector_status"] = {
        "summary_de": "Sektoren: Stand 2026-06-03 · Champion 14/14",
        "traffic": "GRUEN",
        "status_file": {"status": "OK", "updated_at_utc": "2026-06-03T12:00:00+00:00"},
        "reference_path": "sector_reference.csv",
    }
    cockpit_win._go_nav("market")
    assert hasattr(cockpit_win, "_sector_reference_label")
    cockpit_win._refresh_all_views()
    text = cockpit_win._sector_reference_label.text()
    assert "Champion 14/14" in text
    assert "Status-Datei: OK" in text
