"""Walk-forward mirror live execution — daily mark, rebalance every N trading days."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

from aa_safe_io import atomic_write_json

_STATE_REL = Path("live_pilot/confirmed_execution/walkforward_mirror_state.json")
_EVIDENCE_REL = Path("evidence/walkforward_mirror_latest.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today_iso() -> str:
    return date.today().isoformat()


def default_policy() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "enabled": True,
        "execution_mode": "walkforward_mirror",
        "rebalance_every_trading_days": 1,
        "daily_mark_enabled": True,
        "auto_enqueue_on_rebalance_due": True,
        "auto_execute_when_us_open": True,
        "min_trade_eur": 12.0,
        "min_weight_gap_pct": 0.5,
        "cash_buffer_pct": 5.0,
        "max_symbols": 15,
    }


def load_policy(root: Path) -> Dict[str, Any]:
    from analytics.pilot_day_trading_policy import policy_section

    return policy_section(Path(root), "walkforward_mirror")


def _state_path(root: Path) -> Path:
    p = Path(root) / _STATE_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load_state(root: Path) -> Dict[str, Any]:
    path = _state_path(root)
    if not path.is_file():
        return {
            "schema_version": 1,
            "mark_dates": [],
            "last_rebalance_date": "",
            "recorded_trading_days_since_rebalance": 0,
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {
            "schema_version": 1,
            "mark_dates": [],
            "last_rebalance_date": "",
            "recorded_trading_days_since_rebalance": 0,
        }


def save_state(root: Path, state: Dict[str, Any]) -> Path:
    state["updated_at_utc"] = _utc_now()
    return atomic_write_json(_state_path(root), state)


def rebalance_status(root: Path, *, pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Trading-day counter like paper_output/next_rebalance_due.txt (app-run days)."""
    pol = pol or load_policy(root)
    every = int(max(1, pol.get("rebalance_every_trading_days") or 5))
    state = load_state(root)
    recorded = int(state.get("recorded_trading_days_since_rebalance") or 0)
    last_rb = str(state.get("last_rebalance_date") or "")[:10]
    remaining = max(0, every - recorded)
    due = recorded >= every
    rec = "REBALANCE_DUE" if due else "MARK_TO_MARKET_ONLY"
    if not state.get("mark_dates"):
        rec = "REBALANCE_DUE_NO_HISTORY"
        due = True
    return {
        "rebalance_every_trading_days": every,
        "last_rebalance_date": last_rb or "-",
        "recorded_trading_days_since_rebalance": recorded,
        "days_remaining": remaining,
        "is_due": bool(due),
        "recommendation": rec,
        "last_mark_date": str((state.get("mark_dates") or [""])[-1])[:10] if state.get("mark_dates") else "-",
        "summary_de": (
            f"Walk-Forward-Mirror: Rebalance fällig ({recorded}/{every} Handelstage)."
            if due
            else f"Täglicher Mark OK — nächste Rebalance in {remaining} Handelstag(en) ({recorded}/{every})."
        ),
    }


def record_daily_mark(root: Path, *, pol: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Record one trading day when the app runs (paper-style daily mark)."""
    pol = pol or load_policy(root)
    if not pol.get("enabled") or not pol.get("daily_mark_enabled", True):
        return {"recorded": False, "reason": "DISABLED"}
    state = load_state(root)
    today = _today_iso()
    marks: List[str] = [str(d)[:10] for d in (state.get("mark_dates") or [])]
    if today in marks:
        return {"recorded": False, "reason": "ALREADY_MARKED_TODAY", "today": today}
    marks.append(today)
    state["mark_dates"] = marks[-400:]
    state["recorded_trading_days_since_rebalance"] = int(state.get("recorded_trading_days_since_rebalance") or 0) + 1
    save_state(root, state)
    return {
        "recorded": True,
        "today": today,
        "status": rebalance_status(root, pol=pol),
    }


def _held_shares(broker: Mapping[str, Any]) -> Dict[str, float]:
    from analytics.human_vs_base_comparison import _position_symbol

    out: Dict[str, float] = {}
    for pos in broker.get("positions") or []:
        sym = _position_symbol(pos if isinstance(pos, dict) else {})
        if not sym:
            continue
        try:
            q = float(pos.get("quantity") or 0)
        except (TypeError, ValueError):
            q = 0.0
        if q > 0:
            out[sym] = q
    return out


def build_rebalance_orders(
    root: Path,
    *,
    broker: Mapping[str, Any],
    reevaluation: Mapping[str, Any],
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    pol: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Full portfolio delta vs champion — sells first, then buys.
    Uses reevaluation rows when present; otherwise champion targets vs holdings.
    """
    pol = pol or load_policy(root)
    min_eur = float(pol.get("min_trade_eur") or 12.0)
    min_gap_pct = float(pol.get("min_weight_gap_pct") or 0.5)

    rows = list(reevaluation.get("recommended_actions") or reevaluation.get("actions") or [])
    if not rows:
        return []

    orders: List[Dict[str, Any]] = []
    for row in rows:
        code = str(row.get("action_code") or "").upper()
        if code in ("HALTEN", "HOLD", ""):
            continue
        gap = float(row.get("gap_eur") or 0)
        sym = str(row.get("symbol") or "").upper()
        if not sym or abs(gap) < min_eur:
            continue
        drift = abs(float(row.get("weight_gap_pct") or row.get("drift_pct") or 0))
        if drift < min_gap_pct and abs(gap) < min_eur * 2:
            continue
        side = "SELL" if gap < 0 or code in ("REDUZIEREN", "ABBAUEN", "VERKAUFEN") else "BUY"
        notional = round(abs(gap), 2)
        orders.append(
            {
                "symbol": sym,
                "side": side,
                "notional_eur": notional,
                "gap_eur": gap,
                "action_code": code,
                "priority_score": float(row.get("priority_score") or 0),
            }
        )

    held_shares = _held_shares(broker)
    sells = sorted([o for o in orders if o["side"] == "SELL"], key=lambda x: -x["priority_score"])
    buys = sorted([o for o in orders if o["side"] == "BUY"], key=lambda x: -x["priority_score"])
    ordered = sells + buys
    for o in ordered:
        sym = o["symbol"]
        if o["side"] == "SELL":
            if sym in held_shares:
                o["held_quantity"] = held_shares[sym]
            elif quote_snapshot:
                pass
        if quote_snapshot:
            from execution.confirmed_live.us_equity_deferred_intents import limit_price_for_symbol

            px = limit_price_for_symbol(root, sym, quote_snapshot=quote_snapshot)
            if px > 0:
                o["limit_price_eur"] = px
    return ordered


def note_rebalance_completed(root: Path) -> Dict[str, Any]:
    state = load_state(root)
    state["last_rebalance_date"] = _today_iso()
    state["recorded_trading_days_since_rebalance"] = 0
    save_state(root, state)
    return rebalance_status(root)


def run_walkforward_mirror_tick(
    root: Path,
    *,
    broker: Optional[Mapping[str, Any]] = None,
    reevaluation: Optional[Mapping[str, Any]] = None,
    quote_snapshot: Optional[Mapping[str, Any]] = None,
    champion_guard: Optional[Mapping[str, Any]] = None,
    armed_auto: bool = False,
) -> Dict[str, Any]:
    """Daily mark + optional auto rebalance wave when due."""
    root = Path(root)
    pol = load_policy(root)
    out: Dict[str, Any] = {
        "mode": "walkforward_mirror",
        "generated_at_utc": _utc_now(),
        "policy_enabled": bool(pol.get("enabled")),
    }
    if not pol.get("enabled"):
        out["status"] = "DISABLED"
        out["summary_de"] = "Walk-Forward-Mirror deaktiviert."
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    mark = record_daily_mark(root, pol=pol)
    out["daily_mark"] = mark
    status = rebalance_status(root, pol=pol)
    out["rebalance_status"] = status
    out["summary_de"] = status.get("summary_de", "")

    guard = champion_guard or {}
    if not guard.get("champion_ok", True) or not guard.get("signals_ok", True):
        out["status"] = "BLOCKED_GUARD"
        out["summary_de"] = "Champion/Signale blockiert — kein Walk-Forward-Rebalance."
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    if not status.get("is_due"):
        out["status"] = "MARK_ONLY"
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    out["status"] = "REBALANCE_DUE"
    if not broker:
        out["summary_de"] = "Rebalance fällig — zuerst Broker sync (Aktualisieren)."
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    reeval = reevaluation or {}
    orders = build_rebalance_orders(
        root, broker=broker, reevaluation=reeval, quote_snapshot=quote_snapshot, pol=pol
    )
    out["orders_planned"] = len(orders)
    out["orders"] = orders[:20]

    if not orders:
        out["summary_de"] = "Rebalance fällig — keine ausführbaren Deltas (Hürden/Drift)."
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    if not pol.get("auto_enqueue_on_rebalance_due"):
        out["summary_de"] = (
            f"Rebalance fällig — {len(orders)} Order(s) geplant. «Order ausführen» oder Auto-US-Eröffnung."
        )
        atomic_write_json(root / _EVIDENCE_REL, out)
        return out

    from analytics.pilot_investment_plan import build_investment_plan

    plan = build_investment_plan(root, float(broker.get("cash_eur") or 0))
    from execution.confirmed_live.us_equity_deferred_intents import (
        enqueue_walkforward_rebalance_orders,
        process_deferred_intents_if_due,
        try_execute_walkforward_rebalance_now,
    )

    if armed_auto and pol.get("auto_execute_when_us_open", True):
        exec_result = try_execute_walkforward_rebalance_now(
            root,
            orders=orders,
            plan=plan,
            quote_snapshot=quote_snapshot,
            broker=broker,
            source="WALKFORWARD_REBALANCE_AUTO",
        )
        out["execution"] = exec_result
        if exec_result.get("rebalance_completed"):
            out["rebalance_status"] = note_rebalance_completed(root)
    else:
        enq = enqueue_walkforward_rebalance_orders(
            root,
            orders=orders,
            plan=plan,
            quote_snapshot=quote_snapshot,
            source="WALKFORWARD_REBALANCE_DUE",
        )
        out["enqueue"] = enq
        if enq.get("ok"):
            out["rebalance_status"] = note_rebalance_completed(root)
        if pol.get("auto_execute_when_us_open") and armed_auto:
            out["deferred_process"] = process_deferred_intents_if_due(root)

    sells = sum(1 for o in orders if o.get("side") == "SELL")
    buys = sum(1 for o in orders if o.get("side") == "BUY")
    out["summary_de"] = (
        f"Rebalance fällig — {sells} Verkauf(e), {buys} Kauf(e) "
        f"({'Auto' if armed_auto else 'vorgemerkt'})."
    )
    atomic_write_json(root / _EVIDENCE_REL, out)
    return out
