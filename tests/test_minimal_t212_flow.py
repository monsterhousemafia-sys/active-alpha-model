"""Minimal T212 + model plan operational gate."""
from __future__ import annotations

from analytics.pilot_investment_plan import build_investment_plan, ensure_plan_symbols_in_scope
from tools.verify_minimal_t212_flow import run_minimal_flow


def test_run_minimal_flow_with_mocked_broker(tmp_path, monkeypatch):
    import integrations.trading212.t212_readonly_connection_service as ro

    class _Broker:
        status = "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE"
        cash_eur = 400.0
        positions_count = 0
        last_successful_sync_utc = "2026-06-01T00:00:00+00:00"
        last_error = None

    monkeypatch.setattr(ro, "sync_readonly_account", lambda root, force=False: _Broker())

    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    import pandas as pd

    pd.DataFrame(
        [{"ticker": "INTC", "target_weight": 0.1, "alpha_lcb": 0.5, "signal_date": "2026-06-01"}]
    ).to_csv(tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False)

    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/learning_collection_policy.json").write_text(
        '{"active_champion_locked":"R3_w075_q065_noexit","auto_champion_update_enabled":false}',
        encoding="utf-8",
    )
    (tmp_path / "control/trading_mode_preference.json").write_text(
        '{"mode":"ai_assisted","schema_version":1}', encoding="utf-8"
    )
    (tmp_path / "control/p17_review_mode_user_preference.json").write_text(
        '{"review_mode_enabled":false,"schema_version":1}', encoding="utf-8"
    )
    (tmp_path / "control/pilot_live_trading_ack.json").write_text(
        '{"enabled":true,"mode":"MANUAL_CONFIRM_BEFORE_SUBMIT"}', encoding="utf-8"
    )

    plan = build_investment_plan(tmp_path, 400.0)
    ensure_plan_symbols_in_scope(tmp_path, plan)

    report = run_minimal_flow(tmp_path, dry_run_order=False)
    assert report["t212_connected"] is True
    assert report["model_plan_ready"] is True
    assert report["pilot_core_ready"] is True
