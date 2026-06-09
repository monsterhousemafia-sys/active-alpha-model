"""Phase F statistical evidence tests."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_champion_evidence_phase_f import (
    build_gate_matrix,
    build_robustness_rows,
    ensure_preregistered_trial_ledger,
    phase_f_variant_sources,
    run_phase_f,
)
from aa_evidence_schema import AUTHORITATIVE_CHAMPION


def _seed_mom_evidence(root: Path) -> None:
    dates = pd.date_range("2020-01-01", periods=200, freq="B")
    for rel in (
        "evidence/g1_independent_next_level/challenger/MOM_63_TOP12",
        "evidence/autonomous_research/MOM_63_TOP15_RECONSTRUCTED",
    ):
        base = root / rel
        base.mkdir(parents=True)
        pd.Series(0.0005, index=dates).to_frame("strategy_return").to_csv(base / "daily_returns.csv")
    g1 = root / "evidence/g1_independent_next_level/challenger/MOM_63_TOP12"
    (g1 / "turnover").mkdir(parents=True, exist_ok=True)
    (g1 / "turnover/rebalance_turnover.csv").write_text(
        "rebalance_date,turnover\n2020-02-01,0.4\n",
        encoding="utf-8",
    )
    out = root / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)
    pd.Series(0.0004, index=dates).to_csv(out / "strategy_daily_returns.csv")
    (out / "backtest_decisions.csv").write_text(
        "rebalance_date,turnover\n2020-02-01,0.3\n",
        encoding="utf-8",
    )
    (out / "backtest_report.txt").write_text("fee_model: trading212\n", encoding="utf-8")


def test_trial_ledger_created(tmp_path: Path) -> None:
    root = tmp_path
    out = ensure_preregistered_trial_ledger(root)
    assert out["status"] == "CREATED"
    assert (root / "research_evidence/trial_ledger_preregistered.json").is_file()


def test_gate_matrix_includes_champion(tmp_path: Path) -> None:
    root = tmp_path
    _seed_mom_evidence(root)
    cost_rows = [
        {
            "variant_id": AUTHORITATIVE_CHAMPION,
            "role": "CHAMPION",
            "scenario": "PLUS_25_BPS",
            "gate_result": "NOT_EVALUABLE",
            "reason": "test",
        }
    ]
    robust_rows = [
        {
            "variant_id": AUTHORITATIVE_CHAMPION,
            "role": "CHAMPION",
            "status": "EVALUABLE",
            "subperiod_sharpe_stability": "STABLE_POSITIVE",
        }
    ]
    matrix = build_gate_matrix(cost_rows, robust_rows, {"multiple_testing_status": {}})
    champ = next(r for r in matrix["rows"] if r.get("champion_row"))
    assert champ["variant_id"] == AUTHORITATIVE_CHAMPION


def test_phase_f_pipeline(tmp_path: Path) -> None:
    root = tmp_path
    _seed_mom_evidence(root)
    (root / "control").mkdir(parents=True)
    (root / "control/challenger_report.json").write_text(
        json.dumps({"entries": [{"variant_id": AUTHORITATIVE_CHAMPION}]}),
        encoding="utf-8",
    )
    (root / "evidence").mkdir(parents=True, exist_ok=True)
    summary = run_phase_f(root)
    assert summary["status"] == "COMPLETE"
    assert (root / "evidence/phase_f_gate_matrix.json").is_file()
    assert (root / "research_evidence/cost_stress_comparison.csv").is_file()
    matrix = json.loads((root / "evidence/phase_f_gate_matrix.json").read_text(encoding="utf-8"))
    assert any(r.get("champion_row") for r in matrix["rows"])


def test_mom_sources_turnover_when_present(tmp_path: Path) -> None:
    root = tmp_path
    _seed_mom_evidence(root)
    src = phase_f_variant_sources(root)
    assert src["MOM_63_TOP12"].get("turnover_verified") is True
