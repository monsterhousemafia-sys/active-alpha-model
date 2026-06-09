from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aa_alpha_vs_momentum import (  # noqa: E402
    AlphaMomentumThresholds,
    alpha_beats_momentum_significantly,
    compare_return_series,
    parse_report_sections,
    score_alpha_vs_momentum,
)


def test_parse_report_sections_keeps_strategy_metrics(tmp_path: Path):
    report = tmp_path / "backtest_report.txt"
    report.write_text(
        "\n".join(
            [
                "Strategy metrics",
                "----------------",
                "sharpe_0rf: 0.895607",
                "cagr: 0.187415",
                "",
                "Benchmark metrics",
                "-----------------",
                "sharpe_0rf: 0.941091",
                "cagr: 0.178591",
            ]
        ),
        encoding="utf-8",
    )
    sections = parse_report_sections(report)
    assert sections["strategy"]["sharpe_0rf"] == 0.895607
    assert sections["benchmark"]["sharpe_0rf"] == 0.941091


def test_alpha_beats_momentum_gate():
    from aa_alpha_vs_momentum import AlphaMomentumComparison

    strong = AlphaMomentumComparison(
        momentum_benchmark="NAIVE_MOMENTUM_MOM_BLEND_TOP12",
        source="test",
        n_days=500,
        strategy_cagr=0.20,
        momentum_cagr=0.15,
        cagr_diff=0.05,
        strategy_sharpe=1.0,
        momentum_sharpe=0.85,
        sharpe_diff=0.15,
        information_ratio=0.35,
        tracking_error=0.10,
        correlation=0.9,
        beta_to_momentum=0.95,
    )
    ok, reason = alpha_beats_momentum_significantly(strong, AlphaMomentumThresholds())
    assert ok is True
    assert reason == "PASS"
    assert score_alpha_vs_momentum(strong) > 0


def test_parse_backtest_report_momentum(tmp_path: Path):
    report = tmp_path / "backtest_report.txt"
    report.write_text(
        "\n".join(
            [
                "Strategy metrics",
                "----------------",
                "cagr: 0.134508",
                "sharpe_0rf: 0.578349",
                "n_days: 1860",
                "",
                "Benchmark comparison",
                "NAIVE_MOMENTUM_MOM_BLEND_TOP12: CAGR diff=0.018535, IR=0.382047, corr=0.978617, beta=1.087975",
            ]
        ),
        encoding="utf-8",
    )
    from aa_alpha_vs_momentum import parse_backtest_report_momentum

    cmp = parse_backtest_report_momentum(tmp_path)
    assert cmp is not None
    assert cmp.cagr_diff == 0.018535
    assert cmp.information_ratio == 0.382047
    assert cmp.sharpe_diff > 0


def test_compare_return_series():
    idx = pd.date_range("2020-01-01", periods=260, freq="B")
    rng = pd.Series(range(len(idx)), index=idx, dtype=float)
    strategy = pd.Series(0.0012 + 0.0003 * (rng % 7) / 7.0, index=idx)
    momentum = pd.Series(0.0006 + 0.0002 * (rng % 5) / 5.0, index=idx)
    cmp = compare_return_series(strategy, momentum)
    assert cmp is not None
    assert cmp.cagr_diff > 0
    assert cmp.sharpe_diff > 0
