"""R3 — klickbare Aktien + Initial-Gesamtpaket."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from analytics.r3_stock_orders import (
    build_initial_package,
    build_optimal_stock_actions,
    build_stock_groups,
    handle_r3_order_request,
    refresh_stock_order_evidence,
)


def _write_reeval(tmp_path: Path, *, positions: int = 0, buys: bool = True, sells: bool = False) -> None:
    actions = []
    if buys:
        actions.append(
            {
                "symbol": "STX",
                "action_code": "KAUFEN",
                "action_de": "Nachkauf STX",
                "gap_eur": 48.0,
                "priority_score": 9.5,
                "live_price_eur": 85.0,
            }
        )
        actions.append(
            {
                "symbol": "SPY",
                "action_code": "NACHKAUF",
                "action_de": "Nachkauf SPY",
                "gap_eur": 55.0,
                "priority_score": 8.0,
                "live_price_eur": 420.0,
            }
        )
    if sells:
        actions.append(
            {
                "symbol": "INTC",
                "action_code": "REDUZIEREN",
                "action_de": "Verkauf INTC",
                "gap_eur": -30.0,
                "priority_score": 7.0,
                "live_price_eur": 22.0,
            }
        )
    doc = {
        "human_snapshot": {"positions_count": positions, "cash_weight_pct": 100.0 if positions == 0 else 20.0},
        "exposure_check": {"under_invested": positions == 0, "cash_weight_pct": 100.0 if positions == 0 else 20.0},
        "deployable_eur": 500.0,
        "recommended_actions": actions,
    }
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(doc),
        encoding="utf-8",
    )


def _write_flat_context(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    _write_reeval(tmp_path, positions=0, buys=True, sells=False)
    reeval = json.loads(
        (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").read_text(encoding="utf-8")
    )
    allocations = []
    for action in reeval.get("recommended_actions") or []:
        gap = float(action.get("gap_eur") or 0)
        if gap >= 12.0:
            allocations.append(
                {
                    "symbol": action["symbol"],
                    "side": "BUY",
                    "target_eur": round(gap, 2),
                    "model_weight_pct": float(action.get("priority_score") or 1.0),
                }
            )
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 500.0, "allocations": allocations}),
        encoding="utf-8",
    )


def test_build_optimal_stock_actions_sorted(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    rows = build_optimal_stock_actions(tmp_path)
    assert len(rows) == 2
    assert rows[0]["symbol"] == "STX"
    assert rows[0]["side"] == "BUY"
    assert rows[0]["clickable"] is True
    assert all(r.get("decision_source") == "pilot_investment_plan" for r in rows)


def test_build_optimal_empty_without_plan_allocations(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 500.0, "allocations": []}),
        encoding="utf-8",
    )
    assert build_optimal_stock_actions(tmp_path) == []


def test_initial_package_active_when_flat(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    pkg = build_initial_package(tmp_path)
    assert pkg["active"] is True
    assert pkg["order_count"] == 2
    assert float(pkg["notional_eur"]) > 0


def test_initial_package_scales_to_t212_bond(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps(
            {
                "bonded": True,
                "connected": True,
                "cash_eur": 674.66,
                "investable_eur": 640.93,
                "cash_breakdown": {
                    "available_to_trade_eur": 674.66,
                    "planning_cash_eur": 674.66,
                },
                "positions_count": 0,
            }
        ),
        encoding="utf-8",
    )
    pkg = build_initial_package(tmp_path)
    assert pkg["budget_eur"] == 640.93
    assert abs(float(pkg["notional_eur"]) - 640.93) < 2.0
    rows = build_optimal_stock_actions(tmp_path)
    buy_sum = sum(float(r["notional_eur"]) for r in rows if r["side"] == "BUY")
    assert abs(buy_sum - 640.93) < 2.0


def test_initial_package_uses_plan_split_not_single_king_row(tmp_path: Path) -> None:
    """König darf Initial-Paket nicht auf einen Ticker (z. B. STX) kollabieren."""
    _write_flat_context(tmp_path)
    plan_allocations = [
        {"symbol": "MU", "side": "BUY", "target_eur": 53.63, "model_weight_pct": 4.64},
        {"symbol": "INTC", "side": "BUY", "target_eur": 62.31, "model_weight_pct": 5.39},
        {"symbol": "STX", "side": "BUY", "target_eur": 69.7, "model_weight_pct": 6.0},
        {"symbol": "AMD", "side": "BUY", "target_eur": 64.96, "model_weight_pct": 5.6},
    ]
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 640.93, "allocations": plan_allocations}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True, "investable_eur": 640.93, "cash_eur": 674.66}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {"symbol": "STX", "side": "BUY", "sanctioned": True, "notional_eur": 72.3},
                ],
                "executable_count": 1,
            }
        ),
        encoding="utf-8",
    )
    rows = build_optimal_stock_actions(tmp_path)
    symbols = {r["symbol"] for r in rows if r["side"] == "BUY"}
    assert len(symbols) >= 4
    assert "STX" in symbols
    assert "MU" in symbols
    stx = next(r for r in rows if r["symbol"] == "STX")
    assert float(stx["notional_eur"]) < 200.0
    buy_sum = sum(float(r["notional_eur"]) for r in rows if r["side"] == "BUY")
    assert abs(buy_sum - 640.93) < 2.0
    pkg = build_initial_package(tmp_path)
    assert pkg["order_count"] >= 4


def test_never_all_in_single_stock_even_with_king_only(tmp_path: Path) -> None:
    """König-Einzelauswahl wird ignoriert — Ausführung folgt Modell-Plan-Split."""
    _write_flat_context(tmp_path)
    (tmp_path / "evidence/r3_t212_api_bond_latest.json").write_text(
        json.dumps({"bonded": True, "connected": True, "investable_eur": 640.93, "cash_eur": 674.66}),
        encoding="utf-8",
    )
    (tmp_path / "evidence/king_trading_assist_latest.json").write_text(
        json.dumps(
            {
                "trade_decisions": [
                    {"symbol": "STX", "side": "BUY", "sanctioned": True, "notional_eur": 72.3},
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = build_optimal_stock_actions(tmp_path)
    buys = [r for r in rows if r["side"] == "BUY"]
    assert len(buys) >= 2
    max_notional = max(float(r["notional_eur"]) for r in buys)
    assert max_notional < 640.93 * 0.9
    assert max_notional < 500.0


def test_render_includes_clickable_buttons(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    from analytics.r3_trading_functions import build_r3_trading_functions, render_r3_trading_functions_html

    build_r3_trading_functions(tmp_path, persist=True)
    html_out = render_r3_trading_functions_html(tmp_path)
    assert "r3-stock-btn" in html_out
    assert "r3OrderStock" in html_out
    assert "T212" in html_out
    assert "r3FreigabeSubmit" in html_out


def test_handle_single_requires_confirm(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    out = handle_r3_order_request(tmp_path, {"mode": "single", "symbol": "STX", "side": "BUY"})
    assert out["ok"] is False
    assert out["error"] == "CONFIRMATION_REQUIRED"


@patch("analytics.r3_stock_orders.submit_r3_single_stock")
def test_handle_single_delegates(mock_submit, tmp_path: Path) -> None:
    mock_submit.return_value = {"ok": True, "mode": "single", "message_de": "OK"}
    out = handle_r3_order_request(
        tmp_path,
        {"mode": "single", "symbol": "STX", "side": "BUY", "confirm": True},
    )
    mock_submit.assert_called_once()
    assert out["ok"] is True


@patch("analytics.r3_stock_orders.submit_r3_initial_package")
def test_handle_initial_package_delegates(mock_submit, tmp_path: Path) -> None:
    mock_submit.return_value = {"ok": True, "mode": "initial_package", "message_de": "Paket OK"}
    out = handle_r3_order_request(tmp_path, {"mode": "initial_package", "confirm": True})
    mock_submit.assert_called_once()
    assert out["ok"] is True


def test_refresh_stock_order_evidence(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    doc = refresh_stock_order_evidence(tmp_path)
    assert doc["buy_count"] == 2
    assert (tmp_path / "evidence/r3_stock_orders_latest.json").is_file()


def _write_sell_rotation_context(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    doc = {
        "human_snapshot": {
            "positions_count": 2,
            "cash_weight_pct": 15.0,
            "holdings": [
                {"symbol": "INTC", "value_eur": 120.0},
                {"symbol": "SPY", "value_eur": 200.0},
            ],
        },
        "exposure_check": {"under_invested": False, "cash_weight_pct": 15.0},
        "deployable_eur": 80.0,
        "allocation_drift_l1_pct": 6.0,
        "recommended_actions": [
            {
                "symbol": "INTC",
                "action_code": "REDUZIEREN",
                "action_de": "INTC abbauen",
                "gap_eur": -30.0,
                "priority_score": 9.0,
                "live_price_eur": 22.0,
            },
            {
                "symbol": "STX",
                "action_code": "NACHKAUF",
                "action_de": "STX neu ins Portfolio",
                "gap_eur": 48.0,
                "priority_score": 8.5,
                "live_price_eur": 85.0,
            },
            {
                "symbol": "SPY",
                "action_code": "NACHKAUF",
                "action_de": "SPY aufstocken",
                "gap_eur": 20.0,
                "priority_score": 5.0,
                "live_price_eur": 420.0,
            },
        ],
    }
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(doc),
        encoding="utf-8",
    )


def test_stock_groups_split_sell_and_new_buys(tmp_path: Path) -> None:
    _write_sell_rotation_context(tmp_path)
    plan = {
        "investable_eur": 200.0,
        "allocations": [
            {"symbol": "INTC", "side": "SELL", "target_eur": 30.0, "model_weight_pct": 5.0},
            {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 8.5},
            {"symbol": "SPY", "side": "BUY", "target_eur": 20.0, "model_weight_pct": 5.0},
        ],
    }
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    groups = build_stock_groups(tmp_path)
    assert groups["sell_count"] == 1
    assert groups["new_buy_count"] == 1
    assert groups["sells"][0]["symbol"] == "INTC"
    assert groups["sells"][0]["decision_source"] == "pilot_investment_plan"
    assert groups["new_buys"][0]["symbol"] == "STX"
    assert groups["new_buys"][0]["is_new_position"] is True
    assert groups["rebuy"][0]["symbol"] == "SPY"


def test_merge_reeval_sell_when_plan_buy_only(tmp_path: Path) -> None:
    """Verkauf aus Reevaluation auch wenn Plan nur Käufe hat (gehaltene Position)."""
    _write_sell_rotation_context(tmp_path)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 200.0,
                "allocations": [
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 8.5},
                    {"symbol": "SPY", "side": "BUY", "target_eur": 20.0, "model_weight_pct": 5.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = build_optimal_stock_actions(tmp_path)
    sells = [r for r in rows if r.get("side") == "SELL"]
    assert len(sells) == 1
    assert sells[0]["symbol"] == "INTC"
    assert sells[0].get("optimum_ref") == "evidence/pilot_portfolio_reevaluation_latest.json"


def test_render_sell_and_buy_sections_always(tmp_path: Path) -> None:
    _write_flat_context(tmp_path)
    from analytics.r3_trading_functions import render_r3_trading_functions_html

    html_out = render_r3_trading_functions_html(tmp_path)
    assert "r3-stocks-sell" in html_out
    assert "r3-stocks-buy" in html_out
    assert "Verkauf" in html_out
    assert "Kauf" in html_out


def test_render_sell_shows_new_stocks_section(tmp_path: Path) -> None:
    _write_sell_rotation_context(tmp_path)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps(
            {
                "investable_eur": 200.0,
                "allocations": [
                    {"symbol": "INTC", "side": "SELL", "target_eur": 30.0, "model_weight_pct": 5.0},
                    {"symbol": "STX", "side": "BUY", "target_eur": 48.0, "model_weight_pct": 8.5},
                    {"symbol": "SPY", "side": "BUY", "target_eur": 20.0, "model_weight_pct": 5.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    from analytics.r3_trading_functions import build_r3_trading_functions, render_r3_trading_functions_html

    build_r3_trading_functions(tmp_path, persist=True)
    html_out = render_r3_trading_functions_html(tmp_path)
    assert "r3-stock-side" in html_out
    assert "r3-stocks-sell" in html_out
    assert "STX" in html_out
    assert "INTC" in html_out
    assert "r3-stocks-buy" in html_out
