from __future__ import annotations

from pathlib import Path

from analytics.prediction_self_calibration import build_prediction_self_calibration


def test_self_calibration_reports_hit_rate_and_honesty(tmp_path: Path):
    ctrl = tmp_path / "control"
    ctrl.mkdir(parents=True)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    out = tmp_path / "model_output_sp500_pit_t212"
    out.mkdir(parents=True)

    (ctrl / "prediction_readiness.json").write_text(
        '{"ok": true, "signal_date": "2026-06-12", "h1_evaluation": {"metrics_strategy": {"daily_hit_rate": 0.547, "sharpe_0rf": 0.78}}}',
        encoding="utf-8",
    )
    (ctrl / "h1_governance_status.json").write_text(
        '{"status": "COMPLETE", "metrics_strategy": {"daily_hit_rate": 0.547}}',
        encoding="utf-8",
    )
    (out / "r3_daily_diagnosis.json").write_text(
        '{"regime_match": true, "signal_date": "2026-06-12", "feedback_by_regime": {"n_mature": 100, "risk_on": {"signed_hit_rate": 0.51}}}',
        encoding="utf-8",
    )
    (evidence / "r3_daily_postmortem_latest.json").write_text(
        '{"ok": true, "delta_vs_benchmark_pct": 1.2, "headline_de": "Plan +1.2% vs SPY"}',
        encoding="utf-8",
    )
    (evidence / "price_crosscheck_latest.json").write_text(
        '{"verdict": "warn", "spy_status": "pass", "counts": {"stale_primary": 2}}',
        encoding="utf-8",
    )

    doc = build_prediction_self_calibration(tmp_path)
    assert doc["metrics"]["h1_daily_hit_rate"] == 0.547
    assert "nicht immer richtig" in (doc["claims_vs_facts"][0].get("claim_de") or "")
    assert doc["metrics"]["regime_match"] is True
    assert doc["integrity_checks"]
