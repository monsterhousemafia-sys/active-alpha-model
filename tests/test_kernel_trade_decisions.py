"""Kernel — Quant → König 32B → R3 Entscheidungskette."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.kernel_trade_decisions import (
    ensure_kernel_trade_decisions,
    merge_king_decisions,
    pass_through_decisions,
    resolve_executable_trade_decisions,
    write_king_advisory_evidence,
)
from analytics.r3_stock_orders import build_optimal_stock_actions


def _write_kernel_context(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "blockers": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/gas_sell_steering_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evidence/gas_sell_steering_latest.json").write_text(
        json.dumps({"on_course": True}),
        encoding="utf-8",
    )


def _write_reeval(tmp_path: Path) -> None:
    doc = {
        "human_snapshot": {"positions_count": 0, "cash_weight_pct": 100.0},
        "recommended_actions": [
            {
                "symbol": "STX",
                "action_code": "KAUFEN",
                "gap_eur": 48.0,
                "priority_score": 9.0,
                "live_price_eur": 85.0,
            },
            {
                "symbol": "AMD",
                "action_code": "KAUFEN",
                "gap_eur": 40.0,
                "priority_score": 7.0,
                "live_price_eur": 120.0,
            },
        ],
    }
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(doc),
        encoding="utf-8",
    )


def test_pass_through_all_quant(tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    from analytics.r3_stock_orders import _build_quant_stock_actions

    quant = _build_quant_stock_actions(tmp_path)
    out = pass_through_decisions(quant)
    assert len(out) == 2
    assert all(r.get("sanctioned") for r in out)
    assert out[0]["decision_source"] == "quant_pass_through"


def test_merge_king_filters(tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    from analytics.r3_stock_orders import _build_quant_stock_actions

    quant = _build_quant_stock_actions(tmp_path)
    king = [
        {"symbol": "STX", "side": "BUY", "sanctioned": True, "reason_de": "Top-Pick"},
        {"symbol": "AMD", "side": "BUY", "sanctioned": False, "reason_de": "Zu volatil"},
    ]
    out = merge_king_decisions(quant, king, agrees_with_model=True)
    assert len(out) == 1
    assert out[0]["symbol"] == "STX"
    assert out[0]["decision_source"] == "king_32b"


def test_ensure_bootstrap_when_no_king_evidence(tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "blockers": []}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_trading_cycle_latest.json").write_text(
        json.dumps({"closed": True}),
        encoding="utf-8",
    )
    (tmp_path / "control/gas_sell_steering_policy.json").write_text("{}", encoding="utf-8")
    doc = ensure_kernel_trade_decisions(tmp_path)
    assert len(doc.get("trade_decisions") or []) == 2
    assert doc.get("decision_mode") == "quant_bootstrap"
    rows = resolve_executable_trade_decisions(tmp_path)
    assert len(rows) == 2


def test_build_optimal_ignores_king_uses_plan(tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    _write_kernel_context(tmp_path)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 88.0,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 9.0},
                    {"symbol": "AMD", "side": "BUY", "target_eur": 40.0, "model_weight_pct": 7.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {
                        "symbol": "STX",
                        "side": "BUY",
                        "notional_eur": 48.0,
                        "priority_score": 9.0,
                        "sanctioned": True,
                        "clickable": True,
                    },
                    {
                        "symbol": "AMD",
                        "side": "BUY",
                        "sanctioned": False,
                        "clickable": True,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    rows = build_optimal_stock_actions(tmp_path)
    assert len(rows) == 2
    assert {r["symbol"] for r in rows} == {"STX", "AMD"}
    assert all(r.get("decision_source") == "pilot_investment_plan" for r in rows)


def test_resolve_drops_king_only_unknown_symbols(tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    _write_kernel_context(tmp_path)
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {"symbol": "FAKE", "side": "BUY", "sanctioned": True, "clickable": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    ensure_kernel_trade_decisions(tmp_path)
    rows = resolve_executable_trade_decisions(tmp_path)
    syms = {r["symbol"] for r in rows}
    assert "FAKE" not in syms
    assert syms == {"STX", "AMD"}


@patch("analytics.local_llm_bridge.ollama_available", return_value=False)
def test_offline_king_writes_pass_through(mock_ollama, tmp_path: Path) -> None:
    _write_reeval(tmp_path)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 88.0,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 9.0},
                    {"symbol": "AMD", "side": "BUY", "target_eur": 40.0, "model_weight_pct": 7.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "control").mkdir(exist_ok=True)
    (tmp_path / "control/king_trading_assist_policy.json").write_text(
        json.dumps({"enabled": True, "cooldown_min": 0}),
        encoding="utf-8",
    )
    from analytics.king_trading_assist import run_king_trading_assist

    out = run_king_trading_assist(tmp_path, force=True)
    assert out.get("executable_count") == 0
    doc = json.loads((tmp_path / "evidence/king_trading_assist_latest.json").read_text(encoding="utf-8"))
    assert doc.get("decision_mode") == "king_offline_advisory"
    assert doc.get("advisory_only") is True
    assert doc.get("trade_decisions") == []
    assert doc.get("buy_count") == 2


def test_king_advisory_buy_count_matches_plan(tmp_path: Path) -> None:
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 50.0},
                    {"symbol": "AMD", "side": "BUY", "target_eur": 40.0},
                    {"symbol": "MU", "side": "BUY", "target_eur": 0.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    doc = write_king_advisory_evidence(
        tmp_path,
        follow_on_suggestions=[{"symbol": "STX", "worth_follow_on": True}],
        decision_mode="test",
        patch={"buy_count": 99},
    )
    assert doc["buy_count"] == 3
    assert doc["plan_executable_buy_count"] == 2
