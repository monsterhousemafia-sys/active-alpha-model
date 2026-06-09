from execution.confirmed_live.order_sizing import plan_executable_buy_order


def test_plan_includes_t212_cost_estimate() -> None:
    plan = plan_executable_buy_order(
        target_notional_eur=82.0,
        limit_price_eur=94.0,
        free_cash_eur=120.0,
    )
    costs = plan.get("t212_cost_estimate") or {}
    assert costs.get("estimated_fx_fee_eur", 0) > 0
    assert costs.get("all_in_notional_eur", 0) >= plan["executable_notional_eur"]
