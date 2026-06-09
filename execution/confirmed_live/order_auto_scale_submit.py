"""Submit limit buy with automatic down-scaling when T212 rejects insufficient funds."""

from __future__ import annotations



from pathlib import Path

from typing import Any, Dict, Optional



from execution.confirmed_live.managed_scope_service import load_baseline

from execution.confirmed_live.order_confirmation_token_service import issue_token

from execution.confirmed_live.order_draft_service import (

    create_draft,

    prune_stale_order_drafts,

    prune_superseded_drafts_for_instrument,

    refresh_draft_status,

)

from execution.confirmed_live.order_sizing import (

    MAX_AUTO_SCALE_ATTEMPTS,

    MIN_BUY_QUANTITY,

    is_insufficient_funds_error,

    is_min_quantity_error,

    is_rate_limit_error,

    plan_executable_buy_order,

    shrink_quantity_for_retry,

)

from execution.confirmed_live.order_submission_service import submit_confirmed_order

from integrations.trading212.t212_auth_profile_model import PROFILE_CONFIRMED_EXECUTION

from integrations.trading212.t212_limit_order_constraints import (

    apply_min_quantity_floor,

    probe_min_quantity,

)

from integrations.trading212.t212_order_error_parser import extract_min_quantity

from integrations.trading212.t212_order_pacing import (

    can_place_limit_order_now,

    retry_delay_after_insufficient_funds,

)





def _refresh_free_cash(root: Path) -> float | None:

    from integrations.trading212.t212_readonly_connection_service import sync_readonly_account



    try:

        broker = sync_readonly_account(root, force=True)

        if broker.cash_eur is not None:

            return float(broker.cash_eur)

    except Exception:

        pass

    return None





def submit_scaled_limit_buy(

    root: Path,

    *,

    instrument: str,

    t212_id: str,

    target_notional_eur: float,

    limit_price_eur: float,

    free_cash_eur: float | None,

    account_currency: str = "EUR",

    dry_run: bool = False,

    execution_style: str | None = None,

    order_source: str = "",

) -> Dict[str, Any]:

    """

    Try limit buy; on insufficient funds automatically reduce quantity and retry.

    Returns ok, draft, scaling metadata, and user_message_de.

    """

    root = Path(root)

    from execution.confirmed_live.order_execution_style import resolve_order_execution_style

    style = execution_style or resolve_order_execution_style(root)
    is_market = str(style).lower() == "market"

    prune_stale_order_drafts(root, max_age_minutes=10.0)

    from integrations.trading212.t212_order_readiness import assess_order_readiness

    readiness = assess_order_readiness(root, free_cash_eur=free_cash_eur)
    if not readiness.ok and not dry_run:
        return {
            "ok": False,
            "stage": "readiness",
            "error": ",".join(readiness.blockers),
            "user_message_de": readiness.status_de,
            "readiness": readiness.as_dict(),
        }

    allowed, block_msg = can_place_limit_order_now(root)

    if not allowed:

        return {

            "ok": False,

            "stage": "rate_limit",

            "error": "HTTP 429",

            "user_message_de": block_msg,

        }



    session_hint = ""

    if not dry_run:

        from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now



        sess = us_equity_regular_session_open_now()

        if not sess.get("open"):

            session_hint = str(sess.get("reason_de") or "")



    sym = str(instrument).upper()

    limit = round(float(limit_price_eur), 2)

    if limit <= 0:

        return {

            "ok": False,

            "stage": "sizing",

            "error": "INVALID_LIMIT_PRICE",

            "user_message_de": (
                "Kein gültiger Referenzpreis — bitte «Aktualisieren»."
                if is_market
                else "Kein gültiger Limit-Preis — bitte «Aktualisieren»."
            ),

        }



    cash = free_cash_eur if free_cash_eur is not None else _refresh_free_cash(root)

    if cash is None:

        cash = _refresh_free_cash(root)



    min_qty, _probe_status = probe_min_quantity(root, ticker=t212_id, limit_price=limit)



    plan0 = plan_executable_buy_order(
        target_notional_eur=target_notional_eur,
        limit_price_eur=limit,
        free_cash_eur=cash,
        root=root,
        execution_style=style,
    )

    qty = apply_min_quantity_floor(float(plan0["quantity"]), min_qty)

    if qty < MIN_BUY_QUANTITY:

        from integrations.trading212.t212_user_messages import humanize_t212_error



        return {

            "ok": False,

            "stage": "sizing",

            "error": "INSUFFICIENT_FREE_CASH",

            "user_message_de": humanize_t212_error("insufficient funds"),

            "plan": plan0,

        }



    baseline = load_baseline(root) or {}

    currency = str(account_currency or baseline.get("account_currency") or "EUR")



    last_error = ""

    last_draft: Optional[Dict[str, Any]] = None

    attempts_log: list[Dict[str, Any]] = []

    current_qty = qty



    import time

    max_attempts = MAX_AUTO_SCALE_ATTEMPTS

    for attempt in range(max_attempts):

        if attempt > 0:

            time.sleep(retry_delay_after_insufficient_funds())

            allowed, block_msg = can_place_limit_order_now(root)

            if not allowed:

                return {

                    "ok": False,

                    "stage": "rate_limit",

                    "error": "HTTP 429",

                    "draft": last_draft,

                    "plan": plan0,

                    "attempts": attempts_log,

                    "user_message_de": block_msg,

                }

            fresh = _refresh_free_cash(root)

            if fresh is not None:

                cash = fresh

                replan = plan_executable_buy_order(
                    target_notional_eur=target_notional_eur,
                    limit_price_eur=limit,
                    free_cash_eur=cash,
                    root=root,
                    execution_style=style,
                )

                current_qty = apply_min_quantity_floor(float(replan["quantity"]), min_qty)

            elif is_insufficient_funds_error(last_error):

                current_qty = shrink_quantity_for_retry(current_qty, attempt=attempt)



        current_qty = apply_min_quantity_floor(current_qty, min_qty)

        if current_qty < MIN_BUY_QUANTITY:

            break



        exec_notional = round(current_qty * limit, 2)

        prune_superseded_drafts_for_instrument(root, sym)

        draft = create_draft(

            root,

            instrument=sym,

            side="BUY",

            max_notional_eur=exec_notional,

            limit_price=limit,

            t212_id=t212_id,

            quantity=current_qty,

            execution_style=style,

            order_source=order_source,

        )

        draft = refresh_draft_status(

            root, draft, readonly_cash=cash, account_currency=currency

        )

        last_draft = draft

        if draft.get("status") != "DRAFT_READY_FOR_REVIEW":

            return {

                "ok": False,

                "stage": "preflight",

                "blockers": draft.get("blockers"),

                "draft": draft,

                "plan": plan0,

                "attempts": attempts_log,

            }



        token = issue_token(root, draft, profile=PROFILE_CONFIRMED_EXECUTION)

        result = submit_confirmed_order(

            root,

            draft,

            one_time_token=token["one_time_token"],

            readonly_cash=float(cash) if cash is not None else None,

            account_currency=currency,

            dry_run=dry_run,

            execution_style=style,

        )

        attempts_log.append(

            {

                "attempt": attempt + 1,

                "quantity": current_qty,

                "executable_notional_eur": exec_notional,

                "ok": bool(result.get("ok")),

                "error": str(result.get("error") or "")[:200],

            }

        )

        if result.get("ok"):

            from integrations.trading212.t212_user_messages import format_scaled_order_notice



            scaled = attempt > 0 or bool(plan0.get("scaled_down")) or current_qty < float(plan0["quantity"]) - 1e-6

            result["sent_to_t212"] = True
            return {

                "ok": True,

                "status": result.get("status"),

                "response": result.get("response"),

                "draft": draft,

                "plan": plan0,

                "executed_quantity": current_qty,

                "executed_notional_eur": exec_notional,

                "scaled_down": scaled,

                "attempts": attempts_log,

                "user_message_de": (
                    f"Market-Order {sym}: {current_qty:.4f} Stk. (~{exec_notional:.2f} €)."
                    if is_market
                    else format_scaled_order_notice(
                        symbol=sym,
                        target_notional_eur=float(plan0["target_notional_eur"]),
                        executed_notional_eur=exec_notional,
                        quantity=current_qty,
                        limit_price_eur=limit,
                        scaled_down=scaled,
                        attempt_count=attempt + 1,
                    )
                ),

            }



        last_error = str(result.get("error") or "")

        if is_rate_limit_error(last_error):

            from execution.confirmed_live.order_submission_service import format_broker_submission_error



            return {

                "ok": False,

                "stage": "rate_limit",

                "error": last_error,

                "draft": draft,

                "plan": plan0,

                "attempts": attempts_log,

                "user_message_de": format_broker_submission_error(last_error),

            }

        if is_min_quantity_error(last_error):

            bumped = extract_min_quantity(last_error)

            if bumped is not None:

                from integrations.trading212.t212_limit_order_constraints import record_min_quantity



                record_min_quantity(root, t212_id, bumped)

                current_qty = apply_min_quantity_floor(current_qty, bumped, headroom=1.05)

                min_qty = bumped

                continue

        if not is_insufficient_funds_error(last_error):

            from execution.confirmed_live.order_submission_service import format_broker_submission_error



            return {

                "ok": False,

                "stage": result.get("stage", "submission"),

                "error": last_error,

                "draft": draft,

                "plan": plan0,

                "attempts": attempts_log,

                "user_message_de": format_broker_submission_error(last_error),

            }

        current_qty = shrink_quantity_for_retry(current_qty, attempt=attempt + 1)



    from execution.confirmed_live.order_submission_service import format_broker_submission_error



    msg = format_broker_submission_error(last_error or "insufficient funds")

    if session_hint and is_insufficient_funds_error(last_error):

        from integrations.trading212.t212_user_messages import SYM_INFO



        msg = f"{msg}\n{SYM_INFO} {session_hint}"

    market_try = None
    if not is_market:
        market_try = _try_market_order_fallback(
            root,
            instrument=sym,
            t212_id=t212_id,
            quantity=current_qty if current_qty >= MIN_BUY_QUANTITY else qty,
            min_qty=min_qty,
            dry_run=dry_run,
        )
    if market_try is not None:
        market_try["plan"] = plan0
        market_try["attempts"] = attempts_log + (market_try.get("attempts") or [])
        if market_try.get("ok"):
            return market_try
        if market_try.get("user_message_de"):
            msg = str(market_try["user_message_de"])

    return {

        "ok": False,

        "stage": "submission",

        "error": last_error or "INSUFFICIENT_AFTER_AUTO_SCALE",

        "draft": last_draft,

        "plan": plan0,

        "attempts": attempts_log,

        "user_message_de": msg,

    }


def _try_market_order_fallback(
    root: Path,
    *,
    instrument: str,
    t212_id: str,
    quantity: float,
    min_qty: float | None,
    dry_run: bool,
) -> Dict[str, Any] | None:
    """One market buy (extended hours) when limit path exhausted during US session."""
    from integrations.trading212.t212_order_readiness import us_orders_allowed_now

    allowed, sess = us_orders_allowed_now()
    if not allowed:
        return {
            "ok": False,
            "stage": "market_fallback",
            "user_message_de": str(sess.get("reason_de") or "US-Session geschlossen."),
        }

    qty = apply_min_quantity_floor(float(quantity), min_qty)
    if qty < MIN_BUY_QUANTITY:
        return None

    from integrations.trading212.t212_order_pacing import (
        acquire_market_order_slot,
        can_place_market_order_now,
        record_market_order_result,
    )

    ok_pace, block_msg = can_place_market_order_now(root)
    if not ok_pace:
        return {"ok": False, "stage": "rate_limit", "user_message_de": block_msg}

    body = {"ticker": t212_id, "quantity": round(qty, 4), "extendedHours": False}
    if dry_run:
        return {"ok": True, "stage": "market_fallback", "dry_run": True, "body": body}

    from integrations.trading212.t212_confirmed_execution_client import (
        T212ConfirmedExecutionClient,
        T212ExecutionBlockedError,
    )

    acquire_market_order_slot(root)
    try:
        client = T212ConfirmedExecutionClient.from_execution_profile(root)
        resp = client.submit_market_order(body, root=root)
        record_market_order_result(root, success=True)
        return {
            "ok": True,
            "stage": "market_fallback",
            "status": "SUBMITTED_MARKET",
            "response": resp,
            "executed_quantity": qty,
            "user_message_de": f"Market-Order gesendet ({instrument}, {qty:.4f} Stk., extended hours).",
            "attempts": [{"attempt": "market", "quantity": qty, "ok": True}],
        }
    except T212ExecutionBlockedError as exc:
        record_market_order_result(root, success=False, error=str(exc))
        from execution.confirmed_live.order_submission_service import format_broker_submission_error

        return {
            "ok": False,
            "stage": "market_fallback",
            "error": str(exc),
            "user_message_de": format_broker_submission_error(str(exc)),
            "attempts": [{"attempt": "market", "quantity": qty, "ok": False}],
        }


def submit_scaled_limit_sell(
    root: Path,
    *,
    instrument: str,
    t212_id: str,
    target_notional_eur: float,
    limit_price_eur: float,
    sell_quantity: float | None = None,
    account_currency: str = "EUR",
    dry_run: bool = False,
    execution_style: str | None = None,
    order_source: str = "",
) -> Dict[str, Any]:
    """Limit or market sell (covered) sized from notional or explicit held quantity."""
    root = Path(root)
    from execution.confirmed_live.order_execution_style import resolve_order_execution_style

    style = execution_style or resolve_order_execution_style(root)
    is_market = str(style).lower() == "market"
    prune_stale_order_drafts(root, max_age_minutes=10.0)
    from integrations.trading212.t212_order_readiness import assess_order_readiness

    readiness = assess_order_readiness(root, free_cash_eur=None)
    if not readiness.ok and not dry_run:
        return {
            "ok": False,
            "stage": "readiness",
            "error": ",".join(readiness.blockers),
            "user_message_de": readiness.status_de,
            "readiness": readiness.as_dict(),
        }

    allowed, block_msg = can_place_limit_order_now(root)
    if not allowed:
        return {"ok": False, "stage": "rate_limit", "error": "HTTP 429", "user_message_de": block_msg}

    sym = str(instrument).upper()
    limit = round(float(limit_price_eur), 2)
    if limit <= 0:
        return {
            "ok": False,
            "stage": "sizing",
            "error": "INVALID_LIMIT_PRICE",
            "user_message_de": "Kein gültiger Limit-Preis — bitte «Aktualisieren».",
        }

    target_qty = round(float(sell_quantity), 4) if sell_quantity and sell_quantity > 0 else round(
        float(target_notional_eur) / limit, 4
    )
    if target_qty < MIN_BUY_QUANTITY:
        return {
            "ok": False,
            "stage": "sizing",
            "error": "QUANTITY_TOO_SMALL",
            "user_message_de": f"Verkaufsmenge für {sym} zu klein.",
        }

    min_qty, _ = probe_min_quantity(root, ticker=t212_id, limit_price=limit)
    qty = apply_min_quantity_floor(target_qty, min_qty)
    exec_notional = round(qty * limit, 2)
    prune_superseded_drafts_for_instrument(root, sym)
    draft = create_draft(
        root,
        instrument=sym,
        side="SELL",
        max_notional_eur=exec_notional,
        limit_price=limit,
        t212_id=t212_id,
        quantity=qty,
        execution_style=style,
        order_source=order_source,
    )
    draft = refresh_draft_status(root, draft, readonly_cash=None, account_currency=account_currency)
    if draft.get("status") != "DRAFT_READY_FOR_REVIEW":
        return {
            "ok": False,
            "stage": "preflight",
            "blockers": draft.get("blockers"),
            "draft": draft,
        }

    token = issue_token(root, draft, profile=PROFILE_CONFIRMED_EXECUTION)
    result = submit_confirmed_order(
        root,
        draft,
        one_time_token=token["one_time_token"],
        readonly_cash=None,
        account_currency=account_currency,
        dry_run=dry_run,
        execution_style=style,
    )
    if result.get("ok"):
        result["sent_to_t212"] = True
        if is_market:
            result["user_message_de"] = f"Market-Verkauf {sym}: {qty:.4f} Stk."
        else:
            result["user_message_de"] = f"Verkauf {sym}: {qty:.4f} Stk. @ {limit:.2f} € Limit."
    return result


