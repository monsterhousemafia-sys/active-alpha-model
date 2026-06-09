"""Tests for aa_multiple_testing_adjustment (V2R)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from aa_multiple_testing_adjustment import (
    DSR_REQUIRED_PROBABILITY,
    build_multiple_testing_status,
    deflated_sharpe_ratio,
    export_multiple_testing_status,
)


def test_missing_variant_count_blocks_positive_interpretation(tmp_path: Path):
    status = build_multiple_testing_status(tmp_path)
    assert status["MULTIPLE_TESTING_EVIDENCE"]["pass"] is False
    assert status["MULTIPLE_TESTING_EVIDENCE"]["status"] == "NOT_EVALUABLE"


def test_pbo_not_evaluable_without_matrix(tmp_path: Path):
    status = build_multiple_testing_status(tmp_path)
    assert status["PBO_STATUS"] == "NOT_EVALUABLE"
    assert status["PBO_BLOCKER"] == "INSUFFICIENT_CANDIDATE_MATRIX_FOR_PBO"


def test_periodic_sharpe_used_not_annualized():
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(0.0005, 0.01, 500))
    dsr = deflated_sharpe_ratio(returns, n_trials=10)
    assert dsr["status"] in {"PASS", "FAIL"}
    assert "periodic_sharpe" in dsr
    assert "annualized_sharpe_display_only" in dsr
    periodic = dsr["periodic_sharpe"]
    annualized = dsr["annualized_sharpe_display_only"]
    assert abs(annualized - periodic * np.sqrt(252)) < 1e-9
    assert dsr["observation_frequency"] == "daily"
    assert dsr["observations_T"] == 500


def test_insufficient_observations_rejected():
    returns = pd.Series([0.05])
    dsr = deflated_sharpe_ratio(returns, n_trials=10)
    assert dsr["status"] == "NOT_EVALUABLE"


def test_dsr_probability_in_unit_interval():
    rng = np.random.default_rng(7)
    returns = pd.Series(rng.normal(0.0003, 0.01, 400))
    dsr = deflated_sharpe_ratio(returns, n_trials=5)
    prob = dsr.get("dsr_probability")
    assert prob is not None
    assert 0.0 <= float(prob) <= 1.0


def test_dsr_below_required_confidence_fails():
    rng = np.random.default_rng(1)
    returns = pd.Series(rng.normal(0.00001, 0.01, 400))
    dsr = deflated_sharpe_ratio(returns, n_trials=200)
    assert dsr["status"] == "FAIL"
    assert dsr["blocker"] == "DSR_BELOW_REQUIRED_CONFIDENCE"
    assert float(dsr["dsr_probability"]) < DSR_REQUIRED_PROBABILITY


def test_synthetic_dsr_reproducible():
    rng = np.random.default_rng(42)
    returns = pd.Series(rng.normal(0.0005, 0.01, 500))
    dsr = deflated_sharpe_ratio(returns, n_trials=10)
    dsr2 = deflated_sharpe_ratio(returns, n_trials=10)
    assert dsr["dsr_probability"] == dsr2["dsr_probability"]


def test_not_evaluable_does_not_imply_stage_increase(tmp_path: Path):
    status = build_multiple_testing_status(tmp_path)
    assert status["MULTIPLE_TESTING_EVIDENCE"]["status"] == "NOT_EVALUABLE"


def test_export_leaves_protected_files(tmp_path: Path):
    (tmp_path / "control").mkdir()
    (tmp_path / "promotion_gate_config.yaml").write_text("auto_research_enabled: false\n", encoding="utf-8")
    before = (tmp_path / "promotion_gate_config.yaml").read_text(encoding="utf-8")
    export_multiple_testing_status(tmp_path)
    after = (tmp_path / "promotion_gate_config.yaml").read_text(encoding="utf-8")
    assert before == after
