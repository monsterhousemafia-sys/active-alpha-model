"""R3 — klickbare Aktien (Kauf/Verkauf) + Initial-Gesamtpaket; Optimum aus Hintergrund-Reevaluation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json

_ORDER_SOURCE = "R3_DESKTOP"
_EVIDENCE_REL = Path("evidence/r3_stock_orders_latest.json")
_BATCH_EVIDENCE_REL = Path("evidence/r3_order_batch_latest.json")
_DEFERRED_PKG_EVIDENCE_REL = Path("evidence/r3_package_deferred_latest.json")
_SELL_CODES = frozenset({"REDUZIEREN", "ABBAUEN", "VERKAUFEN"})
_BUY_CODES = frozenset({"NACHKAUF", "KAUFEN", "ERHÖHEN"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _action_side(action_code: str, gap_eur: float) -> str:
    code = str(action_code or "").upper()
    if code in _SELL_CODES or gap_eur < 0:
        return "SELL"
    return "BUY"


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").upper().replace(".US", "").strip()


def _held_symbols(root: Path) -> set[str]:
    """Symbole im Depot — für «Neue Aktien» vs Nachkauf."""
    root = Path(root)
    held: set[str] = set()
    reeval = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
    human = reeval.get("human_snapshot") or {}
    for h in human.get("holdings") or []:
        sym = _normalize_symbol(str(h.get("symbol") or h.get("ticker") or ""))
        if sym:
            held.add(sym)
    if held:
        return held
    snap = _load_json(root / "evidence/pilot_day_trading_snapshot_latest.json")
    broker = snap.get("broker") or {}
    for pos in broker.get("positions") or []:
        sym = _normalize_symbol(str(pos.get("ticker") or pos.get("symbol") or ""))
        if sym:
            held.add(sym)
    return held


def _build_plan_stock_actions(root: Path) -> List[Dict[str, Any]]:
    """Einzige Ausführungsquelle — pilot_investment_plan (Modell-Plan)."""
    root = Path(root)
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    allocations = list(plan.get("allocations") or [])
    if not allocations:
        return []

    try:
        from analytics.r3_trading_functions import load_functions_policy

        min_trade = float(load_functions_policy(root).get("min_trade_eur") or 12.0)
    except Exception:
        min_trade = 12.0

    held = _held_symbols(root)
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for alloc in allocations:
        sym = _normalize_symbol(str(alloc.get("symbol") or ""))
        if not sym or sym in seen:
            continue
        side = str(alloc.get("side") or "BUY").upper()
        if side not in ("BUY", "SELL"):
            continue
        target = float(alloc.get("target_eur") or 0)
        if target < min_trade:
            continue
        seen.add(sym)
        if side == "SELL":
            rows.append(
                {
                    "symbol": sym,
                    "side": "SELL",
                    "side_de": "Verkauf",
                    "is_new_position": False,
                    "notional_eur": round(target, 2),
                    "action_code": "REDUZIEREN",
                    "action_de": str(alloc.get("rationale_de") or "")[:120],
                    "priority_score": float(alloc.get("model_weight_pct") or alloc.get("alpha_lcb") or 0),
                    "target_weight_pct": alloc.get("model_weight_pct"),
                    "clickable": True,
                    "optimum_ref": "evidence/pilot_investment_plan_latest.json",
                    "decision_source": "pilot_investment_plan",
                }
            )
            continue
        is_new = sym not in held
        rows.append(
            {
                "symbol": sym,
                "side": "BUY",
                "side_de": "Neue Aktie" if is_new else "Nachkauf",
                "is_new_position": is_new,
                "notional_eur": round(target, 2),
                "action_code": "KAUFEN",
                "action_de": str(alloc.get("rationale_de") or "")[:120],
                "priority_score": float(alloc.get("model_weight_pct") or alloc.get("alpha_lcb") or 0),
                "target_weight_pct": alloc.get("model_weight_pct"),
                "clickable": True,
                "optimum_ref": "evidence/pilot_investment_plan_latest.json",
                "decision_source": "pilot_investment_plan",
            }
        )

    rows.sort(key=lambda x: (-float(x.get("priority_score") or 0), str(x.get("symbol") or "")))
    return rows


def _apply_plan_execution_scaling(root: Path, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Leeres Depot: Plan-Gewichte proportional auf T212-Budget — sonst Plan-Beträge unverändert."""
    if _is_flat_depot(root):
        return _maybe_scale_initial_buys(root, rows)
    return rows


def _merge_reeval_sells_into_plan_rows(
    root: Path,
    plan_rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Verkäufe aus Reevaluation — nur gehaltene Symbole, Plan-SELL hat Vorrang."""
    if not plan_rows:
        return []
    held = _held_symbols(root)
    plan_sell_syms = {str(r.get("symbol") or "").upper() for r in plan_rows if r.get("side") == "SELL"}
    merged = list(plan_rows)
    for row in _build_quant_stock_actions(root):
        if row.get("side") != "SELL":
            continue
        sym = str(row.get("symbol") or "").upper()
        if not sym or sym in plan_sell_syms or sym not in held:
            continue
        merged.append(row)
    merged.sort(key=lambda x: (-float(x.get("priority_score") or 0), str(x.get("symbol") or "")))
    return merged


def build_optimal_stock_actions(root: Path) -> List[Dict[str, Any]]:
    """
    Ausführbare Zeilen: Käufe aus pilot_investment_plan;
    Verkäufe aus Plan und/oder pilot_portfolio_reevaluation (gehaltene Positionen).
    """
    root = Path(root)
    plan_rows = _build_plan_stock_actions(root)
    if not plan_rows:
        sells_only = [r for r in _build_quant_stock_actions(root) if r.get("side") == "SELL"]
        return sells_only
    merged = _merge_reeval_sells_into_plan_rows(root, plan_rows)
    return _apply_plan_execution_scaling(root, merged)


def _is_flat_depot(root: Path) -> bool:
    reeval = _load_json(Path(root) / "evidence/pilot_portfolio_reevaluation_latest.json")
    human = reeval.get("human_snapshot") or {}
    if int(human.get("positions_count") or 0) == 0:
        return True
    snap = _load_json(Path(root) / "evidence/pilot_day_trading_snapshot_latest.json")
    broker = snap.get("broker") or {}
    return len(broker.get("positions") or []) == 0


def _resolve_max_single_buy_eur(root: Path, budget_eur: Optional[float] = None) -> float:
    """Obergrenze pro Einzelkauf — kein All-in in eine Aktie."""
    try:
        from analytics.r3_trading_functions import load_functions_policy

        policy = load_functions_policy(root)
    except Exception:
        policy = {}
    pct = float(policy.get("max_single_buy_pct") or 0.12)
    abs_cap = float(policy.get("max_single_buy_eur") or 0)
    budget = float(budget_eur or 0)
    if budget <= 0:
        budget = float(_resolve_initial_budget_eur(root) or 0)
    if budget <= 0:
        plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
        budget = float(plan.get("investable_eur") or 0)
    pct_cap = round(budget * pct, 2) if budget > 0 else 0.0
    if budget <= 0:
        return 0.0
    if abs_cap > 0 and pct_cap > 0:
        return min(pct_cap, abs_cap)
    if abs_cap > 0:
        return abs_cap
    return pct_cap


def _enforce_no_all_in(
    rows: List[Dict[str, Any]],
    *,
    root: Path,
    budget_eur: Optional[float] = None,
    min_trade_eur: float = 12.0,
) -> List[Dict[str, Any]]:
    """Kein All-in: eine Aktie darf nicht (fast) das gesamte Budget bekommen."""
    budget = float(budget_eur or 0)
    if budget <= 0:
        budget = float(_resolve_initial_budget_eur(root) or 0)
    if budget <= 0:
        return rows
    max_single = _resolve_max_single_buy_eur(root, budget)
    if max_single <= 0:
        return rows
    buys = [r for r in rows if str(r.get("side") or "").upper() == "BUY"]
    n_buys = len(buys)
    out: List[Dict[str, Any]] = []
    for row in rows:
        if str(row.get("side") or "").upper() != "BUY":
            out.append(row)
            continue
        raw = float(row.get("notional_eur") or 0)
        all_in_risk = n_buys == 1 or raw >= budget * 0.9
        if not all_in_risk:
            out.append(row)
            continue
        capped = round(min(raw, max_single), 2)
        if capped < min_trade_eur:
            continue
        patched = {**row, "notional_eur": capped}
        if capped + 0.01 < raw:
            patched["single_buy_capped"] = True
            patched["single_buy_cap_eur"] = max_single
        out.append(patched)
    return out if out else rows


def _maybe_scale_initial_buys(root: Path, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not _is_flat_depot(root):
        return rows
    budget = _resolve_initial_budget_eur(root)
    if not budget or budget <= 0:
        return rows
    try:
        from analytics.r3_trading_functions import load_functions_policy

        min_trade = float(load_functions_policy(root).get("min_trade_eur") or 12.0)
    except Exception:
        min_trade = 12.0
    scaled = _scale_buy_rows_to_budget(rows, budget, min_trade_eur=min_trade)
    return _enforce_no_all_in(scaled, root=root, budget_eur=budget, min_trade_eur=min_trade)


def _build_quant_stock_actions(root: Path) -> List[Dict[str, Any]]:
    """Roh-Optimum aus pilot_portfolio_reevaluation (priority_score)."""
    root = Path(root)
    reeval = _load_json(root / "evidence/pilot_portfolio_reevaluation_latest.json")
    if not reeval:
        snap = _load_json(root / "evidence/pilot_day_trading_snapshot_latest.json")
        reeval = dict(snap.get("reevaluation") or {})

    policy: Dict[str, Any] = {}
    try:
        from analytics.r3_trading_functions import load_functions_policy

        policy = load_functions_policy(root)
    except Exception:
        policy = {"min_trade_eur": 12.0}

    min_trade = float(policy.get("min_trade_eur") or 12.0)
    held = _held_symbols(root)
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for action in sorted(
        list(reeval.get("recommended_actions") or []),
        key=lambda x: -float(x.get("priority_score") or 0),
    ):
        sym = str(action.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        gap = float(action.get("gap_eur") or 0)
        if abs(gap) < min_trade:
            continue
        code = str(action.get("action_code") or "")
        if code == "HALTEN":
            continue
        side = _action_side(code, gap)
        is_new = side == "BUY" and sym not in held
        seen.add(sym)
        if side == "BUY":
            side_de = "Neue Aktie" if is_new else "Nachkauf"
        else:
            side_de = "Verkauf"
        rows.append(
            {
                "symbol": sym,
                "side": side,
                "side_de": side_de,
                "is_new_position": is_new,
                "notional_eur": round(abs(gap), 2),
                "action_code": code,
                "action_de": str(action.get("action_de") or "")[:120],
                "priority_score": float(action.get("priority_score") or 0),
                "target_weight_pct": action.get("target_weight_pct"),
                "limit_price_eur": action.get("live_price_eur"),
                "clickable": True,
                "optimum_ref": "evidence/pilot_portfolio_reevaluation_latest.json",
            }
        )
    return rows


def build_stock_groups(root: Path) -> Dict[str, Any]:
    """Verkauf + neue Aktien (+ Nachkauf) — gleiche Kernel-Quelle wie Submit."""
    rows = build_optimal_stock_actions(root)
    sells = [r for r in rows if r.get("side") == "SELL"]
    buys = [r for r in rows if r.get("side") == "BUY"]
    new_buys = [r for r in buys if r.get("is_new_position")]
    rebuy = [r for r in buys if not r.get("is_new_position")]
    return {
        "sells": sells,
        "new_buys": new_buys,
        "rebuy": rebuy,
        "buys": buys,
        "all": rows,
        "sell_count": len(sells),
        "new_buy_count": len(new_buys),
        "rebuy_count": len(rebuy),
    }


def _resolve_initial_budget_eur(root: Path) -> Optional[float]:
    """Autoritatives T212-Investierbar für Initial-Paket."""
    try:
        from analytics.r3_closed_loop import resolve_r3_investable_for_trading

        return resolve_r3_investable_for_trading(root)
    except Exception:
        return None


def _scale_buy_rows_to_budget(
    rows: List[Dict[str, Any]],
    budget_eur: float,
    *,
    min_trade_eur: float,
) -> List[Dict[str, Any]]:
    """Proportional auf T212-Guthaben skalieren — Gewichtsverhältnisse bleiben."""
    budget = round(max(0.0, float(budget_eur)), 2)
    if budget <= 0:
        return rows
    buys = [r for r in rows if r.get("side") == "BUY"]
    if not buys:
        return rows
    current = sum(float(r.get("notional_eur") or 0) for r in buys)
    if current <= 0:
        weights = [max(float(r.get("priority_score") or 1.0), 0.01) for r in buys]
        wsum = sum(weights) or float(len(buys))
        scaled: List[Dict[str, Any]] = []
        allocated = 0.0
        buy_i = 0
        for row in rows:
            if row.get("side") != "BUY":
                scaled.append(row)
                continue
            buy_i += 1
            if buy_i == len(buys):
                new_n = round(budget - allocated, 2)
            else:
                new_n = round(budget * weights[buy_i - 1] / wsum, 2)
                allocated += new_n
            if new_n < min_trade_eur:
                continue
            scaled.append({**row, "notional_eur": new_n, "budget_scaled": True})
        buy_sum = sum(float(r.get("notional_eur") or 0) for r in scaled if r.get("side") == "BUY")
        if buy_sum > budget + 0.02 and scaled:
            last_buy = max(
                (i for i, r in enumerate(scaled) if r.get("side") == "BUY"),
                default=None,
            )
            if last_buy is not None:
                excess = round(buy_sum - budget, 2)
                scaled[last_buy] = {
                    **scaled[last_buy],
                    "notional_eur": round(
                        max(min_trade_eur, float(scaled[last_buy].get("notional_eur") or 0) - excess),
                        2,
                    ),
                }
        return scaled if scaled else rows
    if abs(current - budget) < 0.5:
        return rows
    if all(r.get("budget_scaled") for r in buys) and abs(current - budget) < 1.0:
        return rows
    factor = budget / current
    scaled: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("side") != "BUY":
            scaled.append(row)
            continue
        new_n = round(float(row.get("notional_eur") or 0) * factor, 2)
        if new_n < min_trade_eur:
            continue
        scaled.append({**row, "notional_eur": new_n, "budget_scaled": True})
    buy_sum = sum(float(r.get("notional_eur") or 0) for r in scaled if r.get("side") == "BUY")
    if buy_sum > budget + 0.02 and scaled:
        last_buy = max(
            (i for i, r in enumerate(scaled) if r.get("side") == "BUY"),
            default=None,
        )
        if last_buy is not None:
            excess = round(buy_sum - budget, 2)
            scaled[last_buy] = {
                **scaled[last_buy],
                "notional_eur": round(max(min_trade_eur, float(scaled[last_buy].get("notional_eur") or 0) - excess), 2),
            }
    return scaled


def build_initial_package(root: Path, *, stocks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    root = Path(root)
    policy: Dict[str, Any] = {}
    ctx: Dict[str, Any] = {}
    try:
        from analytics.r3_trading_functions import (
            _collect_context,
            evaluate_initial_order,
            load_functions_policy,
        )

        policy = load_functions_policy(root)
        ctx = _collect_context(root)
        initial = evaluate_initial_order(ctx, policy)
    except Exception:
        initial = {}

    stock_rows = list(stocks) if stocks is not None else build_optimal_stock_actions(root)
    budget = _resolve_initial_budget_eur(root) or float(ctx.get("investable_eur") or 0)
    min_trade = float(policy.get("min_trade_eur") or 12.0)
    if budget > 0 and int(ctx.get("positions_count") or 0) == 0:
        stock_rows = _scale_buy_rows_to_budget(stock_rows, budget, min_trade_eur=min_trade)
        stock_rows = _enforce_no_all_in(
            stock_rows,
            root=root,
            budget_eur=budget,
            min_trade_eur=min_trade,
        )

    buys = [s for s in stock_rows if s.get("side") == "BUY"]
    active = bool(initial.get("active"))
    notional = round(sum(float(s.get("notional_eur") or 0) for s in buys), 2)
    budget_ref = round(budget, 2) if budget > 0 else None
    return {
        "active": active,
        "label_de": "Gesamtpaket kaufen",
        "order_count": len(buys),
        "notional_eur": notional,
        "budget_eur": budget_ref,
    }


def load_stock_orders(root: Path) -> Dict[str, Any]:
    return _load_json(Path(root) / _EVIDENCE_REL)


def refresh_stock_order_evidence(root: Path, *, persist: bool = True) -> Dict[str, Any]:
    root = Path(root)
    try:
        from analytics.kernel_trade_decisions import ensure_kernel_trade_decisions

        ensure_kernel_trade_decisions(root)
    except Exception:
        pass
    stocks = build_optimal_stock_actions(root)
    buys = [r for r in stocks if r.get("side") == "BUY"]
    sells = [r for r in stocks if r.get("side") == "SELL"]
    new_buys = [r for r in buys if r.get("is_new_position")]
    rebuy = [r for r in buys if not r.get("is_new_position")]
    package = build_initial_package(root, stocks=stocks)
    doc = {
        "schema_version": 2,
        "updated_at_utc": _utc_now(),
        "order_source": _ORDER_SOURCE,
        "stocks": stocks,
        "stock_groups": {
            "sells": sells,
            "new_buys": new_buys,
            "rebuy": rebuy,
        },
        "initial_package": package,
        "buy_count": len(buys),
        "sell_count": len(sells),
        "new_buy_count": len(new_buys),
    }
    if persist:
        atomic_write_json(root / _EVIDENCE_REL, doc)
    return doc


def _find_stock_row(root: Path, symbol: str, side: str) -> Optional[Dict[str, Any]]:
    sym = str(symbol or "").upper()
    side_u = str(side or "").upper()
    for row in build_optimal_stock_actions(root):
        if row.get("symbol") == sym and row.get("side") == side_u:
            return row
    return None


def _precheck_order_rows(
    root: Path,
    rows: List[Dict[str, Any]],
    *,
    side: str,
) -> Dict[str, Any]:
    """Vorcheck aller Zeilen — fail-closed vor Batch-Submit."""
    root = Path(root)
    side_u = str(side or "BUY").upper()
    min_trade = 12.0
    try:
        from analytics.r3_trading_functions import load_functions_policy

        min_trade = float(load_functions_policy(root).get("min_trade_eur") or 12.0)
    except Exception:
        pass
    quote_snapshot: Dict[str, Any] = {}
    try:
        from analytics.live_trading_operations import sync_broker_and_quotes

        sync = sync_broker_and_quotes(root, force_quotes=True)
        quote_snapshot = sync.get("quote_snapshot") or {}
    except Exception:
        pass

    failures: List[Dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if not sym:
            failures.append({"symbol": "—", "error": "MISSING_SYMBOL"})
            continue
        if str(row.get("side") or side_u).upper() != side_u:
            continue
        notional = float(row.get("notional_eur") or 0)
        if notional < min_trade:
            failures.append(
                {
                    "symbol": sym,
                    "error": "NOTIONAL_TOO_SMALL",
                    "notional_eur": notional,
                }
            )
            continue
        limit = _resolve_limit_price(root, sym, row, quote_snapshot=quote_snapshot)
        if limit <= 0:
            failures.append({"symbol": sym, "error": "NO_LIMIT_PRICE"})
    return {
        "ok": len(failures) == 0,
        "checked": len(rows),
        "failures": failures,
        "quote_snapshot": quote_snapshot,
    }


def _min_trade_eur(root: Path) -> float:
    try:
        from analytics.r3_trading_functions import load_functions_policy

        return float(load_functions_policy(root).get("min_trade_eur") or 12.0)
    except Exception:
        return 12.0


def _plan_for_deferred(root: Path) -> Dict[str, Any]:
    plan = _load_json(root / "evidence/pilot_investment_plan_latest.json")
    if plan.get("allocations") or plan.get("primary_action"):
        return plan
    return {}


def _plan_symbols(plan: Dict[str, Any]) -> set[str]:
    syms: set[str] = set()
    for row in plan.get("allocations") or []:
        sym = str(row.get("symbol") or "").upper()
        if sym:
            syms.add(sym)
    primary = plan.get("primary_action") or {}
    ps = str(primary.get("symbol") or "").upper()
    if ps:
        syms.add(ps)
    return syms


def _package_row_symbols(rows: List[Dict[str, Any]], *, side: str) -> set[str]:
    side_u = str(side or "BUY").upper()
    return {
        str(r.get("symbol") or "").upper()
        for r in rows
        if r.get("symbol") and str(r.get("side") or side_u).upper() == side_u
    }


def _persist_deferred_package_evidence(root: Path, out: Dict[str, Any]) -> None:
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "ok": bool(out.get("ok")),
        "mode": out.get("mode"),
        "enqueued": out.get("enqueued"),
        "orders_total": out.get("orders_total"),
        "symbols": list(out.get("symbols") or []),
        "already_queued": bool(out.get("already_queued")),
        "atomic_abort": bool(out.get("atomic_abort")),
        "message_de": str(out.get("message_de") or "")[:300],
        "source_de": _ORDER_SOURCE,
        "queue_ref": "live_pilot/confirmed_execution/us_equity_deferred_intents.json",
    }
    atomic_write_json(root / _DEFERRED_PKG_EVIDENCE_REL, doc)


def _live_submit_ready(root: Path) -> bool:
    try:
        from analytics.r3_mirror_state import resolve_submission_mode

        return bool(resolve_submission_mode(root).get("live_submit"))
    except Exception:
        return False


def _enqueue_r3_package_deferred(
    root: Path,
    rows: List[Dict[str, Any]],
    *,
    quote_snapshot: Dict[str, Any],
    side: str = "BUY",
) -> Dict[str, Any]:
    """Gesamtpaket als US-Vorbestellung — atomar, fail-closed, idempotent."""
    from execution.confirmed_live.us_equity_deferred_intents import (
        cancel_pending_intents,
        enqueue_intent_for_symbol,
        limit_price_for_deferred,
        load_policy,
        r3_package_pending_status,
    )
    from integrations.trading212.t212_exchange_session import format_next_open_de

    side_u = str(side or "BUY").upper()
    pkg_rows = [r for r in rows if str(r.get("side") or side_u).upper() == side_u]
    want_syms = _package_row_symbols(pkg_rows, side=side_u)
    if not want_syms:
        out = {
            "ok": False,
            "error": "NO_PACKAGE_ROWS",
            "mode": "deferred_package",
            "message_de": "Keine Paket-Zeilen für Vorbestellung.",
        }
        _persist_deferred_package_evidence(root, out)
        return out

    pol = load_policy(root)
    if not pol.get("enabled"):
        out = {
            "ok": False,
            "error": "DEFERRED_QUEUE_DISABLED",
            "mode": "deferred_package",
            "message_de": "Vorbestellungs-Warteschlange deaktiviert.",
        }
        _persist_deferred_package_evidence(root, out)
        return out

    status = r3_package_pending_status(root, want_syms)
    if status.get("complete"):
        open_de = format_next_open_de()
        out = {
            "ok": True,
            "already_queued": True,
            "mode": "deferred_package",
            "enqueued": int(status.get("pending_count") or 0),
            "skipped": 0,
            "orders_total": len(pkg_rows),
            "symbols": sorted(status.get("pending_symbols") or []),
            "message_de": (
                f"Paket bereits vorgemerkt ({status.get('pending_count')}/{status.get('want_count')}) "
                f"— US-Eröffnung {open_de}."
            ),
        }
        _persist_deferred_package_evidence(root, out)
        return out

    plan = _plan_for_deferred(root)
    if not plan:
        out = {
            "ok": False,
            "error": "NO_PLAN_EVIDENCE",
            "mode": "deferred_package",
            "message_de": "Kein Modell-Plan — Vorbestellung blockiert.",
        }
        _persist_deferred_package_evidence(root, out)
        return out

    plan_syms = _plan_symbols(plan)
    if plan_syms and not want_syms.issubset(plan_syms):
        foreign = sorted(want_syms - plan_syms)
        out = {
            "ok": False,
            "error": "SYMBOL_NOT_IN_PLAN",
            "mode": "deferred_package",
            "message_de": f"Symbole außerhalb Modell-Plan: {', '.join(foreign[:6])}",
        }
        _persist_deferred_package_evidence(root, out)
        return out

    min_trade = _min_trade_eur(root)
    results: List[Dict[str, Any]] = []
    enqueued_ids: List[str] = []
    try:
        for row in pkg_rows:
            sym = str(row.get("symbol") or "").upper()
            if not sym:
                results.append({"ok": False, "symbol": sym, "error": "NO_SYMBOL"})
                break
            notional = float(row.get("notional_eur") or 0)
            if notional < min_trade:
                results.append(
                    {
                        "ok": False,
                        "symbol": sym,
                        "error": "NOTIONAL_TOO_SMALL",
                        "notional_eur": notional,
                    }
                )
                break
            lim = limit_price_for_deferred(
                root,
                sym,
                quote_snapshot=quote_snapshot,
                fallback_eur=float(row.get("limit_price_eur") or 0),
            )
            if lim <= 0:
                results.append({"ok": False, "symbol": sym, "error": "NO_DEFERRED_LIMIT"})
                break
            r = enqueue_intent_for_symbol(
                root,
                plan=plan,
                symbol=sym,
                target_notional_eur=notional,
                limit_price_eur=lim,
                source=_ORDER_SOURCE,
                side=side_u,
            )
            results.append(r)
            if not r.get("ok"):
                break
            intent = r.get("intent") or {}
            iid = str(intent.get("intent_id") or "")
            if iid:
                enqueued_ids.append(iid)
    except Exception as exc:
        cancel_pending_intents(root, intent_ids=enqueued_ids)
        out = {
            "ok": False,
            "error": "DEFERRED_ENQUEUE_EXCEPTION",
            "atomic_abort": True,
            "mode": "deferred_package",
            "message_de": str(exc)[:160],
        }
        _persist_deferred_package_evidence(root, out)
        return out

    if len(results) != len(pkg_rows) or not all(r.get("ok") for r in results):
        cancel_pending_intents(root, intent_ids=enqueued_ids)
        skipped = [r for r in results if not r.get("ok")]
        out = {
            "ok": False,
            "atomic_abort": True,
            "partial": False,
            "mode": "deferred_package",
            "enqueued": 0,
            "skipped": len(skipped) or max(0, len(pkg_rows) - len(results)),
            "orders_total": len(pkg_rows),
            "symbols": [],
            "results": results,
            "message_de": (
                "Vorbestellung abgebrochen (atomar) — "
                + ", ".join(f"{r.get('symbol')} ({r.get('error')})" for r in skipped[:6])
                if skipped
                else "Vorbestellung abgebrochen — unvollständiges Paket."
            ),
        }
        _persist_deferred_package_evidence(root, out)
        return out

    enqueued = [r for r in results if r.get("ok")]
    syms = [str(r.get("symbol") or "") for r in enqueued if r.get("symbol")]
    open_de = format_next_open_de()
    out = {
        "ok": True,
        "partial": False,
        "mode": "deferred_package",
        "enqueued": len(enqueued),
        "skipped": 0,
        "orders_total": len(pkg_rows),
        "symbols": syms,
        "results": results,
        "message_de": (
            f"{len(enqueued)} Order(s) vorgemerkt für US-Eröffnung ({open_de}): "
            f"{', '.join(syms) or '—'}."
        ),
    }
    _persist_deferred_package_evidence(root, out)
    return out


def _try_execute_pending_r3_deferred(
    root: Path,
    rows: List[Dict[str, Any]],
    *,
    quote_snapshot: Dict[str, Any],
    precheck_ok: bool,
) -> Optional[Dict[str, Any]]:
    """Vorbestellung an T212 — nur bei Live-Kursen, Live-Submit und vollständigem Paket."""
    from execution.confirmed_live.us_equity_deferred_intents import (
        execute_pending_r3_deferred_intents,
        r3_package_pending_status,
    )

    if not precheck_ok or not _live_submit_ready(root):
        return None

    want = _package_row_symbols(rows, side="BUY")
    status = r3_package_pending_status(root, want)
    if not status.get("complete"):
        return None

    n = max(1, len(rows))
    lease = _grant_r3_lease(root, scope="R3_DEFERRED_PACKAGE", max_submissions=n + 5)
    if not lease.get("ok"):
        return {
            "ok": False,
            "error": lease.get("error"),
            "message_de": lease.get("message_de") or "GUI-Bestätigung fehlgeschlagen",
        }

    exec_out = execute_pending_r3_deferred_intents(root, symbols=want)
    ok_n = int(exec_out.get("executed") or 0)
    total_n = int(exec_out.get("orders_total") or 0)
    partial = bool(exec_out.get("partial"))
    return {
        "ok": bool(exec_out.get("ok")),
        "partial": partial,
        "mode": "deferred_execute",
        "execution_path_de": "r3_deferred_intents",
        "orders_submitted": ok_n,
        "orders_failed": int(exec_out.get("orders_failed") or 0),
        "orders_total": total_n,
        "notional_eur": round(
            sum(float(r.get("notional_eur") or 0) for r in rows if str(r.get("symbol", "")).upper() in want),
            2,
        ),
        "results": exec_out.get("results") or [],
        "message_de": (
            f"Vorbestellung ausgeführt: {ok_n}/{total_n} Orders an T212"
            if exec_out.get("ok")
            else (
                f"Teilausführung Vorbestellung: {ok_n}/{total_n}"
                if partial
                else f"Vorbestellung fehlgeschlagen — 0/{total_n} OK"
            )
        ),
        "quote_snapshot": quote_snapshot,
    }


def _persist_batch_result(root: Path, out: Dict[str, Any]) -> None:
    doc = {
        "schema_version": 1,
        "updated_at_utc": _utc_now(),
        "mode": out.get("mode"),
        "ok": bool(out.get("ok")),
        "partial": bool(out.get("partial")),
        "orders_submitted": out.get("orders_submitted"),
        "orders_deferred": out.get("orders_deferred"),
        "orders_total": out.get("orders_total"),
        "notional_eur": out.get("notional_eur"),
        "message_de": out.get("message_de"),
        "results": [
            {
                "symbol": r.get("symbol"),
                "ok": r.get("ok"),
                "error": (r.get("result") or {}).get("error") if isinstance(r.get("result"), dict) else r.get("error"),
                "message_de": r.get("message_de"),
            }
            for r in (out.get("results") or [])
        ],
    }
    atomic_write_json(root / _BATCH_EVIDENCE_REL, doc)


def _resolve_limit_price(
    root: Path,
    symbol: str,
    row: Dict[str, Any],
    *,
    quote_snapshot: Optional[Dict[str, Any]] = None,
) -> float:
    """Live-Kurs bevorzugen — gespeicherte Reeval-Preise nur als Fallback."""
    try:
        from execution.confirmed_live.us_equity_deferred_intents import limit_price_for_symbol

        snap = quote_snapshot
        if snap is None:
            from analytics.live_trading_operations import sync_broker_and_quotes

            sync = sync_broker_and_quotes(root, force_quotes=True)
            snap = sync.get("quote_snapshot") or {}
        live = float(limit_price_for_symbol(root, symbol, quote_snapshot=snap) or 0)
        if live > 0:
            return live
    except Exception:
        pass
    lim = float(row.get("limit_price_eur") or 0)
    return lim if lim > 0 else 0.0


def _grant_r3_lease(root: Path, *, scope: str, max_submissions: int) -> Dict[str, Any]:
    from execution.confirmed_live.gui_execution_confirmation import grant_execution_confirmation

    return grant_execution_confirmation(
        root,
        source=_ORDER_SOURCE,
        scope=scope,
        max_submissions=max_submissions,
        ttl_seconds=600,
        metadata={"surface": "r3_desktop"},
    )


def _execute_stock_row(
    root: Path,
    row: Dict[str, Any],
    *,
    side: str,
    quote_snapshot: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """T212-Submit für eine Optimum-Zeile (ohne Gate/Lease — Caller verantwortlich)."""
    root = Path(root)
    sym = str(row.get("symbol") or "").upper()
    side_u = str(side or row.get("side") or "BUY").upper()
    limit = _resolve_limit_price(root, sym, row, quote_snapshot=quote_snapshot)
    if limit <= 0:
        return {
            "ok": False,
            "error": "NO_LIMIT_PRICE",
            "symbol": sym,
            "message_de": f"Kein Kurs für {sym} — Internet/Kurse prüfen.",
        }

    from integrations.trading212.t212_instrument_mapper import MAPPING_TABLE
    from execution.confirmed_live.order_execution_style import resolve_order_execution_style

    meta = MAPPING_TABLE.get(sym) or {}
    t212_id = str(meta.get("provider_instrument_id") or f"{sym}_US_EQ")
    style = resolve_order_execution_style(root)
    notional = float(row.get("notional_eur") or 0)
    if side_u == "BUY":
        try:
            from analytics.r3_trading_functions import load_functions_policy

            min_trade = float(load_functions_policy(root).get("min_trade_eur") or 12.0)
        except Exception:
            min_trade = 12.0
        capped_rows = _enforce_no_all_in(
            [{**row, "side": "BUY"}],
            root=root,
            min_trade_eur=min_trade,
        )
        if capped_rows:
            notional = float(capped_rows[0].get("notional_eur") or notional)

    try:
        from analytics.r3_closed_loop import load_r3_account_for_engine

        acct = load_r3_account_for_engine(root)
        cash = float(acct.get("investable_eur") or acct.get("cash_eur") or 0)
    except Exception:
        cash = None

    if side_u == "SELL":
        from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_sell

        broker = _load_json(root / "evidence/pilot_day_trading_snapshot_latest.json").get("broker") or {}
        held = 0.0
        for pos in broker.get("positions") or []:
            if str(pos.get("ticker") or pos.get("symbol") or "").upper().replace(".US", "") == sym:
                try:
                    held = float(pos.get("quantity") or 0)
                except (TypeError, ValueError):
                    held = 0.0
                break
        result = submit_scaled_limit_sell(
            root,
            instrument=sym,
            t212_id=t212_id,
            target_notional_eur=notional,
            limit_price_eur=limit,
            sell_quantity=held if held > 0 else None,
            account_currency="EUR",
            dry_run=False,
            execution_style=style,
            order_source=_ORDER_SOURCE,
        )
    else:
        from execution.confirmed_live.order_auto_scale_submit import submit_scaled_limit_buy

        result = submit_scaled_limit_buy(
            root,
            instrument=sym,
            t212_id=t212_id,
            target_notional_eur=notional,
            limit_price_eur=limit,
            free_cash_eur=cash,
            account_currency="EUR",
            dry_run=False,
            execution_style=style,
            order_source=_ORDER_SOURCE,
        )

    return {
        "ok": bool(result.get("ok")),
        "symbol": sym,
        "side": side_u,
        "notional_eur": notional,
        "result": result,
        "message_de": result.get("user_message_de") or result.get("message_de") or "",
    }


def submit_r3_single_stock(
    root: Path,
    *,
    symbol: str,
    side: str,
    confirmed: bool = False,
) -> Dict[str, Any]:
    """Eine Aktie — Kauf oder Verkauf — nur nach R3-Bestätigung."""
    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(root, source=_ORDER_SOURCE, operation="single_stock")
    if not gate.get("allowed"):
        return {
            "ok": False,
            "mode": "r3_order_surface_required",
            "message_de": gate.get("message_de"),
        }
    if not confirmed:
        return {
            "ok": False,
            "error": "CONFIRMATION_REQUIRED",
            "message_de": "Bitte im Dialog bestätigen.",
        }

    from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

    auto_prepare_freigabe_for_desktop(root)

    row = _find_stock_row(root, symbol, side)
    if not row:
        return {
            "ok": False,
            "error": "STOCK_NOT_IN_OPTIMUM",
            "message_de": f"{symbol} nicht im Modell-Plan (pilot_investment_plan).",
        }

    precheck = _precheck_order_rows(root, [row], side=side)
    quote_snapshot = precheck.get("quote_snapshot") or {}

    if precheck.get("ok") and _live_submit_ready(root):
        lease = _grant_r3_lease(root, scope="R3_SINGLE", max_submissions=1)
        if not lease.get("ok"):
            return {
                "ok": False,
                "error": lease.get("error"),
                "message_de": lease.get("message_de") or "GUI-Bestätigung fehlgeschlagen",
            }
        exec_out = _execute_stock_row(
            root, row, side=side, quote_snapshot=quote_snapshot
        )
        refresh_stock_order_evidence(root)
        return {**exec_out, "mode": "single"}

    deferred = _enqueue_r3_package_deferred(root, [row], quote_snapshot=quote_snapshot, side=side)
    if deferred.get("ok"):
        refresh_stock_order_evidence(root)
        return {
            "ok": True,
            "mode": "deferred_single",
            "symbol": str(symbol).upper(),
            "message_de": deferred.get("message_de"),
            "deferred": deferred,
        }
    fail = (precheck.get("failures") or [{}])[0]
    return {
        "ok": False,
        "error": "PRECHECK_FAILED",
        "mode": "precheck_blocked",
        "message_de": (
            deferred.get("message_de")
            or f"{symbol}: Kein Kurs — Vorbestellung nicht möglich."
        ),
        "precheck": precheck,
        "symbol": fail.get("symbol") or symbol,
        "deferred": deferred,
    }


def submit_r3_initial_package(root: Path, *, confirmed: bool = False) -> Dict[str, Any]:
    """Initial Bestellung — ein Ausführungspfad: skalierte r3_stock_orders-Zeilen → T212."""
    root = Path(root)
    from analytics.r3_order_execution_gate import check_order_execution_allowed

    gate = check_order_execution_allowed(root, source=_ORDER_SOURCE, operation="initial_package")
    if not gate.get("allowed"):
        return {
            "ok": False,
            "mode": "r3_order_surface_required",
            "message_de": gate.get("message_de"),
        }
    if not confirmed:
        return {
            "ok": False,
            "error": "CONFIRMATION_REQUIRED",
            "message_de": "Gesamtpaket bitte bestätigen.",
        }

    from analytics.r3_freigabe import auto_prepare_freigabe_for_desktop

    auto_prepare_freigabe_for_desktop(root)
    from analytics.r3_freigabe import package_ready

    freigabe = package_ready(root, refresh_orders=False)
    if not freigabe.get("ready"):
        return {
            "ok": False,
            "error": "FREIGABE_NOT_READY",
            "message_de": str(freigabe.get("headline_de") or "Paket nicht freigegeben")[:160],
        }
    doc = refresh_stock_order_evidence(root)
    package = doc.get("initial_package") or freigabe.get("initial_package") or build_initial_package(root)

    buys = [r for r in (doc.get("stocks") or []) if str(r.get("side") or "").upper() == "BUY"]
    if not buys:
        return {
            "ok": False,
            "error": "NO_BUY_ROWS",
            "message_de": "Keine Kauf-Zeilen im Initial-Paket.",
        }

    precheck = _precheck_order_rows(root, buys, side="BUY")
    quote_snapshot = precheck.get("quote_snapshot") or {}

    deferred_exec = _try_execute_pending_r3_deferred(
        root, buys, quote_snapshot=quote_snapshot, precheck_ok=bool(precheck.get("ok"))
    )
    if deferred_exec is not None:
        deferred_exec["package"] = package
        _persist_batch_result(root, deferred_exec)
        refresh_stock_order_evidence(root)
        return deferred_exec

    if precheck.get("ok") and _live_submit_ready(root):
        n = max(1, len(buys))
        lease = _grant_r3_lease(root, scope="R3_INITIAL_PACKAGE", max_submissions=n + 5)
        if not lease.get("ok"):
            return {
                "ok": False,
                "error": lease.get("error"),
                "message_de": lease.get("message_de") or "GUI-Bestätigung fehlgeschlagen",
            }

        results: List[Dict[str, Any]] = []
        for row in buys:
            results.append(_execute_stock_row(root, row, side="BUY", quote_snapshot=quote_snapshot))

        ok_n = sum(1 for r in results if r.get("ok"))
        fail_n = len(results) - ok_n
        total_n = round(
            sum(float(r.get("notional_eur") or 0) for r in results if r.get("ok")),
            2,
        )
        partial = 0 < ok_n < len(results)
        out = {
            "ok": ok_n == len(results) and ok_n > 0,
            "partial": partial,
            "mode": "initial_package",
            "execution_path_de": "r3_stock_orders_batch",
            "package": package,
            "orders_submitted": ok_n,
            "orders_failed": fail_n,
            "orders_total": len(results),
            "notional_eur": total_n,
            "results": results,
            "message_de": (
                f"Initial-Paket: {ok_n}/{len(results)} Orders · {total_n:.0f} €"
                if ok_n == len(results)
                else (
                    f"Teilerfolg: {ok_n}/{len(results)} Orders · {total_n:.0f} € — Rest manuell prüfen"
                    if partial
                    else f"Initial-Paket fehlgeschlagen — 0/{len(results)} OK"
                )
            ),
        }
        _persist_batch_result(root, out)
        refresh_stock_order_evidence(root)
        return out

    deferred = _enqueue_r3_package_deferred(root, buys, quote_snapshot=quote_snapshot, side="BUY")
    total_n = round(sum(float(r.get("notional_eur") or 0) for r in buys), 2)
    if deferred.get("ok"):
        out = {
            "ok": True,
            "partial": False,
            "mode": "deferred_package",
            "execution_path_de": "r3_deferred_intents",
            "package": package,
            "orders_submitted": 0,
            "orders_deferred": int(deferred.get("enqueued") or 0),
            "orders_failed": 0,
            "orders_total": len(buys),
            "notional_eur": total_n,
            "deferred": deferred,
            "message_de": deferred.get("message_de"),
        }
        _persist_batch_result(root, out)
        refresh_stock_order_evidence(root)
        return out

    syms = ", ".join(str(f.get("symbol") or "?") for f in (precheck.get("failures") or [])[:4])
    out = {
        "ok": False,
        "partial": bool(deferred.get("partial")),
        "error": "PRECHECK_FAILED",
        "mode": "precheck_blocked",
        "package": package,
        "orders_deferred": int(deferred.get("enqueued") or 0),
        "orders_total": len(buys),
        "notional_eur": total_n,
        "message_de": deferred.get("message_de")
        or f"Vorcheck fehlgeschlagen — {syms} (Kurse prüfen, Seite neu laden).",
        "precheck": precheck,
        "deferred": deferred,
    }
    _persist_batch_result(root, out)
    return out


def handle_r3_order_request(root: Path, payload: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(payload.get("mode") or "single").strip().lower()
    confirmed = bool(payload.get("confirm") or payload.get("confirmed"))
    if mode in ("initial_package", "initial", "package"):
        return submit_r3_initial_package(root, confirmed=confirmed)
    return submit_r3_single_stock(
        root,
        symbol=str(payload.get("symbol") or ""),
        side=str(payload.get("side") or "BUY").upper(),
        confirmed=confirmed,
    )
