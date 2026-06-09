"""R3 — drei Handelsfunktionen."""
from __future__ import annotations

import json
from pathlib import Path

from analytics.r3_trading_functions import (
    build_r3_trading_functions,
    evaluate_initial_order,
    evaluate_rebalance_notice,
    evaluate_sell_notice,
    load_functions_policy,
    render_r3_trading_functions_html,
)


def _write_reeval(tmp_path: Path, *, positions: int = 0, buys: bool = True, sells: bool = False) -> None:
    actions = []
    if buys:
        actions.append(
            {
                "symbol": "SPY",
                "action_code": "NACHKAUF",
                "gap_eur": 55.0,
                "weight_gap_pct": 10.0,
            }
        )
    if sells:
        actions.append(
            {
                "symbol": "INTC",
                "action_code": "REDUZIEREN",
                "gap_eur": -30.0,
                "weight_gap_pct": -5.0,
            }
        )
    doc = {
        "human_snapshot": {"positions_count": positions, "cash_weight_pct": 100.0 if positions == 0 else 20.0},
        "exposure_check": {"under_invested": positions == 0, "cash_weight_pct": 100.0 if positions == 0 else 20.0},
        "deployable_eur": 500.0,
        "allocation_drift_l1_pct": 12.0 if positions else 80.0,
        "recommended_actions": actions,
    }
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(doc), encoding="utf-8"
    )


def test_initial_order_when_flat(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 500.0}),
        encoding="utf-8",
    )
    _write_reeval(tmp_path, positions=0, buys=True, sells=False)
    policy = load_functions_policy(tmp_path)
    from analytics.r3_trading_functions import _collect_context

    ctx = _collect_context(tmp_path)
    fn = evaluate_initial_order(ctx, policy)
    assert fn["active"] is True
    assert fn["id"] == "initial_order"


def test_sell_notice(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    _write_reeval(tmp_path, positions=3, buys=False, sells=True)
    policy = load_functions_policy(tmp_path)
    from analytics.r3_trading_functions import _collect_context

    ctx = _collect_context(tmp_path)
    fn = evaluate_sell_notice(ctx, policy)
    assert fn["active"] is True
    assert fn["order_count"] == 1


def test_rebalance_when_due_with_sells_only(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    _write_reeval(tmp_path, positions=3, buys=False, sells=True)
    (tmp_path / "evidence/pilot_day_trading_snapshot_latest.json").write_text(
        json.dumps({"rebalance_status": {"is_due": True}}),
        encoding="utf-8",
    )
    policy = load_functions_policy(tmp_path)
    from analytics.r3_trading_functions import _collect_context

    ctx = _collect_context(tmp_path)
    fn = evaluate_rebalance_notice(ctx, policy)
    assert fn["active"] is True
    assert fn["rebalance_due"] is True


def test_rebalance_when_due_with_low_drift(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    doc = {
        "human_snapshot": {"positions_count": 3, "cash_weight_pct": 20.0},
        "exposure_check": {"under_invested": False, "cash_weight_pct": 20.0},
        "deployable_eur": 500.0,
        "allocation_drift_l1_pct": 1.0,
        "recommended_actions": [
            {"symbol": "SPY", "action_code": "NACHKAUF", "gap_eur": 55.0, "weight_gap_pct": 10.0},
        ],
    }
    (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").write_text(
        json.dumps(doc), encoding="utf-8"
    )
    (tmp_path / "evidence/pilot_day_trading_snapshot_latest.json").write_text(
        json.dumps({"rebalance_status": {"is_due": True}}),
        encoding="utf-8",
    )
    policy = load_functions_policy(tmp_path)
    from analytics.r3_trading_functions import _collect_context

    ctx = _collect_context(tmp_path)
    fn = evaluate_rebalance_notice(ctx, policy)
    assert fn["active"] is True


def test_rebalance_when_positions_and_drift(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    _write_reeval(tmp_path, positions=2, buys=True, sells=True)
    (tmp_path / "evidence/pilot_day_trading_snapshot_latest.json").write_text(
        json.dumps({"rebalance_status": {"is_due": True}}),
        encoding="utf-8",
    )
    policy = load_functions_policy(tmp_path)
    from analytics.r3_trading_functions import _collect_context

    ctx = _collect_context(tmp_path)
    fn = evaluate_rebalance_notice(ctx, policy)
    assert fn["active"] is True


def test_build_and_render(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True, exist_ok=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    (tmp_path / "evidence").mkdir(exist_ok=True)
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 500.0}),
        encoding="utf-8",
    )
    _write_reeval(tmp_path, positions=0)
    doc = build_r3_trading_functions(tmp_path, persist=True)
    assert len(doc.get("functions") or []) == 3
    assert (tmp_path / "evidence/r3_trading_functions_latest.json").is_file()
    html_out = render_r3_trading_functions_html(tmp_path)
    assert "r3-trading-functions" in html_out
    assert "r3-freigabe-btn" in html_out
    assert "T212" in html_out


def test_desktop_exec_only_hides_einzelaktien(tmp_path: Path) -> None:
    (tmp_path / "control").mkdir(parents=True)
    (tmp_path / "evidence").mkdir(parents=True)
    (tmp_path / "control/r3_trading_functions_policy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "control/prediction_readiness.json").write_text(
        json.dumps({"ok": True, "order_gate_ok": True}),
        encoding="utf-8",
    )
    _write_reeval(tmp_path, positions=0)
    reeval = json.loads(
        (tmp_path / "evidence/pilot_portfolio_reevaluation_latest.json").read_text(encoding="utf-8")
    )
    allocations = [
        {
            "symbol": a["symbol"],
            "side": "BUY",
            "target_eur": round(float(a.get("gap_eur") or 0), 2),
            "model_weight_pct": float(a.get("priority_score") or 1.0),
        }
        for a in (reeval.get("recommended_actions") or [])
        if float(a.get("gap_eur") or 0) >= 12.0
    ]
    (tmp_path / "evidence/pilot_investment_plan_latest.json").write_text(
        json.dumps({"investable_eur": 500.0, "allocations": allocations}),
        encoding="utf-8",
    )
    build_r3_trading_functions(tmp_path, persist=True)
    full = render_r3_trading_functions_html(tmp_path, exec_only=False)
    slim = render_r3_trading_functions_html(tmp_path, exec_only=True)
    assert 'class="r3-stock-btn' in full
    assert 'class="r3-stock-btn' not in slim
    assert 'class="r3-stock-btn' in full
    assert "r3-einzel-wrap" in full
    assert "r3-freigabe-btn" in slim
