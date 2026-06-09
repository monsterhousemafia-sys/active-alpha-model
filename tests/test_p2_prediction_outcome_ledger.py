"""P2 prediction outcome ledger gate tests (master prompt §11.6)."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from aa_model_status import build_model_status, format_model_status_block
from aa_prediction_outcomes import (
    OUTCOMES_FILE,
    FEEDBACK_SUMMARY_FILE,
    LEDGER_FILE,
    append_predictions_from_decisions,
    load_ledger,
    load_outcomes,
    mature_pending_from_decisions,
    update_prediction_outcomes,
    write_outcomes_parquet,
    write_prediction_feedback_summary,
)


def _write_sample_decisions(path: Path) -> None:
    rows = [
        {
            "rebalance_date": "2020-01-02",
            "date": "2020-01-02",
            "ticker": "AAPL",
            "mu_hat": 0.02,
            "alpha_lcb": 0.01,
            "selection_score": 0.8,
            "target_weight": 0.1,
            "target_exposure": 0.65,
            "target": 0.015,
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
            "selection_score": 0.85,
            "target_weight": 0.12,
            "target_exposure": 0.65,
            "target": float("nan"),
            "risk_on": False,
            "selection_mode": "mom_blend_blend",
            "gate_mode": "momentum_rescue",
        },
    ]
    pd.DataFrame(rows).to_csv(path, index=False)


def test_p2_new_signal_immutable_append(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_sample_decisions(out / "backtest_decisions.csv")
    n = append_predictions_from_decisions(out, variant_id="R3_test", source_run_id="run1")
    assert n == 2
    ledger = load_ledger(out)
    assert ledger.at[0, "signal_id"] == ledger.at[0, "prediction_id"]
    assert ledger.at[0, "mu_hat"] == pytest.approx(0.02)
    assert (out / LEDGER_FILE).is_file()


def test_p2_immature_has_no_outcome_row(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_sample_decisions(out / "backtest_decisions.csv")
    append_predictions_from_decisions(out, variant_id="R3_test")
    outcomes = load_outcomes(out)
    pending = load_ledger(out)[load_ledger(out)["status"] == "pending"]
    assert len(pending) == 1
    if not outcomes.empty:
        assert pending.iloc[0]["prediction_id"] not in set(outcomes["prediction_id"].astype(str))


def test_p2_mature_outcome_appended_without_overwriting_prediction(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    decisions = out / "backtest_decisions.csv"
    _write_sample_decisions(decisions)
    append_predictions_from_decisions(out, variant_id="R3_test")
    before = load_ledger(out)
    pending_id = before[before["status"] == "pending"].iloc[0]["prediction_id"]
    original_mu = float(before[before["prediction_id"] == pending_id].iloc[0]["mu_hat"])
    frame = pd.read_csv(decisions)
    frame.loc[frame["rebalance_date"] == "2020-01-07", "target"] = 0.025
    frame.to_csv(decisions, index=False)
    matured = mature_pending_from_decisions(out)
    assert matured == 1
    after = load_ledger(out)
    row = after[after["prediction_id"] == pending_id].iloc[0]
    assert float(row["mu_hat"]) == pytest.approx(original_mu)
    assert row["status"] == "mature"
    write_outcomes_parquet(out)
    outcomes = load_outcomes(out)
    assert (out / OUTCOMES_FILE).is_file()
    assert pending_id in set(outcomes["prediction_id"].astype(str))
    assert outcomes[outcomes["prediction_id"] == pending_id].iloc[0]["outcome_status"] == "MATURE"


def test_p2_feedback_summary_and_model_status(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_sample_decisions(out / "backtest_decisions.csv")
    update_prediction_outcomes(out, variant_id="R3_test", source_run_id="run1")
    assert (out / FEEDBACK_SUMMARY_FILE).is_file()
    summary = json.loads((out / FEEDBACK_SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["stored_predictions"] == 2
    assert summary["mature_outcomes"] >= 1
    status = build_model_status(out)
    assert status["stored_predictions"] == 2
    text = format_model_status_block(status)
    assert "Gespeicherte Prognosen" in text
    assert "Reife ausgewertete Prognosen" in text


def test_p2_reappend_does_not_duplicate_or_mutate(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    _write_sample_decisions(out / "backtest_decisions.csv")
    append_predictions_from_decisions(out, variant_id="R3_test")
    first = load_ledger(out).copy()
    append_predictions_from_decisions(out, variant_id="R3_test")
    second = load_ledger(out)
    assert len(second) == len(first)
    pd.testing.assert_series_equal(
        second.sort_values("prediction_id")["mu_hat"].reset_index(drop=True),
        first.sort_values("prediction_id")["mu_hat"].reset_index(drop=True),
    )


def test_p2_failed_outcome_job_leaves_validated_pointer(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    (out / "latest_validated_run.json").write_text(
        '{"integrity_status":"PASS","run_id":"good","variant_id":"R3"}',
        encoding="utf-8",
    )
    _write_sample_decisions(out / "backtest_decisions.csv")
    append_predictions_from_decisions(out, variant_id="R3_test")
    pointer = json.loads((out / "latest_validated_run.json").read_text(encoding="utf-8"))
    assert pointer["run_id"] == "good"
    assert pointer["integrity_status"] == "PASS"
