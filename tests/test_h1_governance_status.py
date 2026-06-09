"""H1 governance central status."""
from __future__ import annotations

from pathlib import Path

from analytics.h1_governance_status import estimate_h1_progress_pct, format_h1_banner_de, sync_h1_governance_status


def test_banner_running(tmp_path: Path) -> None:
    doc = {"status": "RUNNING", "sealed": False, "progress_pct": 68}
    assert "68%" in format_h1_banner_de(doc)
    assert "Seal" in format_h1_banner_de(doc)


def test_progress_features_done(tmp_path: Path) -> None:
    run = tmp_path / "validation_runs/20260606T102626Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "features.parquet").write_bytes(b"x")
    pct = estimate_h1_progress_pct(
        tmp_path,
        {"status": "RUNNING", "run_dir": "validation_runs/20260606T102626Z_DAILY_ALPHA_H1"},
    )
    assert pct >= 60


def test_banner_complete_seal_optional() -> None:
    doc = {
        "status": "COMPLETE",
        "sealed": False,
        "seal_required": False,
        "seal_policy_de": "H1-Seal optional",
    }
    banner = format_h1_banner_de(doc)
    assert "optional" in banner.lower() or "Seal optional" in banner


def test_sync_writes_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda r: {"status": "RUNNING", "run_dir": "validation_runs/x"},
    )
    monkeypatch.setattr("analytics.live_profile_governance.is_h1_backtest_sealed", lambda r: False)
    doc = sync_h1_governance_status(tmp_path, write_readiness=False)
    assert (tmp_path / "control/h1_governance_status.json").is_file()
    assert doc.get("banner_de")
