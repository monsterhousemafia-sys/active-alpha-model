"""König 32B — Trading-Beratung für Active Alpha Model."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.king_trading_assist import (
    build_trading_context,
    run_king_trading_assist,
)


def _write_trading_evidence(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/king_trading_assist_policy.json").write_text(
        json.dumps({"enabled": True, "cooldown_min": 0}),
        encoding="utf-8",
    )
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "signal_date": "2026-06-08", "blockers": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 641.0,
                "positions": 0,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 9.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(
            {
                "human_snapshot": {"positions_count": 0, "cash_weight_pct": 100.0},
                "recommended_actions": [
                    {
                        "symbol": "STX",
                        "action_code": "KAUFEN",
                        "gap_eur": 48.0,
                        "priority_score": 9.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_functions_latest.json").write_text(
        json.dumps(
            {
                "primary_function_id": "initial_order",
                "functions": [{"id": "initial_order", "active": True, "label_de": "Initial"}],
                "context": {"investable_eur": 641.0, "positions_count": 0},
            }
        ),
        encoding="utf-8",
    )


def test_build_trading_context(tmp_path: Path) -> None:
    _write_trading_evidence(tmp_path)
    ctx = build_trading_context(tmp_path)
    assert ctx.get("prediction_ok") is True
    assert ctx.get("primary_function") == "initial_order"
    assert ctx.get("model_plan", {}).get("role_de")
    assert ctx.get("stock_summary", {}).get("new_buys")


@patch("analytics.local_llm_bridge.ollama_available", return_value=False)
def test_run_skips_when_ollama_offline(mock_avail, tmp_path: Path) -> None:
    _write_trading_evidence(tmp_path)
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "follow_on_suggestions": [
                    {"symbol": "STX", "worth_follow_on": True, "priority": 3.0, "reason_de": "Top"},
                ]
            }
        ),
        encoding="utf-8",
    )
    out = run_king_trading_assist(tmp_path, force=True)
    assert out.get("skipped") is True
    doc = json.loads((tmp_path / "evidence/king_trading_assist_latest.json").read_text())
    assert len(doc.get("follow_on_suggestions") or []) == 1
    assert doc.get("follow_on_preserved") is True


@patch("analytics.local_llm_bridge.chat_completion")
@patch("analytics.local_llm_bridge.ollama_available", return_value=True)
@patch("analytics.r3_model_synergy.resolve_ollama_role")
def test_run_advice_from_32b(mock_role, mock_avail, mock_chat, tmp_path: Path) -> None:
    _write_trading_evidence(tmp_path)
    mock_role.return_value = {
        "model": "qwen2.5-coder:32b",
        "role_de": "Trading mit Evidence-Kontext",
        "num_ctx": 8192,
    }
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 641.0,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 9.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    mock_chat.return_value = (
        json.dumps(
            {
                "summary_de": "Nach Plan: STX für Follow-on Top-up prüfen.",
                "primary_action_de": "Modell-Plan zuerst ausführen",
                "risks_de": ["US-Session"],
                "agrees_with_model": True,
                "focus_symbols": ["STX"],
                "operator_hint_de": "Erst Gesamtpaket, dann Nachkauf erwägen",
                "follow_on_suggestions": [
                    {
                        "symbol": "STX",
                        "worth_follow_on": True,
                        "reason_de": "Stärkstes Signal nach Plan-Allokation",
                        "hint_eur": 25.0,
                        "priority": 9.0,
                    }
                ],
            }
        ),
        {},
    )
    out = run_king_trading_assist(tmp_path, force=True)
    assert out.get("ok") is True
    assert out.get("agrees_with_model") is True
    assert out.get("executable_count") == 0
    assert out.get("follow_on_count") == 1
    doc = json.loads((tmp_path / "evidence/king_trading_assist_latest.json").read_text(encoding="utf-8"))
    assert doc.get("advisory_only") is True
    assert doc.get("trade_decisions") == []
    assert doc["follow_on_suggestions"][0]["symbol"] == "STX"


def test_king_skips_without_plan_change(tmp_path: Path) -> None:
    _write_trading_evidence(tmp_path)
    (tmp_path / "control/king_trading_assist_policy.json").write_text(
        json.dumps({"enabled": True, "cooldown_min": 60}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_worthwhile_positions_latest.json").write_text(
        json.dumps({"worthwhile_buy_count": 0}),
        encoding="utf-8",
    )
    plan = json.loads((tmp_path / "evidence/pilot_investment_plan_latest.json").read_text())
    from analytics.king_trading_assist import _plan_fingerprint

    fp = _plan_fingerprint(plan)
    predict = json.loads((tmp_path / "control/prediction_readiness.json").read_text())
    (tmp_path / "control/king_trading_assist_state.json").write_text(
        json.dumps(
            {
                "last_run_utc": "2020-01-01T00:00:00+00:00",
                "last_plan_fingerprint": fp,
                "last_worthwhile_buy_count": 0,
                "last_signal_at_utc": predict.get("generated_at_utc"),
            }
        ),
        encoding="utf-8",
    )
    with patch(
        "analytics.king_trading_assist._king_trigger_reason",
        return_value=None,
    ):
        out = run_king_trading_assist(tmp_path, force=False)
    assert out.get("skipped") is True
    assert out.get("reason_de") == "no_plan_change"

