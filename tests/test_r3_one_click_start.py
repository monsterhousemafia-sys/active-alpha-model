"""R3 Ein-Klick-Start."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_one_click_start_pipeline(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    with patch(
        "analytics.r3_internet_requirement.require_internet_for",
        return_value={"allowed": True},
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
    assert doc.get("package_ready") is True
    assert (tmp_path / "evidence/r3_one_click_start_latest.json").is_file()
