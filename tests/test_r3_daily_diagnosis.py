from __future__ import annotations

from pathlib import Path

import pandas as pd

from aa_r3_daily_diagnosis import (
    build_refinement_hints,
    compute_live_market_regime,
    enrich_snapshot_market_regime,
    load_stored_signal_diagnosis,
    verify_r3_diagnosis_against_daily_data,
    write_r3_diagnosis_manifest,
)


def _write_price_panel(out_dir: Path, *, benchmark: str, closes: list[float]) -> None:
    cache = out_dir / "price_cache"
    cache.mkdir(parents=True, exist_ok=True)
    dates = pd.bdate_range("2024-01-01", periods=len(closes))
    panel = pd.DataFrame(
        {
            "date": dates,
            "ticker": benchmark,
            "Close": closes,
        }
    )
    panel.to_parquet(cache / "ohlcv_panel.parquet", index=False)


def test_compute_live_market_regime_risk_on():
    import active_alpha_model as aam

    idx = pd.bdate_range("2024-01-01", periods=250)
    close = pd.Series([100 + i * 0.5 for i in range(250)], index=idx)
    cfg = aam.BacktestConfig()
    live = compute_live_market_regime(close, cfg)
    assert live["risk_on"] is True
    assert live["regime_label"] == "RISK_ON"


def test_compute_live_market_regime_risk_off():
    import active_alpha_model as aam

    idx = pd.bdate_range("2024-01-01", periods=250)
    close = pd.Series([200 - i * 0.8 for i in range(250)], index=idx)
    cfg = aam.BacktestConfig()
    live = compute_live_market_regime(close, cfg)
    assert live["risk_on"] is False
    assert live["regime_label"] == "RISK_OFF"


def test_load_stored_signal_diagnosis(tmp_path: Path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "latest_signals.csv").write_text(
        "signal_date,ticker,target_weight,risk_on,risk_off_gate_mode,"
        "risk_off_momentum_rescue_quantile,eligibility_reason\n"
        "2026-05-28,AAA,0.5,False,momentum_rescue,0.65,risk_off_momentum_rescue\n"
        "2026-05-28,BBB,0.5,False,momentum_rescue,0.65,risk_off_legacy_gate\n",
        encoding="utf-8",
    )
    doc = load_stored_signal_diagnosis(out)
    assert doc["available"] is True
    assert doc["risk_on"] is False
    assert doc["n_rescued_by_momentum"] == 1


def test_build_refinement_hints_regime_drift():
    hints = build_refinement_hints(
        live={"risk_on": True, "regime_label": "RISK_ON"},
        stored={"available": True, "risk_on": False, "regime_label": "RISK_OFF"},
        feedback={},
        price_latest="2026-05-29",
        signal_date="2026-05-28",
    )
    assert any("Regime-Drift" in h for h in hints)
    assert any("Preis-Stand" in h for h in hints)


def test_enrich_snapshot_market_regime_fills_missing_ret63(tmp_path: Path):
    import active_alpha_model as aam
    from aa_portfolio import determine_risk_on

    out = tmp_path / "model_out"
    out.mkdir()
    closes = [100 + i * 0.4 for i in range(250)]
    _write_price_panel(out, benchmark="SPY", closes=closes)
    cfg = aam.BacktestConfig(benchmark="SPY")
    latest = pd.bdate_range("2024-01-01", periods=len(closes))[-1]
    snap = pd.DataFrame(
        {
            "date": [latest],
            "ticker": ["AAA"],
            "market_trend_200": [1.0],
            "market_ret_63": [float("nan")],
        }
    )
    mt = float(snap["market_trend_200"].iloc[0])
    assert determine_risk_on(mt, -1.0, cfg) is False
    enriched = enrich_snapshot_market_regime(snap, cfg, out, as_of=latest)
    mr = float(enriched["market_ret_63"].iloc[0])
    assert mr > -0.07
    assert determine_risk_on(mt, mr, cfg) is True


def test_verify_r3_diagnosis_against_daily_data(tmp_path: Path, monkeypatch):
    import active_alpha_model as aam

    out = tmp_path / "model_out"
    out.mkdir()
    _write_price_panel(out, benchmark="SPY", closes=[100 + i * 0.4 for i in range(250)])
    (out / "latest_signals.csv").write_text(
        "signal_date,ticker,target_weight,risk_on\n"
        "2026-05-28,AAA,1.0,True\n",
        encoding="utf-8",
    )

    env = {"AA_BACKTEST_OUT_DIR": str(out), "AA_BENCHMARK": "SPY"}

    class _Cfg(aam.BacktestConfig):
        pass

    def _fake_from_args(_args):
        return aam.BacktestConfig()

    monkeypatch.setattr("aa_config.BacktestConfig.from_args", _fake_from_args)
    monkeypatch.setattr("aa_config.parse_args", lambda: None)
    monkeypatch.setattr("aa_config_env.build_backtest_argv", lambda _e: ["prog"])

    report = verify_r3_diagnosis_against_daily_data(tmp_path, env, update_feedback=False)
    assert report.ok is True
    assert report.regime_match is True
    assert (out / "r3_daily_diagnosis.json").is_file()
