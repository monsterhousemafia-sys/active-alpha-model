#!/usr/bin/env python3
"""Virtual end-to-end test for pilot day trading facade (no broker/network)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from unittest.mock import patch

    import pandas as pd

    from analytics.pilot_day_trading_facade import refresh_trading_snapshot
    from analytics.pilot_day_trading_policy import migrate_legacy_policies_to_unified

    root = ROOT
    csv_path = root / "model_output_sp500_pit_t212/latest_target_portfolio.csv"
    if not csv_path.is_file():
        print("SKIP: no champion CSV in workspace")
        return 0

    migrate_legacy_policies_to_unified(root)
    df = pd.read_csv(csv_path)
    df = df[df["ticker"].astype(str).str.upper() != "SPY"].head(1)
    sym = str(df.iloc[0]["ticker"]) if not df.empty else "INTC"

    broker = {
        "cash_eur": 492.0,
        "cash_breakdown": {"total_account_value_eur": 520.0},
        "positions": [],
    }
    plan = {
        "champion_id": "R3_w075_q065_noexit",
        "signal_date": str(df.iloc[0].get("signal_date", ""))[:10] if not df.empty else "",
        "primary_action": {"symbol": sym, "target_eur": 40.0},
        "allocations": [{"symbol": sym, "model_weight_pct": 8.0, "alpha_lcb": 0.5}],
    }

    scenarios = [
        ("US_OPEN", {"open": True, "phase": "OPEN"}),
        ("US_CLOSED", {"open": False, "phase": "CLOSED"}),
    ]
    results = []
    for label, sess in scenarios:
        with patch(
            "integrations.trading212.t212_exchange_session.us_equity_regular_session_open_now",
            return_value=sess,
        ):
            with patch(
                "execution.confirmed_live.us_equity_deferred_intents.process_deferred_intents_if_due",
                return_value={"executed": 0, "skipped": ["VIRTUAL"]},
            ):
                with patch(
                    "integrations.trading212.t212_order_readiness.assess_order_readiness",
                ) as m:
                    from integrations.trading212.t212_order_readiness import T212OrderReadiness

                    m.return_value = T212OrderReadiness(
                        ok=bool(sess.get("open")),
                        api_execute_configured=True,
                        api_execute_scope_proven=True,
                        us_session_open=bool(sess.get("open")),
                        cash_eur=492.0,
                        cash_source="virtual",
                        blockers=[] if sess.get("open") else ["US_REGULAR_SESSION_CLOSED"],
                        warnings=[],
                        status_de="virtual",
                        session=sess,
                    )
                    snap = refresh_trading_snapshot(
                        root,
                        broker=broker,
                        plan=plan,
                        quote_snapshot={
                            "freshness": {
                                "status": "FRESH",
                                "calculation_allowed": True,
                                "age_seconds": 10,
                            },
                            "executable_prices_eur": {sym: 25.0},
                        },
                        champion_guard={"champion_ok": True, "signals_ok": True},
                        force_reevaluation=True,
                    )
        results.append(
            {
                "scenario": label,
                "next_action": snap.playbook.get("next_action"),
                "urgency": snap.reevaluation.get("urgency"),
                "trade_required": snap.reevaluation.get("trade_required"),
                "headline": snap.playbook.get("headline_de"),
            }
        )

    out = root / "evidence" / "virtual_test_pilot_day_trading_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"results": results}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    payload = json.dumps(results, indent=2, ensure_ascii=True)
    print(payload)
    ok = all(r.get("next_action") for r in results)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
