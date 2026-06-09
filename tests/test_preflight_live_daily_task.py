"""Preflight checklist for scheduled live daily mark (Step B)."""
from __future__ import annotations

import json
from pathlib import Path


def _write_policy(root: Path) -> None:
    (root / "control").mkdir(parents=True)
    (root / "control/pilot_day_trading.json").write_text(
        json.dumps(
            {
                "live_trading": {
                    "enabled": True,
                    "rebalance_every_trading_days": 1,
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "control/learning_collection_policy.json").write_text(
        json.dumps({"auto_execute_real_money_enabled": False}),
        encoding="utf-8",
    )


def test_scheduled_enqueue_only_required(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    (tmp_path / "active_alpha_model.py").write_text("# stub\n", encoding="utf-8")
    import pandas as pd

    (tmp_path / "model_output_sp500_pit_t212").mkdir(parents=True)
    pd.DataFrame([{"ticker": "INTC", "target_weight": 0.1, "signal_date": "2020-01-01"}]).to_csv(
        tmp_path / "model_output_sp500_pit_t212/latest_target_portfolio.csv", index=False
    )
    (tmp_path / "control/live_trading_daily_task_checklist.json").write_text(
        (Path(__file__).resolve().parents[1] / "control/live_trading_daily_task_checklist.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )

    from tools.preflight_live_daily_task import evaluate_live_daily_task_preflight

    r = evaluate_live_daily_task_preflight(tmp_path, scheduled=False)
    assert not r["ok"]
    assert any("safety_enqueue_only" in b for b in r["blockers"])

    r2 = evaluate_live_daily_task_preflight(tmp_path, scheduled=True)
    assert any(i["id"] == "safety_enqueue_only" and i["ok"] for i in r2["items"])


def test_rebalance_daily_check(tmp_path: Path) -> None:
    _write_policy(tmp_path)
    from tools.preflight_live_daily_task import _check_rebalance_daily

    assert _check_rebalance_daily(tmp_path)["ok"] is True


def test_human_report_format(tmp_path: Path) -> None:
    from tools.live_daily_task_ui import format_preflight_report

    text = format_preflight_report(
        {
            "ok": True,
            "message_de": "OK",
            "items": [{"id": "a", "label": "Test", "required": True, "ok": True, "detail_de": ""}],
            "blockers": [],
        }
    )
    assert "Systemcheck" in text
    assert "[OK]" in text
