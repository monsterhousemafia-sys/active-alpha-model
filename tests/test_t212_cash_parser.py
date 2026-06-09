from integrations.trading212.t212_cash_parser import (
    extract_free_cash_eur,
    parse_cash_breakdown,
    verify_cash_eur_matches_summary,
)


def test_prefers_available_to_trade_from_summary() -> None:
    bd = parse_cash_breakdown(
        {"total": 999.0, "cash": 888.0},
        account_summary={
            "currency": "EUR",
            "totalValue": 492.4,
            "cash": {
                "availableToTrade": 444.13,
                "reservedForOrders": 12.0,
                "inPies": 5.0,
            },
            "investments": {"currentValue": 48.2},
        },
    )
    assert bd.available_to_trade_eur == 444.13
    assert bd.planning_cash_eur == 444.13
    assert extract_free_cash_eur(account_summary={"cash": {"availableToTrade": 444.13}}) == 444.13
    assert bd.total_account_value_eur == 492.4
    assert bd.reserved_for_orders_eur == 12.0
    assert bd.in_pies_eur == 5.0
    assert bd.source == "account_summary.cash.availableToTrade"


def test_never_uses_total_as_planning_cash() -> None:
    bd = parse_cash_breakdown(account_summary={"totalValue": 999.0, "cash": {}})
    assert bd.planning_cash_eur is None


def test_cash_alignment_check() -> None:
    summary = {"cash": {"availableToTrade": 100.0}}
    assert verify_cash_eur_matches_summary(100.0, summary)["ok"] is True
    assert verify_cash_eur_matches_summary(492.0, summary)["ok"] is False


def test_order_sizing_caps_by_free_cash() -> None:
    from execution.confirmed_live.order_sizing import size_buy_quantity

    qty, warn = size_buy_quantity(
        target_notional_eur=82.0,
        limit_price_eur=94.0,
        free_cash_eur=120.0,
        min_reserve_eur=50.0,
    )
    assert qty < 0.88
    assert warn == "ORDER_SIZE_REDUCED_TO_AVAILABLE_CASH"
