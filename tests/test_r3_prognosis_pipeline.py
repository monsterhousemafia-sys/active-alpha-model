"""Prognose-Freischaltung — Pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_run_prognosis_automation(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    with patch(
        "analytics.r3_live_capital.compute_worthwhile_positions",
        return_value={
            "ok": True,
            "capital_basis": {"investable_eur": 641.0, "planning_cash_eur": 675.0},
            "worthwhile_buys": [{"symbol": "STX"}],
            "worthwhile_buy_count": 1,
        },
    ), patch(
        "analytics.r3_t212_prognosis.refresh_r3_daily_prognosis",
        return_value={"ok": True, "positions": 11, "investable_eur": 641.0, "t212_trusted": True},
    ), patch(
        "analytics.r3_trading_functions.build_r3_trading_functions",
        return_value={"functions_active": 1, "primary_function_id": "initial_order"},
    ), patch(
        "analytics.r3_freigabe.auto_prepare_freigabe_for_desktop",
        return_value={"package_ready": True},
    ), patch(
        "analytics.r3_t212_sync_coordinator.record_t212_sync",
    ), patch("analytics.desktop_shell_cache.warm_desktop_cache"):
        from analytics.r3_prognosis_pipeline import run_prognosis_automation

        doc = run_prognosis_automation(tmp_path, persist=True)
    assert doc.get("ok") is True
    assert (tmp_path / "evidence/r3_prognosis_pipeline_latest.json").is_file()


def test_ensure_prognosis_fresh_skips_when_recent(tmp_path: Path) -> None:
    import json
    from datetime import datetime, timezone

    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (tmp_path / "evidence/r3_t212_prognosis_latest.json").write_text(
        json.dumps(
            {
                "ok": True,
                "updated_at_utc": now,
                "positions": 11,
                "worthwhile_buy_count": 11,
                "worthwhile_buys": [{"symbol": "STX", "target_eur": 70.0}],
            }
        ),
        encoding="utf-8",
    )
    with patch("analytics.r3_prognosis_pipeline.run_prognosis_automation") as run:
        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

        out = ensure_r3_prognosis_fresh(tmp_path, force=False)
    assert out.get("skipped") is True
    run.assert_not_called()


def test_ensure_prognosis_fresh_refreshes_when_stale(tmp_path: Path) -> None:
    import json

    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/r3_t212_prognosis_latest.json").write_text(
        json.dumps({"ok": True, "updated_at_utc": "2020-01-01T00:00:00+00:00", "positions": 11}),
        encoding="utf-8",
    )
    with patch(
        "analytics.r3_prognosis_pipeline.run_prognosis_automation",
        return_value={"ok": True, "prognosis": {"ok": True, "worthwhile_buy_count": 11}},
    ) as run:
        from analytics.r3_prognosis_pipeline import ensure_r3_prognosis_fresh

        out = ensure_r3_prognosis_fresh(tmp_path, force=False)
    run.assert_called_once()
    assert out.get("ok") is True
