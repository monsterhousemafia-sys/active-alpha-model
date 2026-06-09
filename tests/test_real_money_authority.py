"""Real-money authority tests."""
from __future__ import annotations


def test_t212_booked_totals_from_sync_snapshot() -> None:
    from ui.interactive_cockpit.services.real_money_authority import apply_real_money_state, t212_booked_totals

    broker = {
        "credentials_configured": True,
        "status": "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
        "cash_eur": 443.9,
        "positions_count": 1,
        "last_successful_sync_utc": "2026-06-01T21:31:39+00:00",
        "account_summary": {
            "currency": "EUR",
            "totalValue": 492.07,
            "cash": {"availableToTrade": 443.9},
            "investments": {"currentValue": 48.17, "realizedProfitLoss": 8.74, "unrealizedProfitLoss": 0.11},
        },
        "positions": [
            {
                "quantity": 0.3894975,
                "walletImpact": {"currentValue": 48.17, "currency": "EUR"},
            }
        ],
    }
    totals = t212_booked_totals(broker)
    assert totals["cash_eur"] == 443.9
    assert totals["invested_eur"] == 48.17
    assert totals["total_value_eur"] == 492.07
    assert totals["realized_pnl_eur"] == 8.74

    state = {"broker": broker, "cash": {}, "paper": {"virtual_paper_cash_eur": 153.7288}}
    apply_real_money_state(state)
    assert state["real_money"]["real_money_only"] is True
    assert state["paper"]["display_suppressed"] is True
    assert state["cash"]["readonly_observed_real_broker_available_cash_eur"] == 443.9
    assert state["cash"]["readonly_reconciled_real_invested_eur"] == 48.17
