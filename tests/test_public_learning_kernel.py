"""Public learning kernel — quality score and report."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.public_learning_kernel import (
    compute_quality_score,
    learning_summary_for_dashboard,
    run_daily_learning,
)


def test_quality_score_and_report(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "market_data/live_learning").mkdir(parents=True, exist_ok=True)

    (tmp_path / "control/public_learning_principles.json").write_text(
        json.dumps(
            {
                "quality_floors": {
                    "ic_pearson": 0.02,
                    "signed_hit_rate": 0.52,
                    "min_live_mature_for_calibration": 3,
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/learning_collection_policy.json").write_text(
        json.dumps(
            {
                "auto_model_training_enabled": False,
                "auto_champion_update_enabled": False,
                "auto_execute_real_money_enabled": False,
                "observation_collection_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/AI_KERNEL.json").write_text(
        json.dumps({"safety": {"auto_execute_real_money": False}}),
        encoding="utf-8",
    )

    q = compute_quality_score(
        capture={"learning_healthy": True, "intraday_observations": 10, "learning_collection_active": True},
        backtest={"ic_pearson": 0.025, "signed_hit_rate": 0.53},
        live={"n_mature": 2},
        governance={"ok": True},
        principles=json.loads((tmp_path / "control/public_learning_principles.json").read_text()),
        trends={},
    )
    assert q["total"] >= 70
    assert q["grade"] in ("A", "B", "C")

    report = run_daily_learning(tmp_path, sync_outcomes=False, run_audit=False)
    assert report.get("quality_score")
    assert (tmp_path / "evidence/public_learning_report_latest.json").is_file()
    dash = learning_summary_for_dashboard(report)
    assert "grade" in dash


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        test_quality_score_and_report(Path(td))
    print("OK")
