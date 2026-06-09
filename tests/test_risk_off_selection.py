from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import active_alpha_model as aam
from aa_portfolio import (
    _blended_risk_off_selection_score,
    _ensemble_selection_score,
    _momentum_rank_pct,
    _momentum_score,
    safe_rank_pct,
    select_portfolio,
)


def _mini_snapshot(*, risk_on: bool = False) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ticker": ["AAA", "BBB", "CCC", "DDD"],
            "mu_hat": [0.02, 0.01, -0.01, 0.005],
            "rank_score": [0.8, 0.6, 0.4, 0.55],
            "alpha_lcb": [0.01, -0.02, -0.05, -0.01],
            "trend_50": [1, 0, 0, 1],
            "trend_200": [1, 0, 0, 0],
            "rel_strength_63": [0.6, 0.5, 0.4, 0.45],
            "sector_rel_strength_63": [0.5, 0.5, 0.5, 0.5],
            "vol_20": [0.2, 0.25, 0.3, 0.22],
            "idio_vol_63": [0.2, 0.25, 0.3, 0.22],
            "adv_20": [1e8, 1e8, 1e8, 1e8],
            "in_universe": [True, True, True, True],
            "mom_252_21": [0.30, 0.20, 0.10, 0.25],
            "mom_126_21": [0.20, 0.15, 0.05, 0.18],
            "mom_63_21": [0.10, 0.05, 0.02, 0.08],
            "market_trend_200": [1.0 if risk_on else 0.9] * 4,
            "market_ret_63": [0.05 if risk_on else -0.05] * 4,
            "sector": ["Tech", "Tech", "Energy", "Health"],
            "issuer": ["AAA", "BBB", "CCC", "DDD"],
            "correlation_cluster": ["C1", "C1", "C2", "C3"],
            "beta_252": [1.1, 1.0, 0.9, 0.8],
        }
    )


def test_prediction_fingerprint_changes_with_risk_off_selection_mode():
    cfg_legacy = aam.BacktestConfig(risk_off_selection_mode="legacy")
    cfg_blend = aam.BacktestConfig(risk_off_selection_mode="mom_blend_blend", risk_off_momentum_weight=0.70)
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]
    assert aam._prediction_build_fingerprint(cfg_legacy, 100, rbs) != aam._prediction_build_fingerprint(cfg_blend, 100, rbs)


def test_prediction_fingerprint_changes_with_force_exit_flag():
    cfg_off = aam.BacktestConfig(risk_off_force_exit_enabled=False)
    cfg_on = aam.BacktestConfig(risk_off_force_exit_enabled=True)
    rbs = [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-02-01")]
    assert aam._prediction_build_fingerprint(cfg_off, 100, rbs) != aam._prediction_build_fingerprint(cfg_on, 100, rbs)


def test_config_validation_rejects_invalid_modes():
    with pytest.raises(ValueError):
        aam.BacktestConfig(risk_off_selection_mode="invalid")
    with pytest.raises(ValueError):
        aam.BacktestConfig(risk_off_gate_mode="bad")
    with pytest.raises(ValueError):
        aam.BacktestConfig(risk_off_momentum_weight=1.5)


def test_momentum_rank_direction():
    snap = _mini_snapshot(risk_on=False)
    cfg = aam.BacktestConfig()
    mom = _momentum_score(snap, "mom_blend_top12")
    rank = _momentum_rank_pct(snap, cfg)
    best = mom.idxmax()
    worst = mom.idxmin()
    assert float(rank.loc[best]) > float(rank.loc[worst])


def test_momentum_rescue_gate_allows_strong_momentum_despite_weak_alpha():
    cfg = aam.BacktestConfig(risk_off_gate_mode="momentum_rescue", risk_off_momentum_rescue_quantile=0.70, min_edge=0.0)
    snap = _mini_snapshot(risk_on=False)
    snap.loc[2, "alpha_lcb"] = -0.10
    snap.loc[2, "trend_50"] = 0
    snap.loc[2, "trend_200"] = 0
    snap.loc[2, "mom_252_21"] = 0.50
    snap.loc[2, "mom_126_21"] = 0.40
    snap.loc[2, "mom_63_21"] = 0.30
    cfg_legacy = aam.BacktestConfig(risk_off_gate_mode="legacy", min_edge=0.0)
    eligible_legacy = aam.compute_risk_off_eligibility(snap, cfg_legacy, risk_on=False)
    eligible_rescue = aam.compute_risk_off_eligibility(snap, cfg, risk_on=False)
    assert not bool(eligible_legacy.iloc[2])
    assert bool(eligible_rescue.iloc[2])


def test_blend_weight_calculation():
    snap = _mini_snapshot(risk_on=False)
    cfg = aam.BacktestConfig(risk_off_selection_mode="mom_blend_blend", risk_off_momentum_weight=0.70)
    cross = snap.copy()
    ensemble = _ensemble_selection_score(cross)
    ens_rank = safe_rank_pct(ensemble, ascending=True)
    mom_rank = _momentum_rank_pct(cross, cfg)
    expected = (1.0 - 0.70) * ens_rank + 0.70 * mom_rank - 0.5
    got = _blended_risk_off_selection_score(cross, cfg, risk_on=False)
    pd.testing.assert_series_equal(got, expected, check_names=False, atol=1e-9)


def test_risk_on_selection_unchanged_across_modes():
    snap = _mini_snapshot(risk_on=True)
    cfg_legacy = aam.BacktestConfig(risk_off_selection_mode="legacy")
    cfg_blend = aam.BacktestConfig(risk_off_selection_mode="mom_blend_blend", risk_off_momentum_weight=0.70)
    cross = snap.copy()
    s_legacy = _blended_risk_off_selection_score(cross, cfg_legacy, risk_on=True)
    s_blend = _blended_risk_off_selection_score(cross, cfg_blend, risk_on=True)
    pd.testing.assert_series_equal(s_legacy, s_blend)
    e_legacy = aam.compute_risk_off_eligibility(snap, cfg_legacy, risk_on=True)
    e_blend = aam.compute_risk_off_eligibility(snap, cfg_blend, risk_on=True)
    pd.testing.assert_series_equal(e_legacy, e_blend)


def test_forced_exit_tickers_when_gates_fail():
    cfg = aam.BacktestConfig(risk_off_force_exit_enabled=True, min_edge=0.0, risk_off_gate_mode="legacy")
    snap = _mini_snapshot(risk_on=False)
    snap.loc[2, "alpha_lcb"] = -0.10
    snap.loc[2, "trend_50"] = 0
    snap.loc[2, "trend_200"] = 0
    snap.loc[2, "mom_252_21"] = 0.01
    prev = pd.Series({"CCC": 0.05})
    forced = aam.compute_risk_off_forced_exit_tickers(snap, prev, cfg, risk_on=False)
    assert "CCC" in forced


def test_apply_buy_hold_spread_respects_forced_exit():
    cfg = aam.BacktestConfig(top_k=1, buy_hold_spread=True, hold_rank_multiple=2.5)
    target = pd.Series({"AAA": 0.10})
    previous = pd.Series({"CCC": 0.05})
    ranked = pd.DataFrame({"ticker": ["AAA", "BBB", "CCC"], "selection_score": [1.0, 0.5, 0.4]})
    out = aam.apply_buy_hold_spread(target, previous, ranked, cfg, forced_exit_tickers={"CCC"})
    assert float(out.get("CCC", 0.0)) == 0.0


def test_select_portfolio_includes_risk_off_diagnostic_columns():
    snap = _mini_snapshot(risk_on=False)
    snap["date"] = pd.Timestamp("2020-06-01")
    cfg = aam.BacktestConfig(
        risk_off_selection_mode="mom_blend_blend",
        risk_off_gate_mode="momentum_rescue",
        top_k=2,
        max_gross_exposure=1.0,
        min_edge=0.0,
    )
    weights, ranked = select_portfolio(snap, rmse=0.01, cfg=cfg)
    for col in [
        "risk_off_selection_mode",
        "risk_off_momentum_score",
        "risk_off_momentum_rank",
        "ensemble_selection_score",
        "ensemble_selection_rank",
        "eligibility_reason",
        "eligible_legacy_risk_off",
        "eligible_momentum_rescue",
    ]:
        assert col in ranked.columns


def test_naive_artifact_slug_matched_controls():
    from aa_backtest import _naive_artifact_slug

    assert _naive_artifact_slug("mom_blend_matched_controls") == "mom_blend_matched_controls"
    assert _naive_artifact_slug("mom_blend_top12") == "naive_mom_blend"


def test_naive_daily_returns_path_prefers_naive_file(tmp_path: Path):
    from aa_risk_off_reporting import _resolve_daily_returns_path

    (tmp_path / "naive_mom_blend_daily_returns.csv").write_text("date,strategy_return\n2020-01-01,0.0\n", encoding="utf-8")
    (tmp_path / "strategy_daily_returns.csv").write_text("date,strategy_return\n2020-01-01,0.0\n", encoding="utf-8")
    p = _resolve_daily_returns_path("NAIVE_MOM_BLEND_TOP12", tmp_path)
    assert p.name == "naive_mom_blend_daily_returns.csv"
    p2 = _resolve_daily_returns_path("R0_LEGACY_ENSEMBLE", tmp_path)
    assert p2.name == "strategy_daily_returns.csv"


def test_experiment_runner_defines_separate_output_dirs():
    from run_active_alpha_riskoff_experiments import EXPERIMENTS, build_command

    keys = {e["key"] for e in EXPERIMENTS}
    assert "R0_LEGACY_ENSEMBLE" in keys
    assert "R3_w070_q070_noexit" in keys
    assert "R4_w070_q070_forceexit" in keys
    roots = set()
    for exp in EXPERIMENTS:
        cmd = build_command(exp, research_root=Path("research_riskoff_experiments"), shared_cache=Path("cache"))
        out_idx = cmd.index("--out-dir") + 1
        roots.add(cmd[out_idx])
        assert "process" in cmd
        assert "--parallel-profile" in cmd
    assert len(roots) == len(EXPERIMENTS)
