"""Tests for aa_cost_stress (V2R)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from aa_cost_stress import (
    CHALLENGER,
    apply_incremental_cost_stress,
    build_cost_stress_status,
    evaluate_variant_scenario,
    export_cost_stress_status,
    resolve_variant_sources,
)
from aa_evidence_schema import resolve_locked_champion


def _write_champion_inputs(root: Path, *, n: int = 300) -> None:
    (root / "model_output_sp500_pit_t212").mkdir(parents=True, exist_ok=True)
    idx = pd.date_range("2019-01-01", periods=n, freq="B")
    pd.DataFrame({"strategy_return": [0.0001] * n}, index=idx).to_csv(
        root / "model_output_sp500_pit_t212" / "strategy_daily_returns.csv"
    )
    dec = pd.DataFrame({"rebalance_date": [idx[0], idx[50]], "turnover": [0.9, 0.9]})
    dec.to_csv(root / "model_output_sp500_pit_t212" / "backtest_decisions.csv", index=False)
    report = root / "model_output_sp500_pit_t212" / "backtest_report.txt"
    report.write_text("fee_model: trading212\ncost_bps: 10\n", encoding="utf-8")
    m1_dir = root / "validation_runs" / "20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS"
    m1_dir.mkdir(parents=True, exist_ok=True)
    (m1_dir / "backtest_report.txt").write_text("cost_bps: 10\nfee_model: trading212\n", encoding="utf-8")
    naive_dir = (
        root
        / "runs"
        / "20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce"
    )
    naive_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"NAIVE_MOMENTUM_MOM_63_TOP12": [0.0002] * n}, index=idx).to_csv(
        naive_dir / "naive_momentum_daily_returns.csv"
    )


def test_missing_turnover_not_evaluable(tmp_path: Path):
    ret = tmp_path / "returns.csv"
    proof = tmp_path / "proof.txt"
    proof.write_text("cost_bps: 10\nfee_model: trading212\n", encoding="utf-8")
    pd.DataFrame({"strategy_return": [0.001, 0.002, -0.001]}, index=pd.date_range("2020-01-01", periods=3)).to_csv(ret)
    result = evaluate_variant_scenario(
        tmp_path,
        "TEST",
        {
            "returns_path": "returns.csv",
            "returns_column": "strategy_return",
            "decisions_path": "",
            "baseline_cost_proof_path": "proof.txt",
        },
        "PLUS_25_BPS",
        {"extra_bps": 25, "kind": "incremental_bps"},
    )
    assert result["evaluation_status"] == "NOT_EVALUABLE"
    assert result["reason"] == "turnover_missing"


def test_challenger_without_turnover_blocks_gate(tmp_path: Path):
    _write_champion_inputs(tmp_path)
    status = build_cost_stress_status(tmp_path)
    assert status["COST_STRESS_GATE"]["pass"] is False
    assert status["COST_STRESS_GATE"]["evaluation_status"] == "NOT_EVALUABLE"
    assert "CHALLENGER_TURNOVER_NOT_VERIFIED" in status["COST_STRESS_GATE"]["blockers"]


def test_proxy_sensitivity_not_gate_evidence(tmp_path: Path):
    _write_champion_inputs(tmp_path)
    status = build_cost_stress_status(tmp_path)
    proxy = status.get("sensitivity_analysis", {}).get("proxy_turnover_results", {})
    assert status["sensitivity_analysis"]["label"] == "NOT_GATE_EVIDENCE"
    if proxy:
        for scenario_rows in proxy.values():
            for row in scenario_rows:
                assert row.get("turnover_is_proxy") is True
                assert row.get("evaluation_status") != "EVALUABLE" or row.get("reason") == "turnover_proxy_only"


def test_unverified_baseline_blocks_gate(tmp_path: Path):
    _write_champion_inputs(tmp_path)
    (tmp_path / "model_output_sp500_pit_t212" / "backtest_report.txt").unlink()
    status = build_cost_stress_status(tmp_path)
    assert status["COST_STRESS_GATE"]["pass"] is False
    blockers = status["COST_STRESS_GATE"]["blockers"]
    assert any("BASELINE_COST_TREATMENT_NOT_VERIFIED" in b for b in blockers)


def test_synthetic_reproducible_stress():
    idx = pd.date_range("2020-01-01", periods=10, freq="B")
    returns = pd.Series([0.001] * 10, index=idx)
    turnover = pd.Series([0.5], index=[idx[0]])
    stressed, detail = apply_incremental_cost_stress(returns, turnover, extra_bps=25)
    assert detail["applied"] is True
    assert stressed.iloc[0] < returns.iloc[0]


def test_plus_25_bps_applied_to_turnover():
    idx = pd.date_range("2020-01-01", periods=5, freq="B")
    returns = pd.Series([0.01] * 5, index=idx)
    turnover = pd.Series([0.4], index=[idx[0]])
    stressed, detail = apply_incremental_cost_stress(returns, turnover, extra_bps=25)
    expected_drag = (25 / 10000.0) * 0.4
    assert abs(stressed.iloc[0] - (0.01 - expected_drag)) < 1e-9


def test_scenario_separates_evaluation_and_comparison(tmp_path: Path):
    _write_champion_inputs(tmp_path)
    sources = resolve_variant_sources(tmp_path)
    champion_id = resolve_locked_champion(tmp_path)
    champ = sources[champion_id]
    row = evaluate_variant_scenario(tmp_path, champion_id, champ, "PLUS_25_BPS", {"extra_bps": 25, "kind": "incremental_bps"})
    assert "evaluation_status" in row
    assert "comparison_result" in row
    assert row["evaluation_status"] == "EVALUABLE"
    assert row["comparison_result"] == "NOT_APPLICABLE"


def test_verified_challenger_can_be_evaluable(tmp_path: Path):
    _write_champion_inputs(tmp_path)
    naive_dir = (
        tmp_path
        / "runs"
        / "20260530T162749569Z_M1_MOM_BLEND_MATCHED_CONTROLS_dec4af3a_012fe917_s2i0_15c6ce"
    )
    idx = pd.date_range("2019-01-01", periods=300, freq="B")
    dec_dir = tmp_path / "model_output_sp500_pit_t212"
    chal_dec = dec_dir / "challenger_decisions.csv"
    pd.DataFrame({"rebalance_date": [idx[0], idx[50]], "turnover": [0.5, 0.5]}).to_csv(chal_dec, index=False)
    m1_report = tmp_path / "validation_runs" / "20260530T162737Z_M1_MOM_BLEND_MATCHED_CONTROLS" / "backtest_report.txt"
    source = {
        "returns_path": str(
            (naive_dir / "naive_momentum_daily_returns.csv").relative_to(tmp_path)
        ).replace("\\", "/"),
        "returns_column": "NAIVE_MOMENTUM_MOM_63_TOP12",
        "decisions_path": str(chal_dec.relative_to(tmp_path)).replace("\\", "/"),
        "baseline_cost_proof_path": str(m1_report.relative_to(tmp_path)).replace("\\", "/"),
        "gate_eligible": True,
    }
    row = evaluate_variant_scenario(tmp_path, CHALLENGER, source, "PLUS_25_BPS", {"extra_bps": 25, "kind": "incremental_bps"})
    assert row["evaluation_status"] == "EVALUABLE"
    assert row["turnover_is_proxy"] is False


def test_export_does_not_touch_promotion_files(tmp_path: Path):
    (tmp_path / "control").mkdir()
    (tmp_path / "control" / "auto_promotion_status.json").write_text('{"promotion_allowed": false}', encoding="utf-8")
    before = (tmp_path / "control" / "auto_promotion_status.json").read_text(encoding="utf-8")
    export_cost_stress_status(tmp_path)
    after = (tmp_path / "control" / "auto_promotion_status.json").read_text(encoding="utf-8")
    assert before == after
