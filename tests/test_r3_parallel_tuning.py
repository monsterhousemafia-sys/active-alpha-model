from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from run_r3_parallel_tuning import (  # noqa: E402
    R3_START,
    R3_TUNING_VARIANTS,
    TuneResult,
    _score_result,
    build_r3_command,
)


def test_r3_period_matches_champion():
    assert R3_START == "2012-01-01"
    champ = next(v for v in R3_TUNING_VARIANTS if v["name"] == "R3_champion_w075_q065")
    assert champ["weight"] == "0.75"
    assert champ["quantile"] == "0.65"


def test_build_r3_command_has_strict_repro():
    cmd = build_r3_command(
        R3_TUNING_VARIANTS[0],
        shared_cache=__import__("pathlib").Path("cache"),
        cpu_cores=5,
        price_source="fictive",
    )
    joined = " ".join(cmd)
    assert "--start 2012-01-01" in joined
    assert "--reproducibility-mode strict" in joined
    assert "--risk-off-momentum-weight 0.75" in joined
    assert "--risk-off-momentum-rescue-quantile 0.65" in joined


def test_score_prefers_pass():
    good = TuneResult(name="a", returncode=0, out_dir="", sharpe=0.9, cagr=12.0, max_drawdown=-15.0, integrity="PASS")
    bad = TuneResult(name="b", returncode=1, out_dir="", integrity="FAIL")
    assert _score_result(good) > _score_result(bad)
