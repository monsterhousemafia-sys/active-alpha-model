"""Tests for prediction outcome ledger (Phase 2)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from aa_prediction_outcomes import (
    append_predictions_from_decisions,
    compute_feedback_metrics,
    load_ledger,
    make_prediction_id,
    mature_pending_from_decisions,
    sync_outcome_ledger_from_out_dir,
    update_prediction_outcomes,
)


def _write_sample_decisions(path: Path) -> None:
    rows = [
        {
            "rebalance_date": "2020-01-02",
            "date": "2020-01-02",
            "ticker": "AAPL",
            "mu_hat": 0.02,
            "alpha_lcb": 0.01,
            "rank_score": 0.9,
            "selection_score": 0.8,
            "target_weight": 0.1,
            "target": 0.015,
            "risk_on": True,
            "selection_mode": "legacy",
            "gate_mode": "legacy",
        },
        {
            "rebalance_date": "2020-01-02",
            "date": "2020-01-02",
            "ticker": "MSFT",
            "mu_hat": -0.01,
            "alpha_lcb": -0.02,
            "rank_score": 0.4,
            "selection_score": 0.3,
            "target_weight": 0.0,
            "target": 0.005,
            "risk_on": True,
            "selection_mode": "legacy",
            "gate_mode": "legacy",
        },
        {
            "rebalance_date": "2020-01-07",
            "date": "2020-01-07",
            "ticker": "AAPL",
            "mu_hat": 0.03,
            "alpha_lcb": 0.02,
            "rank_score": 0.95,
            "selection_score": 0.85,
            "target_weight": 0.12,
            "target": float("nan"),
            "risk_on": False,
            "selection_mode": "mom_blend_blend",
            "gate_mode": "momentum_rescue",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_make_prediction_id_stable() -> None:
    a = make_prediction_id(variant_id="R3", rebalance_date="2020-01-02", ticker="AAPL")
    b = make_prediction_id(variant_id="R3", rebalance_date="2020-01-02", ticker="AAPL")
    c = make_prediction_id(variant_id="R3", rebalance_date="2020-01-02", ticker="MSFT")
    assert a == b
    assert a != c


def test_append_and_dedupe(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    decisions = out_dir / "backtest_decisions.csv"
    _write_sample_decisions(decisions)
    n1 = append_predictions_from_decisions(out_dir, variant_id="R3_test", source_run_id="run1")
    n2 = append_predictions_from_decisions(out_dir, variant_id="R3_test", source_run_id="run1")
    assert n1 == 3
    assert n2 == 0
    ledger = load_ledger(out_dir)
    assert len(ledger) == 3
    assert set(ledger["status"]) == {"mature", "pending"}


def test_mature_pending(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    decisions = out_dir / "backtest_decisions.csv"
    _write_sample_decisions(decisions)
    append_predictions_from_decisions(out_dir, variant_id="R3_test")
    assert int((load_ledger(out_dir)["status"] == "pending").sum()) == 1
    # Fill target for pending row
    frame = pd.read_csv(decisions)
    frame.loc[frame["ticker"] == "AAPL", "target"] = 0.02
    frame.to_csv(decisions, index=False)
    matured = mature_pending_from_decisions(out_dir)
    assert matured == 1
    assert (load_ledger(out_dir)["status"] == "pending").sum() == 0


def test_update_and_metrics(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _write_sample_decisions(out_dir / "backtest_decisions.csv")
    summary = update_prediction_outcomes(out_dir, variant_id="R3_test", source_run_id="run1")
    metrics = summary["metrics"]
    assert metrics["n_total"] == 3
    assert metrics["n_mature"] == 2
    assert "ic_pearson" in metrics
    assert (out_dir / "feedback_report.txt").is_file()


def test_sync_idempotent(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    _write_sample_decisions(out_dir / "backtest_decisions.csv")
    sync_outcome_ledger_from_out_dir(out_dir, run_id="r1", variant_id="R3")
    sync_outcome_ledger_from_out_dir(out_dir, run_id="r1", variant_id="R3")
    assert len(load_ledger(out_dir)) == 3
