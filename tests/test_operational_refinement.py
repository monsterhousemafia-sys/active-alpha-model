from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from aa_operational_refinement import (
    DEFAULT_REFINEMENT,
    apply_turbo_capacity_env,
    load_refinement_config,
    run_operational_refinement,
)


def test_apply_turbo_capacity_env_defaults():
    env = apply_turbo_capacity_env({})
    assert env["AA_CPU_CORES"] == "16"
    assert env["AA_RUNTIME_PROFILE"] == "turbo"
    assert env["AA_RESERVE_CPU_CORES"] == "0"


def test_load_refinement_config_merges_control_file(tmp_path: Path):
    ctrl = tmp_path / "control"
    ctrl.mkdir()
    (ctrl / "operational_refinement.json").write_text(
        '{"enabled": true, "refresh_signal": false}',
        encoding="utf-8",
    )
    cfg = load_refinement_config(tmp_path)
    assert cfg["enabled"] is True
    assert cfg["refresh_signal"] is False
    assert cfg["auto_signal_on_regime_drift"] is True


def test_run_operational_refinement_orchestrates_steps(tmp_path: Path, monkeypatch):
    ctrl = tmp_path / "control"
    ctrl.mkdir()
    out = tmp_path / "model_out"
    out.mkdir()

    sync_mock = MagicMock()
    sync_mock.ok = True
    sync_mock.r3_regime_match = True
    sync_mock.signal_refreshed = True
    sync_mock.messages = ["sync ok"]
    sync_mock.portfolio_tickers = []
    sync_mock.merged_ticker_count = 0
    sync_mock.live_quotes = {}
    sync_mock.manifest_path = str(out / "live_daily_sync.json")
    sync_mock.prices_refreshed = True
    sync_mock.price_latest = "2026-05-29"
    sync_mock.signal_date = "2026-05-29"
    sync_mock.r3_diagnosis_ok = True
    sync_mock.r3_diagnosis_path = str(out / "r3_daily_diagnosis.json")

    monkeypatch.setattr("aa_live_daily_sync.sync_live_daily_for_predictions", lambda *a, **k: sync_mock)
    monkeypatch.setattr(
        "aa_ops_refresh.resolve_out_dir",
        lambda _r, _e: out,
    )
    monkeypatch.setattr(
        "aa_prediction_outcomes.update_prediction_outcomes",
        lambda _o: {"metrics": {"n_mature": 5}},
    )
    monkeypatch.setattr("aa_model_status.write_model_status", lambda _o, **k: out / "model_status.json")
    monkeypatch.setattr("aa_control_plane.sync_control_plane", lambda *_: None)
    monkeypatch.setattr("aa_control_plane.write_next_cursor_prompt", lambda *_: None)
    monkeypatch.setattr(
        "aa_decision_cockpit_readonly_snapshot.refresh_live_review_snapshot",
        lambda _r: ctrl / "review_snapshot.json",
    )

    env = {"AA_BACKTEST_OUT_DIR": str(out)}
    cfg = dict(DEFAULT_REFINEMENT)
    cfg["run_background_research"] = False

    report = run_operational_refinement(tmp_path, env, cfg=cfg, log_print=False)
    assert report.ok is True
    assert report.cockpit_refreshed is True
    assert report.model_status_updated is True
    assert any(s["step"] == "live_daily_sync" for s in report.steps)
    assert (tmp_path / "control" / "operational_refinement_state.json").is_file()


def test_auto_signal_on_regime_drift(tmp_path: Path, monkeypatch):
    out = tmp_path / "model_out"
    out.mkdir()
    (tmp_path / "control").mkdir()

    sync_mock = MagicMock()
    sync_mock.ok = True
    sync_mock.r3_regime_match = False
    sync_mock.signal_refreshed = False
    sync_mock.messages = []
    sync_mock.portfolio_tickers = []
    sync_mock.merged_ticker_count = 0
    sync_mock.live_quotes = {}
    sync_mock.manifest_path = ""
    sync_mock.prices_refreshed = True
    sync_mock.price_latest = "2026-05-29"
    sync_mock.signal_date = "2026-05-28"
    sync_mock.r3_diagnosis_ok = True
    sync_mock.r3_diagnosis_path = ""

    r3_after = MagicMock()
    r3_after.regime_match = True
    r3_after.messages = ["fixed"]

    monkeypatch.setattr("aa_live_daily_sync.sync_live_daily_for_predictions", lambda *a, **k: sync_mock)
    monkeypatch.setattr("aa_ops_refresh.resolve_out_dir", lambda _r, _e: out)
    monkeypatch.setattr("aa_ops_refresh.refresh_signal_portfolio", lambda *a, **k: True)
    monkeypatch.setattr(
        "aa_r3_daily_diagnosis.verify_r3_diagnosis_against_daily_data",
        lambda *a, **k: r3_after,
    )

    class _DataReport:
        signal_date = None

    monkeypatch.setattr("aa_data_freshness.assess_daily_data", lambda *a, **k: _DataReport())
    monkeypatch.setattr(
        "aa_prediction_outcomes.update_prediction_outcomes",
        lambda _o: {"metrics": {}},
    )
    monkeypatch.setattr("aa_model_status.write_model_status", lambda _o, **k: out / "model_status.json")
    monkeypatch.setattr("aa_control_plane.sync_control_plane", lambda *_: None)
    monkeypatch.setattr("aa_control_plane.write_next_cursor_prompt", lambda *_: None)
    monkeypatch.setattr(
        "aa_decision_cockpit_readonly_snapshot.refresh_live_review_snapshot",
        lambda _r: tmp_path / "snap.json",
    )

    cfg = dict(DEFAULT_REFINEMENT)
    cfg["run_background_research"] = False
    report = run_operational_refinement(
        tmp_path,
        {"AA_BACKTEST_OUT_DIR": str(out)},
        cfg=cfg,
        log_print=False,
    )
    assert report.r3_regime_match is True
    assert any(s["step"] == "auto_signal_on_drift" for s in report.steps)
