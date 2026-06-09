from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))

from run_validation_matrix import CHALLENGER_COST_KEYS, MATRIX, _build_cmd  # noqa: E402
from run_r5_challenger_pipeline import R5_BASE, build_r5_command  # noqa: E402


def test_r5_in_validation_matrix():
    keys = {v["key"] for v in MATRIX}
    assert "R5_rank_only_train5" in keys
    assert "R5_rank_only_train5" in CHALLENGER_COST_KEYS


def test_build_cmd_r5_overrides():
    variant = next(v for v in MATRIX if v["key"] == "R5_rank_only_train5")
    cmd = _build_cmd(variant, Path("out"), fast_profile=True)
    joined = " ".join(cmd)
    assert "--alpha-model-mode rank_only" in joined
    assert "--train-years 5" in joined


def test_build_r5_internet_command():
    cmd = build_r5_command(R5_BASE, out_dir=Path("out"), cpu_cores=8, price_source="internet", full_reporting=True)
    joined = " ".join(cmd)
    assert "--alpha-model-mode rank_only" in joined
    assert "--train-years 5" in joined
    assert "--naive-momentum-variants mom_blend_top12" in joined
    assert "--minimal-backtest-reporting" not in joined


def test_matrix_base_uses_phase_matrix():
    from tools import run_r5_challenger_pipeline as mod

    stamp = "teststamp"
    cmd = [
        mod.PYTHON,
        str(mod.ROOT / "tools" / "run_validation_matrix.py"),
        "--phase",
        "matrix",
        "--variant",
        mod.R5_KEY,
        "--stamp",
        stamp,
    ]
    joined = " ".join(cmd)
    assert "--phase matrix" in joined


def test_build_r5_command_slippage_override():
    variant = {**R5_BASE, "slippage_bps": "10", "market_impact_bps": "5"}
    cmd = build_r5_command(variant, out_dir=Path("out"), cpu_cores=8, price_source="internet", full_reporting=True)
    joined = " ".join(cmd)
    assert "--slippage-bps 10" in joined
    assert "--market-impact-bps 5" in joined
