#!/usr/bin/env python3
"""Diagnose T212 limit-order execution — prints PASS/FAIL and German hints."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from aa_pilot_launch import bootstrap_pilot_runtime

    root = bootstrap_pilot_runtime(ROOT)
    from integrations.trading212.t212_dual_profile_credential_store import execution_configured
    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now
    from integrations.trading212.t212_limit_order_constraints import probe_min_quantity
    from integrations.trading212.t212_confirmed_execution_client import (
        T212ConfirmedExecutionClient,
        T212ExecutionBlockedError,
    )
    from integrations.trading212.t212_order_pacing import acquire_limit_order_slot, record_limit_order_result
    from market.live_quote_engine import ensure_live_quotes_fresh

    from integrations.trading212.t212_order_readiness import assess_order_readiness

    print("=== T212 Order Execute Verify ===")
    if not execution_configured():
        print("FAIL: API mit Order-Rechten nicht geladen — in der App speichern.")
        return 1

    broker = sync_readonly_account(root, force=True)
    print(f"Cash availableToTrade: {broker.cash_eur} EUR")

    readiness = assess_order_readiness(root, free_cash_eur=broker.cash_eur)
    print("Readiness:", readiness.status_de.replace("\n", " | "))
    if not readiness.ok:
        print("BLOCKERS:", readiness.blockers)
        if "US_REGULAR_SESSION_CLOSED" in readiness.blockers:
            print("INFO: API-Berechtigungen sind OK — Test während US-Regular-Session wiederholen.")
            return 2
        return 1

    session = us_equity_regular_session_open_now()
    print(f"US regular session open: {session.get('open')} — {session.get('reason_de', 'OK')}")

    snap = ensure_live_quotes_fresh(root, force=False)
    prices = snap.get("executable_prices_eur") or {}
    ticker = "INTC_US_EQ"
    limit = round(float(prices.get("INTC") or 94.0), 2)
    print(f"INTC limit EUR (model): {limit}")

    min_q, status = probe_min_quantity(root, ticker=ticker, limit_price=limit, use_cache=False)
    print(f"Min quantity probe: {min_q} ({status})")

    if min_q is None:
        print("WARN: Min quantity unknown — probe did not return min-quantity error.")
        return 2

    qty = round(min_q * 1.05, 4)
    body = {
        "ticker": ticker,
        "quantity": qty,
        "limitPrice": limit,
        "timeValidity": "GOOD_TILL_CANCEL",
    }
    acquire_limit_order_slot(root)
    client = T212ConfirmedExecutionClient.from_execution_profile(root)
    try:
        resp = client.submit_limit_order(body, root=root)
        record_limit_order_result(root, success=True)
        print(f"PASS: Order accepted id={resp.get('id')} status={resp.get('status')}")
        return 0
    except T212ExecutionBlockedError as exc:
        record_limit_order_result(root, success=False, error=str(exc))
        from integrations.trading212.t212_user_messages import humanize_t212_error

        print("FAIL:", humanize_t212_error(str(exc)).encode("ascii", "replace").decode())
        print("\nRaw:", str(exc)[:300])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
