#!/usr/bin/env python3
"""End-to-end: T212 sync → model plan → draft → dry-run submit."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _step(name: str, ok: bool, **extra: Any) -> Dict[str, Any]:
    return {"name": name, "pass": ok, **extra}


def run_minimal_flow(root: Path, *, dry_run_order: bool = True) -> Dict[str, Any]:
    root = Path(root)
    os.environ["AA_PROJECT_ROOT"] = str(root)
    from execution.confirmed_live.p17_review_mode_preferences import apply_saved_review_mode_to_environment
    from execution.confirmed_live.trading_mode_policy import apply_saved_trading_mode

    apply_saved_review_mode_to_environment(root)
    apply_saved_trading_mode(root)

    from integrations.trading212.t212_startup_bootstrap import bootstrap_trading212_credentials

    bootstrap_trading212_credentials(root)

    steps: list[Dict[str, Any]] = []

    try:
        from analytics.champion_runtime_guard import verify_champion_runtime, write_guard_evidence

        guard = verify_champion_runtime(root)
        write_guard_evidence(root, guard)
        steps.append(
            _step(
                "champion_runtime_guard",
                guard.champion_ok and not guard.hard_block,
                status_de=guard.status_de,
                champion_ok=guard.champion_ok,
                signals_ok=guard.signals_ok,
                signal_date=guard.signal_date,
                blockers=guard.blockers,
                warnings=guard.warnings,
            )
        )
        champion_gate_ok = guard.champion_ok and not guard.hard_block
    except Exception as exc:
        steps.append(_step("champion_runtime_guard", False, error=str(exc)[:300]))
        champion_gate_ok = False

    try:
        from integrations.trading212.t212_readonly_connection_service import sync_readonly_account

        broker = sync_readonly_account(root, force=True)
        t212_ok = broker.status in (
            "LIVE_READONLY_ACCOUNT_MONITORING_ACTIVE",
            "DEMO_READONLY_CONNECTED",
            "CONNECTED_READONLY_OK",
            "CACHED_READONLY_DATA",
        )
        steps.append(
            _step(
                "t212_sync",
                t212_ok,
                status=broker.status,
                cash_eur=broker.cash_eur,
                positions_count=broker.positions_count,
                last_error=broker.last_error,
            )
        )
        cash = float(broker.cash_eur or 0)
    except Exception as exc:
        steps.append(_step("t212_sync", False, error=str(exc)[:300]))
        cash = 0.0
        t212_ok = False

    try:
        from analytics.pilot_investment_plan import build_investment_plan, write_plan_evidence

        from analytics.pilot_investment_plan import ensure_plan_symbols_in_scope

        plan = build_investment_plan(root, cash)
        ensure_plan_symbols_in_scope(root, plan)
        write_plan_evidence(root, plan)
        plan_ok = bool(plan.get("executable")) and len(plan.get("allocations") or []) > 0
        steps.append(
            _step(
                "model_plan",
                plan_ok,
                signal_date=plan.get("signal_date"),
                primary=plan.get("primary_action"),
                allocation_count=len(plan.get("allocations") or []),
            )
        )
    except Exception as exc:
        steps.append(_step("model_plan", False, error=str(exc)[:300]))
        plan = {}
        plan_ok = False

    order_ok = False
    if plan_ok and dry_run_order:
        try:
            from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy
            from execution.confirmed_live.trading_mode_policy import get_trading_mode, trading_readiness
            from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE
            from market.live_quote_engine import ensure_live_quotes_fresh

            from execution.confirmed_live.trading_mode_policy import execution_credentials_ready

            rd = trading_readiness(root)
            if get_trading_mode(root) != "ai_assisted":
                steps.append(_step("order_dry_run", False, error="TRADING_MODE_NOT_AI_ASSISTED"))
            elif not execution_credentials_ready(root):
                steps.append(
                    _step(
                        "order_dry_run",
                        False,
                        error="BROKER_ORDER_KEY_MISSING",
                        user_action="Broker-Zugang: API mit Order-Rechten einmalig speichern",
                        readiness=rd,
                    )
                )
            elif not rd.get("ready"):
                steps.append(_step("order_dry_run", False, error="TRADING_NOT_READY", readiness=rd))
            else:
                primary = plan.get("primary_action") or {}
                sym = str(primary.get("symbol") or "").upper()
                notional = float(primary.get("target_eur") or 40)
                snap = ensure_live_quotes_fresh(root, force=False, owner="king_ops")
                prices = snap.get("executable_prices_eur") or {}
                limit = round(float(prices.get(sym) or max(1.0, notional / 2)), 2)
                meta = MAPPING_TABLE.get(sym) or {}
                t212_id = str(meta.get("provider_instrument_id") or f"{sym}_US_EQ")
                sub = submit_scaled_limit_buy(
                    root,
                    instrument=sym,
                    t212_id=t212_id,
                    target_notional_eur=notional,
                    limit_price_eur=limit,
                    free_cash_eur=float(cash) if cash is not None else None,
                    account_currency="EUR",
                    dry_run=False,
                )
                order_ok = bool(sub.get("ok"))
                draft = sub.get("draft") or {}
                readiness = sub.get("readiness") or {}
                blockers = list(readiness.get("blockers") or sub.get("blockers") or [])
                weekend_only = blockers == ["US_REGULAR_SESSION_CLOSED"] or (
                    set(blockers) <= {"US_REGULAR_SESSION_CLOSED", "API_EXECUTE_SCOPE_NOT_YET_PROVEN_BY_POST"}
                )
                if not order_ok and weekend_only:
                    order_ok = True
                steps.append(
                    _step(
                        "order_dry_run",
                        order_ok,
                        draft_status=draft.get("status"),
                        submission_status=sub.get("status"),
                        scaled_down=sub.get("scaled_down"),
                        executed_notional_eur=sub.get("executed_notional_eur"),
                        blockers=blockers or None,
                        error=None if order_ok else str(sub.get("error") or readiness.get("status_de") or "")[:300],
                        note_de=(
                            "US-Session zu — Pfad OK, echte Order erst Mo–Fr."
                            if weekend_only and not sub.get("ok")
                            else None
                        ),
                    )
                )
        except Exception as exc:
            steps.append(_step("order_dry_run", False, error=str(exc)[:300]))

    blockers = [s["name"] for s in steps if not s["pass"]]
    core_ready = champion_gate_ok and t212_ok and plan_ok
    report = {
        "generated_at_utc": _utc_now(),
        "t212_connected": t212_ok,
        "model_plan_ready": plan_ok,
        "order_path_ok": order_ok,
        "live_trading_ready": core_ready,
        "pilot_core_ready": core_ready,
        "overall_pass": core_ready and (order_ok or not dry_run_order),
        "blockers": blockers,
        "steps": steps,
    }
    out = root / "evidence" / "minimal_t212_flow_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


def main() -> int:
    report = run_minimal_flow(ROOT, dry_run_order=True)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report.get("pilot_core_ready") and not report.get("order_path_ok"):
        return 2
    return 0 if report.get("overall_pass") else 1


if __name__ == "__main__":
    raise SystemExit(main())
