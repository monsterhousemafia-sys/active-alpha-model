"""Seal-artifact resolution: naive_mom_1 vs SPY benchmark_daily_returns."""
from __future__ import annotations

from pathlib import Path

import pytest

from aa_backtest import expected_naive_detailed_paths, verify_naive_detailed_artifacts
from aa_config import BacktestConfig


def test_expected_naive_detailed_paths_mom_1_top12(tmp_path: Path) -> None:
    cfg = BacktestConfig(
        naive_detailed_reporting=True,
        naive_detailed_variants="mom_1_top12",
        out_dir=str(tmp_path),
    )
    paths = expected_naive_detailed_paths(cfg, tmp_path)
    assert len(paths) == 1
    assert paths[0].name == "naive_mom_1_daily_returns.csv"


def test_verify_naive_detailed_artifacts_rejects_spy_only(tmp_path: Path) -> None:
    cfg = BacktestConfig(
        naive_detailed_reporting=True,
        naive_detailed_variants="mom_1_top12",
        out_dir=str(tmp_path),
    )
    (tmp_path / "benchmark_daily_returns.csv").write_text("date,benchmark_return\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="naive_mom_1_daily_returns.csv"):
        verify_naive_detailed_artifacts(cfg, tmp_path)


def test_verify_naive_detailed_artifacts_passes_with_seal_csv(tmp_path: Path) -> None:
    cfg = BacktestConfig(
        naive_detailed_reporting=True,
        naive_detailed_variants="mom_1_top12",
        out_dir=str(tmp_path),
    )
    seal = tmp_path / "naive_mom_1_daily_returns.csv"
    seal.write_text("date,return\n2016-01-01,0.001\n", encoding="utf-8")
    found = verify_naive_detailed_artifacts(cfg, tmp_path)
    assert found == [seal]
