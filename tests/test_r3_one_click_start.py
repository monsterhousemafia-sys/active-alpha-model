"""R3 Ein-Klick-Start."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_one_click_start_pipeline(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    from analytics.r3_t212_operator_api import mark_operator_api_setup_complete

    mark_operator_api_setup_complete(tmp_path)
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.r3_t212_api_bond.ensure_r3_t212_api_bond",
        return_value={
            "setup_ok": True,
            "t212_trusted": True,
            "credentials_configured": True,
            "bonded": True,
            "headline_de": "T212 API verbunden",
            "steps": [{"step": "api_bond_sync", "ok": True}],
        },
    ), patch(
        "analytics.r3_prognosis_pipeline.run_prognosis_automation",
        return_value={"ok": True, "t212_trusted": True, "worthwhile_buys": 11, "investable_eur": 640.0},
    ), patch(
        "analytics.r3_freigabe.auto_prepare_freigabe_for_desktop",
        return_value={"package_ready": True, "notional_eur": 640.0},
    ):
        from analytics.r3_one_click_start import run_one_click_start

        doc = run_one_click_start(tmp_path, persist=True)
    assert doc.get("ok") is True
    assert doc.get("setup_ok") is True
    assert doc.get("package_ready") is True
    assert (tmp_path / "evidence/r3_one_click_start_latest.json").is_file()


def test_one_click_start_blocks_without_api_setup(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.r3_t212_api_bond.ensure_r3_t212_api_bond",
    ) as mock_bond, patch(
        "analytics.r3_prognosis_pipeline.run_prognosis_automation",
    ) as mock_pipeline:
        from analytics.r3_one_click_start import run_one_click_start

        doc = run_one_click_start(tmp_path, persist=False)
    assert doc.get("ok") is False
    assert doc.get("needs_api_setup") is True
    mock_bond.assert_not_called()
    mock_pipeline.assert_not_called()


def test_one_click_waits_for_trust_before_prognosis(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    from analytics.r3_t212_operator_api import mark_operator_api_setup_complete

    mark_operator_api_setup_complete(tmp_path)
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
    ), patch(
        "analytics.r3_t212_api_bond.ensure_r3_t212_api_bond",
        return_value={
            "setup_ok": True,
            "t212_trusted": False,
            "credentials_configured": True,
            "headline_de": "Sync läuft",
            "steps": [],
        },
    ), patch(
        "analytics.r3_prognosis_pipeline.run_prognosis_automation",
    ) as mock_pipeline:
        from analytics.r3_one_click_start import run_one_click_start

        doc = run_one_click_start(tmp_path, persist=False)
    assert doc.get("setup_ok") is True
    assert doc.get("t212_trusted") is False
    mock_pipeline.assert_not_called()
