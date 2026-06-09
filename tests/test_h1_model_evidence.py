"""H1 model evidence — COMPLETE without fabricated seal."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_h1_model_evidence_complete_seal_optional() -> None:
    from analytics.live_profile_governance import h1_model_evidence

    ev = h1_model_evidence(ROOT)
    assert ev["h1_status"] == "COMPLETE"
    assert ev.get("run_dir")
    assert ev["operational_ok"] is True
    assert ev["pass_full_seal"] is False
    assert ev["seal_required"] is False
    metrics = ev.get("metrics_strategy") or {}
    assert metrics.get("sharpe_0rf") is not None


def test_sync_readiness_includes_h1_evaluation(tmp_path: Path) -> None:
    from analytics.live_profile_governance import sync_readiness_with_order_gate

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/h1_seal_policy.json").write_text(
        json.dumps({"seal_required": False, "benchmark_required_for_operations": False}),
        encoding="utf-8",
    )
    run = tmp_path / "validation_runs/20260606T102626Z_DAILY_ALPHA_H1"
    run.mkdir(parents=True)
    (run / "strategy_daily_returns.csv").write_text("date,ret\n2020-01-01,0.01\n", encoding="utf-8")
    (tmp_path / "evidence/daily_alpha_h1_evaluation_latest.json").write_text(
        json.dumps(
            {
                "pass_full_seal": False,
                "evaluated_at_utc": "2026-06-08T15:34:29+00:00",
                "metrics_strategy": {"sharpe_0rf": 0.782, "cagr": 0.14, "n_days": 1866},
                "run_dir": "validation_runs/20260606T102626Z_DAILY_ALPHA_H1",
            }
        ),
        encoding="utf-8",
    )
    payload = {
        "ok": True,
        "profile_used": "daily_alpha_h1",
        "top_picks": [{"ticker": "INTC", "target_weight": 0.5}],
        "signal_date": "2026-06-05",
    }
    synced = sync_readiness_with_order_gate(tmp_path, payload)
    assert synced.get("h1_operational_ok") is True
    assert synced.get("h1_backtest_status", {}).get("status") == "COMPLETE"
    assert synced.get("h1_evaluation", {}).get("pass_full_seal") is False
    assert synced.get("h1_evaluation", {}).get("metrics_strategy", {}).get("sharpe_0rf") == 0.782


def test_governance_sync_complete_operational_ok(tmp_path: Path, monkeypatch) -> None:
    from analytics.h1_governance_status import sync_h1_governance_status

    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "control/h1_seal_policy.json").write_text(
        json.dumps({"seal_required": False}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "profile_used": "daily_alpha_h1"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_backtest_status",
        lambda r: {"status": "COMPLETE", "run_dir": "validation_runs/x"},
    )
    monkeypatch.setattr("analytics.live_profile_governance.is_h1_backtest_sealed", lambda r: False)
    monkeypatch.setattr(
        "analytics.live_profile_governance.h1_model_evidence",
        lambda r: {
            "h1_status": "COMPLETE",
            "run_dir": "validation_runs/x",
            "sealed": False,
            "pass_full_seal": False,
            "seal_required": False,
            "seal_policy_de": "Seal optional",
            "operational_ok": True,
            "metrics_strategy": {"sharpe_0rf": 0.78},
            "evaluated_at_utc": "2026-06-08T00:00:00+00:00",
            "message_de": "H1 COMPLETE",
            "detail_de": None,
        },
    )
    doc = sync_h1_governance_status(tmp_path, write_readiness=True)
    assert doc.get("operational_ok") is True
    assert doc.get("gate_blockers") == []
    readiness = json.loads((tmp_path / "control/prediction_readiness.json").read_text(encoding="utf-8"))
    assert readiness.get("h1_operational_ok") is True
    assert readiness.get("h1_evaluation", {}).get("pass_full_seal") is False
