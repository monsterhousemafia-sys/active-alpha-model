"""Dashboard data and actions — wraps live_trading_operations + T212 APIs only."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_DASHBOARD_REL = Path("live_pilot/confirmed_execution/live_trading_dashboard.txt")


def _venv_ok(root: Path) -> bool:
    from aa_paths import venv_python_ok

    return venv_python_ok(root)


def _traffic(
    status: Dict[str, Any],
    guard: Dict[str, Any],
    broker: Dict[str, Any],
    *,
    day_warnings: Optional[Dict[str, Any]] = None,
) -> str:
    from analytics.pilot_trading_day_warnings import warnings_traffic_level

    if day_warnings:
        level = warnings_traffic_level(day_warnings)
        if level == "ROT":
            return "ROT"
    if not guard.get("champion_ok") or not guard.get("signals_ok"):
        return "ROT"
    if broker.get("error") or not broker.get("credentials_configured", True):
        return "GELB"
    if status.get("is_due"):
        return "GELB"
    if day_warnings and int(day_warnings.get("warn_count") or 0) > 0:
        return "GELB"
    return "GRUEN"


def _attach_day_warnings(root: Path, snap: Dict[str, Any]) -> Dict[str, Any]:
    from analytics.pilot_trading_day_warnings import collect_trading_day_warnings

    report = collect_trading_day_warnings(root, snap=snap)
    snap["day_warnings"] = report
    snap["traffic"] = _traffic(
        snap.get("rebalance_status") or {},
        snap.get("guard") or {},
        snap.get("broker") or {},
        day_warnings=report,
    )
    if report.get("must_resolve_before_trading"):
        snap["today_action_de"] = str(report.get("headline_de") or snap.get("today_action_de"))
    return snap


def _today_action_de(status: Dict[str, Any]) -> str:
    rec = str(status.get("recommendation") or "")
    if rec in ("REBALANCE_DUE", "REBALANCE_DUE_NO_HISTORY"):
        return "REBALANCE FÄLLIG: Schritt ② ausführen (Signal + Orders an T212)."
    return "NUR MARK: Schritt ① täglich — Rebalance erst wenn Zähler voll (wie Paper)."


def _refresh_snapshot_via_facade(root: Path, *, force: bool = True) -> Dict[str, Any]:
    """Full Pilot Day Trading refresh (playbook + deferred + reeval)."""
    from analytics.live_trading_operations import load_policy, rebalance_status
    from analytics.pilot_integrated_refresh import run_integrated_refresh
    from execution.confirmed_live.live_trading_enablement import is_live_trading_enabled
    from execution.confirmed_live.trading_mode_policy import trading_readiness
    from execution.confirmed_live.live_trading_enablement import live_submission_allowed
    from execution.confirmed_live.p17_review_mode_guard import review_mode_active
    from aa_sector_reference import format_sector_dashboard_status
    from market.champion_quote_gate import require_champion_quote_coverage, symbols_from_orders
    from analytics.live_trading_operations import build_rebalance_orders

    result = run_integrated_refresh(root, force=force, auto_enqueue=False)
    broker = dict(result.broker or {})
    guard_d = dict(result.champion_guard or {})
    plan = dict(result.investment_plan or {})
    reeval = dict(result.reevaluation or {})
    status = rebalance_status(root)
    traffic = _traffic(status, guard_d, broker)
    today_action = _today_action_de(status)
    ts = result.trading_snapshot
    playbook = ts.playbook if hasattr(ts, "playbook") else {}
    deferred = ts.deferred_summary if hasattr(ts, "deferred_summary") else {}
    if playbook.get("headline_de"):
        today_action = str(playbook.get("headline_de"))
    next_action = str(playbook.get("next_action") or "")
    if next_action and next_action not in ("WAIT", "NO_TRADE", "REFRESH"):
        today_action = f"{today_action} [{next_action}]"
    cash = float(broker.get("cash_eur") or 0)
    quote_snapshot = dict(result.market_prices or {})
    pol = load_policy(root)
    orders = build_rebalance_orders(
        root,
        broker=broker,
        reevaluation=reeval,
        quote_snapshot=quote_snapshot,
        pol=pol,
    )
    portfolio_orders = summarize_portfolio_orders(orders, signal_date=str(plan.get("signal_date") or ""))
    buy_symbols = symbols_from_orders(orders)
    quote_gate = require_champion_quote_coverage(
        root,
        symbols=buy_symbols if buy_symbols else None,
        quote_snapshot=quote_snapshot,
        refresh_if_stale=False,
    )
    portfolio_orders["quote_coverage"] = quote_gate
    portfolio_orders["quote_coverage_label_de"] = quote_gate.get("quote_coverage_label_de", "—")
    portfolio_orders["quote_coverage_ok"] = bool(quote_gate.get("ok"))
    readiness = trading_readiness(root)
    readiness["orders_allowed"] = live_submission_allowed(root)
    readiness["review_mode_active"] = review_mode_active()
    snap = {
        "traffic": traffic,
        "sector_status": format_sector_dashboard_status(root),
        "today_action_de": today_action,
        "portfolio_orders": portfolio_orders,
        "quote_coverage": quote_gate,
        "rebalance_status": status,
        "guard": guard_d,
        "broker": broker,
        "plan": plan,
        "prediction_meta": plan.get("prediction_meta") or {},
        "eod_switch": {},
        "prediction_gate": {},
        "reevaluation": reeval,
        "deferred": deferred,
        "playbook": playbook,
        "day_trading_snapshot": ts.as_dict() if hasattr(ts, "as_dict") else {},
        "refresh_status": result.refresh_status,
        "live_enabled": is_live_trading_enabled(root),
        "trading_readiness": readiness,
        "policy": pol,
        "n_positions": len(broker.get("positions") or []),
        "venv_ok": _venv_ok(root),
        "model_script_ok": (root / "active_alpha_model.py").is_file(),
    }
    _attach_learning(root, snap, quote_snapshot=quote_snapshot, broker=broker)
    _attach_day_warnings(root, snap)
    write_dashboard_txt(root, snap)
    try:
        from analytics.snapshot_freshness import mark_snapshot_fresh

        mark_snapshot_fresh(root, source="dashboard_snapshot")
    except Exception:
        pass
    return snap


def _attach_learning(
    root: Path,
    snap: Dict[str, Any],
    *,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    broker: Optional[Dict[str, Any]] = None,
) -> None:
    from analytics.public_learning_kernel import (
        learning_summary_for_dashboard,
        run_capture_only,
    )

    try:
        cap = run_capture_only(root, live_snapshot=quote_snapshot, broker=broker)
        snap["learning_capture"] = cap.get("readiness") or {}
    except Exception as exc:
        snap["learning_capture"] = {"error": str(exc)[:120]}
    report_path = root / "evidence/public_learning_report_latest.json"
    if report_path.is_file():
        try:
            import json

            report = json.loads(report_path.read_text(encoding="utf-8"))
            snap["public_learning"] = learning_summary_for_dashboard(report)
        except Exception:
            snap["public_learning"] = {}
    else:
        snap["public_learning"] = {
            "headline_de": "Noch kein Lernreport — python3 tools/ai_kernel.py learn",
            "stage_de": "Sportwagen",
        }


def _refresh_snapshot_impl(root: Path, *, force_quotes: bool = True, force_sync: bool = True) -> Dict[str, Any]:
    root = Path(root)
    if sys.platform.startswith("linux"):
        return _refresh_snapshot_via_facade(root, force=force_quotes or force_sync)
    try:
        from integrations.trading212.t212_execution_profile_bootstrap import ensure_execution_profile_ready

        ensure_execution_profile_ready(root)
    except Exception:
        pass
    from analytics.champion_runtime_guard import verify_champion_runtime
    from analytics.live_trading_operations import load_policy, rebalance_status, sync_broker_and_quotes
    from analytics.pilot_investment_plan import build_investment_plan
    from analytics.pilot_portfolio_reevaluation import evaluate_live_portfolio_vs_champion
    from analytics.prediction_operations import (
        ensure_prediction_before_orders,
        evaluate_prediction_readiness_for_orders,
        maybe_run_eod_prediction_switch,
        plan_metadata,
    )
    from execution.confirmed_live.live_trading_enablement import is_live_trading_enabled
    from execution.confirmed_live.us_equity_deferred_intents import load_deferred_summary
    from aa_sector_reference import format_sector_dashboard_status

    guard = verify_champion_runtime(root)
    guard_d = guard.as_dict()
    status = rebalance_status(root)

    broker: Dict[str, Any] = {}
    try:
        from integrations.trading212.t212_readonly_connection_service import load_cached_broker_status

        cached = load_cached_broker_status(root)
        if cached and cached.cash_eur is not None:
            broker = {
                "cash_eur": float(cached.cash_eur),
                "positions": cached.positions or [],
                "credentials_configured": True,
                "cached": True,
                "last_sync_utc": cached.last_successful_sync_utc,
            }
    except Exception:
        pass

    sync = sync_broker_and_quotes(root, force_quotes=force_quotes, force_sync=force_sync)
    live_broker = dict(sync.get("broker") or {})
    if live_broker.get("cash_eur") is not None or live_broker.get("error"):
        broker = live_broker
    quote_snapshot = sync.get("quote_snapshot") or {}
    cash = float(broker.get("cash_eur") or 0)
    eod_switch = maybe_run_eod_prediction_switch(root, force=False)
    pred_gate = evaluate_prediction_readiness_for_orders(root)
    if not pred_gate.get("ok") and not pred_gate.get("skipped"):
        pred_gate = ensure_prediction_before_orders(root, auto_run=True)
    plan = build_investment_plan(root, cash)
    reeval = evaluate_live_portfolio_vs_champion(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=guard_d,
    )
    deferred = load_deferred_summary(root)
    try:
        from execution.confirmed_live.trading_mode_policy import trading_readiness
        from execution.confirmed_live.live_trading_enablement import live_submission_allowed
        from execution.confirmed_live.p17_review_mode_guard import review_mode_active

        readiness = trading_readiness(root)
        readiness["orders_allowed"] = live_submission_allowed(root)
        readiness["review_mode_active"] = review_mode_active()
    except Exception as exc:
        readiness = {"ready": False, "error": str(exc)[:200]}
    positions = broker.get("positions") or []
    traffic = _traffic(status, guard_d, broker)
    today_action = _today_action_de(status)
    pol = load_policy(root)
    from analytics.live_trading_operations import build_rebalance_orders

    orders = build_rebalance_orders(
        root,
        broker=broker,
        reevaluation=reeval,
        quote_snapshot=quote_snapshot,
        pol=pol,
    )
    portfolio_orders = summarize_portfolio_orders(orders, signal_date=str(plan.get("signal_date") or ""))
    from market.champion_quote_gate import require_champion_quote_coverage, symbols_from_orders

    buy_symbols = symbols_from_orders(orders)
    quote_gate = require_champion_quote_coverage(
        root,
        symbols=buy_symbols if buy_symbols else None,
        quote_snapshot=quote_snapshot,
        refresh_if_stale=False,
    )
    portfolio_orders["quote_coverage"] = quote_gate
    portfolio_orders["quote_coverage_label_de"] = quote_gate.get("quote_coverage_label_de", "—")
    portfolio_orders["quote_coverage_ok"] = bool(quote_gate.get("ok"))
    sector_status = format_sector_dashboard_status(root)
    snap = {
        "traffic": traffic,
        "sector_status": sector_status,
        "today_action_de": today_action,
        "portfolio_orders": portfolio_orders,
        "quote_coverage": quote_gate,
        "rebalance_status": status,
        "guard": guard_d,
        "broker": broker,
        "plan": plan,
        "prediction_meta": plan.get("prediction_meta") or plan_metadata(
            root,
            available_cash_eur=cash,
            investable_eur=float(plan.get("investable_eur") or 0),
        ),
        "eod_switch": eod_switch,
        "prediction_gate": pred_gate,
        "reevaluation": reeval,
        "deferred": deferred,
        "live_enabled": is_live_trading_enabled(root),
        "trading_readiness": readiness,
        "policy": load_policy(root),
        "n_positions": len(positions),
        "venv_ok": _venv_ok(root),
        "model_script_ok": (root / "active_alpha_model.py").is_file(),
    }
    _attach_learning(root, snap, quote_snapshot=quote_snapshot, broker=broker)
    _attach_day_warnings(root, snap)
    write_dashboard_txt(root, snap)
    try:
        from analytics.snapshot_freshness import mark_snapshot_fresh

        mark_snapshot_fresh(root, source="dashboard_snapshot")
    except Exception:
        pass
    return snap


def refresh_snapshot(
    root: Path,
    *,
    force_quotes: bool = True,
    force_sync: bool = True,
    timeout_s: float = 90.0,
) -> Dict[str, Any]:
    """Load dashboard state; never block the UI thread (caller runs in worker)."""
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(_refresh_snapshot_impl, root, force_quotes=force_quotes, force_sync=force_sync)
        try:
            return fut.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            partial: Dict[str, Any] = {}
            try:
                partial = _refresh_snapshot_impl(root, force_quotes=False, force_sync=False)
            except Exception:
                pass
            if partial and not partial.get("broker", {}).get("error"):
                partial["warning"] = "Teil-Aktualisierung (Timeout) — «Verbindung laden» für frisches Konto."
                return partial
            return {
                "error": "Konto-Aktualisierung dauert zu lange — Sie können trotzdem alle Schritte starten.",
                "traffic": "GELB",
                "today_action_de": "Aktualisieren erneut oder Schritt ①/② direkt ausführen.",
                "rebalance_status": {},
                "guard": {},
                "broker": {"error": "timeout"},
                "plan": {},
                "deferred": {},
                "live_enabled": False,
                "trading_readiness": {"ready": False, "checks": []},
                "policy": {},
                "n_positions": 0,
                "venv_ok": _venv_ok(root),
                "model_script_ok": (root / "active_alpha_model.py").is_file(),
            }


def write_dashboard_txt(root: Path, snap: Dict[str, Any]) -> Path:
    root = Path(root)
    status = snap.get("rebalance_status") or {}
    broker = snap.get("broker") or {}
    guard = snap.get("guard") or {}
    plan = snap.get("plan") or {}
    reeval = snap.get("reevaluation") or {}
    deferred = snap.get("deferred") or {}
    lines = [
        "Active Alpha Live Trading - Dashboard",
        "=====================================",
        "",
        f"status: {snap.get('traffic', '-')}",
        f"today_action: {snap.get('today_action_de', '-')}",
        f"live_trading_enabled: {snap.get('live_enabled')}",
        "",
        "Rebalance schedule (Paper-parity)",
        "--------------------------------",
        f"rebalance_every_recorded_trading_days: {status.get('rebalance_every_trading_days')}",
        f"last_rebalance_date: {status.get('last_rebalance_date')}",
        f"recorded_mark_days_since_rebalance: {status.get('recorded_trading_days_since_rebalance')}",
        f"days_remaining_until_due: {status.get('days_remaining')}",
        f"recommendation: {status.get('recommendation')}",
        f"summary: {status.get('summary_de', '')}",
        "",
        "Sector reference",
        "----------------",
        f"sector_summary: {(snap.get('sector_status') or {}).get('summary_de', '-')}",
        f"sector_traffic: {(snap.get('sector_status') or {}).get('traffic', '-')}",
        "",
        "T212 Konto",
        "----------",
        f"cash_eur: {broker.get('cash_eur', '-')}",
        f"n_positions: {snap.get('n_positions', 0)}",
        f"champion_ok: {guard.get('champion_ok')}",
        f"signals_ok: {guard.get('signals_ok')}",
        f"model_symbols: {len(plan.get('allocations') or [])}",
        f"reeval_urgency: {reeval.get('urgency')}",
        f"trade_required: {reeval.get('trade_required')}",
        "",
        "US order queue",
        "---------------",
        f"pending: {deferred.get('pending_count', 0)}",
        f"queue_status: {deferred.get('status_de', '-')}",
        "",
        "Pre-session warnings",
        "--------------------",
        f"warning_severity: {(snap.get('day_warnings') or {}).get('severity', '-')}",
        f"warning_headline: {(snap.get('day_warnings') or {}).get('headline_de', '-')}",
        f"critical_count: {(snap.get('day_warnings') or {}).get('critical_count', 0)}",
        "",
        "KI learning",
        "-----------",
        f"learning_score: {(snap.get('public_learning') or {}).get('score', '-')}",
        f"learning_grade: {(snap.get('public_learning') or {}).get('grade', '-')}",
        f"learning_stage: {(snap.get('public_learning') or {}).get('stage_de', '-')}",
        f"ic_pearson: {(snap.get('public_learning') or {}).get('ic_pearson', '-')}",
        f"live_mature: {(snap.get('public_learning') or {}).get('live_mature', 0)}",
    ]
    dw = snap.get("day_warnings") or {}
    for w in (dw.get("warnings") or [])[:8]:
        lines.append(f"  [{w.get('severity')}] {w.get('code')}: {w.get('title_de')}")
    lines.extend(
        [
            "",
            "Steps (wie Paper)",
            "-----------------",
            "① 1_live_daily_sync.bat  — täglicher Mark",
            "② 2_live_rebalance_when_due.bat — Signal + Rebalance",
            "③ Signal — nur Modell-CSV aktualisieren",
        ]
    )
    path = root / _DASHBOARD_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def action_sync_broker(root: Path) -> Dict[str, Any]:
    from analytics.live_trading_operations import sync_broker_and_quotes

    sync = sync_broker_and_quotes(root, force_quotes=True, force_sync=True)
    broker = sync.get("broker") or {}
    ok = broker.get("credentials_configured") and broker.get("cash_eur") is not None and not broker.get("error")
    cash = broker.get("cash_eur")
    msg = f"Verbunden — verfügbar: {float(cash):,.2f} €." if ok else str(
        broker.get("error") or broker.get("warning") or "Sync fehlgeschlagen"
    )[:200]
    return {"ok": ok, "sync": sync, "message_de": msg, "broker": broker}


def action_daily_mark(root: Path) -> Dict[str, Any]:
    from analytics.live_trading_operations import run_daily_live_cycle
    from execution.confirmed_live.trading_mode_policy import get_trading_mode, trading_readiness

    armed = get_trading_mode(root) == "ai_assisted" and trading_readiness(root).get("ready")
    out = run_daily_live_cycle(root, armed_auto=armed, force_rebalance=False)
    out.setdefault("message_de", out.get("summary_de", ""))
    return out


def action_reset_t212_buy_gate(root: Path) -> Dict[str, Any]:
    from integrations.trading212.t212_order_readiness import reset_stock_buy_gate

    doc = reset_stock_buy_gate(root, reason="live_dashboard")
    return {
        "ok": True,
        "message_de": "T212-Kaufblock zurückgesetzt — nach Testkauf in der App erneut Rebalance versuchen.",
        "gate": doc,
    }


def set_order_execution_type(root: Path, order_execution_type: str) -> Dict[str, Any]:
    from execution.confirmed_live.order_execution_style import set_order_execution_style

    return set_order_execution_style(root, order_execution_type)


def summarize_portfolio_orders(
    orders: List[Dict[str, Any]],
    *,
    signal_date: str = "",
) -> Dict[str, Any]:
    """Human-readable champion portfolio order wave (all symbols, not single pick)."""
    buys = [o for o in orders if str(o.get("side") or "").upper() == "BUY"]
    sells = [o for o in orders if str(o.get("side") or "").upper() == "SELL"]
    lines: List[str] = []
    for row in orders[:25]:
        sym = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "BUY").upper()
        try:
            eur = float(row.get("notional_eur") or 0)
        except (TypeError, ValueError):
            eur = 0.0
        lines.append(f"  {side} {sym}  ~{eur:,.0f} €")
    if len(orders) > 25:
        lines.append(f"  … +{len(orders) - 25} weitere")
    total_buy = sum(float(o.get("notional_eur") or 0) for o in buys)
    if not orders:
        summary = "Portfolio am Ziel — keine neuen Orders nötig."
    else:
        summary = (
            f"Champion-Portfolio: {len(buys)} Kauf/Käufe, {len(sells)} Verkauf/Verkäufe "
            f"({len(orders)} Orders, Käufe ~{total_buy:,.0f} €)."
        )
    return {
        "order_count": len(orders),
        "n_buys": len(buys),
        "n_sells": len(sells),
        "total_buy_eur": total_buy,
        "lines_de": lines,
        "summary_de": summary,
        "has_orders": len(orders) > 0,
        "signal_date": str(signal_date or "")[:10],
    }


def action_execute_champion_portfolio(
    root: Path,
    *,
    run_signal_first: bool = False,
) -> Dict[str, Any]:
    """Send full champion rebalance wave to T212 (not a single-stock pick)."""
    from analytics.champion_runtime_guard import verify_champion_runtime
    from analytics.live_trading_operations import execute_live_rebalance

    guard = verify_champion_runtime(root).as_dict()
    return execute_live_rebalance(
        root,
        force=True,
        run_signal_before=run_signal_first,
        source="LIVE_DASHBOARD_PORTFOLIO",
        champion_guard=guard,
    )


def action_rebalance(root: Path, *, force: bool = False) -> Dict[str, Any]:
    from analytics.live_trading_operations import execute_live_rebalance, rebalance_status

    if not force:
        st = rebalance_status(root)
        if not st.get("is_due"):
            return {
                "ok": False,
                "message_de": st.get("summary_de", "Kein Rebalance fällig — nur Mark."),
                "rebalance_status": st,
            }
    from analytics.champion_runtime_guard import verify_champion_runtime

    guard = verify_champion_runtime(root).as_dict()
    return execute_live_rebalance(
        root,
        force=True,
        source="LIVE_DASHBOARD_REBALANCE",
        champion_guard=guard,
    )


def action_signal_update(root: Path) -> Dict[str, Any]:
    from analytics.live_trading_operations import run_champion_signal_update

    return run_champion_signal_update(root)


def action_enable_live(root: Path) -> Dict[str, Any]:
    from execution.confirmed_live.live_trading_enablement import ensure_live_trading_enabled

    doc = ensure_live_trading_enabled(root, changed_by="live_dashboard")
    return {"ok": True, "ack": doc}


def portfolio_table_rows(snap: Dict[str, Any], *, max_rows: int = 40) -> List[Dict[str, Any]]:
    reeval = snap.get("reevaluation") or {}
    actions = {str(r.get("symbol") or "").upper(): r for r in (reeval.get("recommended_actions") or [])}
    plan_rows = (snap.get("plan") or {}).get("allocations") or []
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for alloc in plan_rows:
        sym = str(alloc.get("symbol") or "").upper()
        if not sym or sym in seen:
            continue
        seen.add(sym)
        act = actions.get(sym) or {}
        rows.append(
            {
                "symbol": sym,
                "target_eur": float(alloc.get("target_eur") or 0),
                "weight_pct": float(alloc.get("model_weight_pct") or 0),
                "current_eur": float(act.get("current_eur") or 0),
                "gap_eur": float(act.get("gap_eur") or 0),
                "action_de": str(act.get("action_de") or "—"),
            }
        )
        if len(rows) >= max_rows:
            break
    for sym, act in actions.items():
        if sym in seen:
            continue
        rows.append(
            {
                "symbol": sym,
                "target_eur": float(act.get("target_eur") or 0),
                "weight_pct": 0.0,
                "current_eur": float(act.get("current_eur") or 0),
                "gap_eur": float(act.get("gap_eur") or 0),
                "action_de": str(act.get("action_de") or "—"),
            }
        )
        if len(rows) >= max_rows:
            break
    return rows
