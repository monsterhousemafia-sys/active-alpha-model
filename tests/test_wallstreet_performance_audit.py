"""Wall Street audit smoke tests."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.wallstreet_performance_audit import run_wallstreet_audit


def test_wallstreet_audit_produces_verdict(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r0_migration").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "market_data/live_learning").mkdir(parents=True, exist_ok=True)

    canonical = {
        "headline": {"primary_sharpe_leader": "MOM_63_TOP12", "champion_is_sharpe_leader": False},
        "cost_stress": {
            "gate": {"pass": True, "detail": "ok"},
            "scenarios": {
                "PLUS_25_BPS": [
                    {
                        "variant_id": "R3_w075_q065_noexit",
                        "metrics": {
                            "sharpe_0rf": 0.95,
                            "max_drawdown": -0.27,
                            "cagr": 0.17,
                            "annual_vol": 0.2,
                            "daily_hit_rate": 0.55,
                            "n_days": 1000,
                        },
                    },
                    {
                        "variant_id": "MOM_63_TOP12",
                        "metrics": {
                            "sharpe_0rf": 0.88,
                            "max_drawdown": -0.28,
                            "cagr": 0.15,
                            "annual_vol": 0.21,
                            "daily_hit_rate": 0.53,
                            "n_days": 1000,
                        },
                    },
                ]
            },
        },
    }
    (tmp_path / "evidence/canonical_model_comparison.json").write_text(
        json.dumps(canonical), encoding="utf-8"
    )
    (tmp_path / "control/evidence/cost_stress_status.json").write_text(
        json.dumps({"COST_STRESS_GATE": {"pass": True}}), encoding="utf-8"
    )
    (tmp_path / "evidence/learning_cycle_audit_latest.json").write_text(
        json.dumps(
            {
                "backtest_metrics": {"n_mature": 100, "ic_pearson": 0.02, "signed_hit_rate": 0.51},
                "live_metrics": {"n_mature": 0},
                "stage": {"stage_id": "sportwagen"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/competition_readiness_latest.json").write_text(
        json.dumps(
            {
                "ready_for_live_session": False,
                "blockers": ["TEST_BLOCKER"],
                "h1_backtest": {"status": "FAILED"},
                "signal_date": "2026-06-05",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control/learning_collection_policy.json").write_text(
        json.dumps({"intraday_quote_capture_enabled": True, "auto_model_training_enabled": False}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"signal_date": "2026-06-05", "price_latest": "2026-06-05"}),
        encoding="utf-8",
    )
    (tmp_path / "control/r0_migration/alpha_objective.json").write_text(
        json.dumps({"objective": {"horizon": 1, "benchmark": "1_day_momentum"}}),
        encoding="utf-8",
    )

    report = run_wallstreet_audit(tmp_path)
    assert report["verdict"] in ("NOT_INSTITUTIONAL_READY", "RESEARCH_ONLY_CHAMPION_BELOW_BENCHMARK")
    assert "performance" in report
    assert report["performance"]["champion_vs_benchmark"]["beats_benchmark_sharpe"] is True
    assert (tmp_path / "evidence/wallstreet_audit_latest.json").is_file()


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        test_wallstreet_audit_produces_verdict(Path(td))
    print("OK")
