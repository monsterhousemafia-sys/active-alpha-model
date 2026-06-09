"""Active Alpha Model — Hintergrund-Engine, R3 nur Anzeige."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from analytics.alpha_model_background_engine import (
    build_engine_status,
    load_engine_policy,
    render_r3_engine_status_line,
    tick_alpha_model_background,
)


def test_engine_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_engine_policy(root)
    assert policy.get("status") == "AUTHORITATIVE"
    assert "auto_orders" in str(policy.get("forbidden_de") or "")


def test_tick_runs_steps(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "control/alpha_model_background_engine_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05", "generated_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_internet_latest.json").write_text(
        json.dumps({"internet_ok": True, "updated_at_utc": "2026-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    with patch(
        "analytics.prediction_operations.maybe_run_eod_prediction_switch",
        return_value={"ok": True, "skipped": True, "reason": "eod_not_due"},
    ), patch(
        "analytics.r3_closed_loop.load_r3_account_for_engine",
        return_value={
            "ok": True,
            "planning_cash_eur": 500.0,
            "investable_eur": 475.0,
            "cash_eur": 500.0,
            "cash_source": "r3_t212_api_bond",
            "message_de": "R3 · 475 € investierbar",
        },
    ), patch(
        "analytics.live_trading_operations.rebalance_status",
        return_value={"is_due": False, "summary_de": "OK"},
    ), patch(
        "analytics.king_plan_integration.rebuild_investment_plan_with_king",
        return_value={
            "ok": True,
            "pipeline_synced": True,
            "investable_eur": 475.0,
            "plan_capital_eur": 475.0,
            "t212_positions_count": 0,
            "detail_de": "Plan",
        },
    ), patch(
        "analytics.king_trading_assist.run_king_trading_assist",
        return_value={"step": "king_trading", "ok": True, "skipped": True, "reason_de": "test"},
    ), patch(
        "analytics.live_profile_governance.h1_backtest_status",
        return_value={"status": "RUNNING", "progress_pct": 42},
    ), patch(
        "analytics.r3_prognosis_pipeline.ensure_r3_prognosis_fresh",
        return_value={
            "ok": True,
            "skipped": False,
            "prognosis": {
                "ok": True,
                "signal_date": "2026-06-05",
                "positions": 3,
                "message_de": "bereit",
            },
        },
    ):
        doc = tick_alpha_model_background(tmp_path, force=True)
    assert doc.get("steps_total") == 6
    assert doc.get("order_prep", {}).get("ok") is not None or "order_prep" in doc
    assert (tmp_path / "evidence/alpha_model_background_engine_latest.json").is_file()
    assert "Active Alpha" in str(doc.get("confirmation_de") or "")
    assert doc.get("h1_backtest", {}).get("status") == "RUNNING"


def test_render_engine_line(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence/alpha_model_background_engine_latest.json").write_text(
        json.dumps({"confirmation_de": "Active Alpha · Test", "ok": True, "r3_display": {"ok": True}}),
        encoding="utf-8",
    )
    html_out = render_r3_engine_status_line(tmp_path)
    assert 'id="r3-engine-status"' in html_out
    assert "Active Alpha" in html_out


def test_desktop_includes_engine_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AA_PROJECT_ROOT", str(tmp_path))
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-05", "top_picks": [{"ticker": "A", "target_weight": 0.1}]}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/alpha_model_background_engine_latest.json").write_text(
        json.dumps({"confirmation_de": "Active Alpha · Hintergrund", "ok": True, "r3_display": {"ok": True}}),
        encoding="utf-8",
    )
    for name in (
        "r3_local_first_policy.json",
        "r3_t212_api_bond_policy.json",
        "r3_flow_orchestrator_policy.json",
    ):
        (tmp_path / "control" / name).write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_network_pulse_latest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/king_hardware_latest.json").write_text("{}", encoding="utf-8")
    from analytics.preview_hub_page import render_desktop_shell_page

    html_out = render_desktop_shell_page(tmp_path).decode("utf-8")
    assert "r3-trading-functions" in html_out or "r3-freigabe-btn" in html_out
    assert "r3-engine-status" not in html_out
