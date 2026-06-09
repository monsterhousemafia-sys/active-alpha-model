"""Facade — one refresh cycle for US day trading (UI + virtual tests)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from aa_safe_io import atomic_write_json
from analytics.pilot_day_trading_policy import load_unified_policy, policy_section

_EVIDENCE_REL = Path("evidence/pilot_day_trading_snapshot_latest.json")
_PLAN_EVIDENCE = Path("evidence/pilot_investment_plan_latest.json")


class DayTradingSnapshotError(RuntimeError):
    """Kritischer Day-Trading-Fehler — Pipeline fail-closed."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def us_session_open() -> bool:
    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    return bool(us_equity_regular_session_open_now().get("open"))


def effective_quote_refresh_seconds(root: Path) -> int:
    from analytics.pilot_day_trading_policy import effective_quote_refresh_seconds as _secs

    return _secs(root)


def effective_full_refresh_ms(root: Path) -> int:
    from analytics.pilot_day_trading_policy import effective_full_refresh_ms as _ms

    return _ms(root)


def quote_fetch_timeout_s(root: Path) -> float:
    from analytics.pilot_day_trading_policy import refresh_timing

    ref = refresh_timing(root)
    if us_session_open():
        return float(ref.get("quote_fetch_timeout_open_s") or 45)
    return float(ref.get("quote_fetch_timeout_closed_s") or 25)


@dataclass
class PilotTradingSnapshot:
    generated_at_utc: str
    session: Dict[str, Any] = field(default_factory=dict)
    reevaluation: Dict[str, Any] = field(default_factory=dict)
    deferred_summary: Dict[str, Any] = field(default_factory=dict)
    playbook: Dict[str, Any] = field(default_factory=dict)
    deferred_process: Dict[str, Any] = field(default_factory=dict)
    readiness: Dict[str, Any] = field(default_factory=dict)
    enqueue_result: Optional[Dict[str, Any]] = None
    live_trading_ops: Dict[str, Any] = field(default_factory=dict)
    health: Dict[str, Any] = field(default_factory=dict)
    broker: Dict[str, Any] = field(default_factory=dict)
    plan_ref: str = ""
    plan_pipeline_run_id: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "generated_at_utc": self.generated_at_utc,
            "session": self.session,
            "reevaluation": self.reevaluation,
            "deferred_summary": self.deferred_summary,
            "playbook": self.playbook,
            "deferred_process": self.deferred_process,
            "readiness": self.readiness,
            "enqueue_result": self.enqueue_result,
            "live_trading_ops": self.live_trading_ops,
            "health": self.health,
            "broker": self.broker,
            "plan_ref": self.plan_ref,
            "plan_pipeline_run_id": self.plan_pipeline_run_id,
        }


def refresh_trading_snapshot(
    root: Path,
    *,
    broker: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    quote_snapshot: Optional[Dict[str, Any]] = None,
    champion_guard: Optional[Dict[str, Any]] = None,
    force_reevaluation: bool = False,
    auto_enqueue: bool = False,
    run_deferred_processor: bool = True,
    limit_price_eur: Optional[float] = None,
    fail_closed: bool = False,
) -> PilotTradingSnapshot:
    """
    Single orchestrated pass: deferred processor → reeval → playbook (no duplicate reeval).
    fail_closed=True: raises DayTradingSnapshotError when health.ok is False (Pipeline).
    """
    root = Path(root)
    from analytics.pilot_day_trading_reliability import (
        build_snapshot_health,
        resolve_broker_for_day_trading,
        resolve_plan_for_day_trading,
    )

    step_errors: List[str] = []
    broker, broker_warnings = resolve_broker_for_day_trading(root, broker)
    plan, plan_warnings = resolve_plan_for_day_trading(root, plan)

    from integrations.trading212.t212_exchange_session import us_equity_regular_session_open_now

    session = dict(us_equity_regular_session_open_now())
    from analytics.pilot_portfolio_reevaluation import _check_quotes_for_session, load_policy as _reeval_pol

    _reeval_cfg = _reeval_pol(root)
    need_quotes = quote_snapshot is None
    if not need_quotes and session.get("open"):
        q_ok, _, _ = _check_quotes_for_session(quote_snapshot, _reeval_cfg)
        need_quotes = not q_ok
    if need_quotes or (session.get("open") and force_reevaluation):
        try:
            from analytics.pilot_live_trade_gate import fetch_live_quotes_fail_closed

            quote_snapshot, q_blocks = fetch_live_quotes_fail_closed(root, force=True)
            if q_blocks:
                step_errors.append(f"quotes:{str(q_blocks)[:80]}")
        except Exception as exc:
            step_errors.append(f"quotes:{str(exc)[:80]}")
            if session.get("open") and force_reevaluation:
                quote_snapshot = quote_snapshot or {}

    deferred_process: Dict[str, Any] = {}
    if run_deferred_processor:
        try:
            from execution.confirmed_live.us_equity_deferred_intents import process_deferred_intents_if_due

            deferred_process = process_deferred_intents_if_due(root)
        except Exception as exc:
            deferred_process = {"error": str(exc)[:200]}
            step_errors.append(f"deferred:{str(exc)[:80]}")

    from analytics.pilot_portfolio_reevaluation import run_periodic_reevaluation

    reevaluation = run_periodic_reevaluation(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
        force=force_reevaluation,
    )

    live_trading_ops: Dict[str, Any] = {}
    try:
        from analytics.live_trading_operations import load_policy as load_lt_pol
        from analytics.live_trading_operations import run_daily_live_cycle

        lt = load_lt_pol(root)
        if lt.get("enabled", True):
            from execution.confirmed_live.us_equity_deferred_intents import load_policy as load_def_pol

            def_pol = load_def_pol(root)
            armed = bool(
                def_pol.get("user_armed_auto_open_execution")
                and def_pol.get("auto_execute_at_us_open")
            )
            live_trading_ops = run_daily_live_cycle(
                root,
                champion_guard=champion_guard,
                armed_auto=armed or auto_enqueue,
                force_rebalance=False,
            )
    except Exception as exc:
        live_trading_ops = {"error": str(exc)[:200]}
        step_errors.append(f"live_ops:{str(exc)[:80]}")

    from execution.confirmed_live.us_equity_deferred_intents import load_deferred_summary

    deferred_summary = load_deferred_summary(root)

    readiness: Dict[str, Any] = {}
    if broker:
        try:
            from integrations.trading212.t212_order_readiness import assess_order_readiness

            readiness = assess_order_readiness(root, free_cash_eur=broker.get("cash_eur")).as_dict()
        except Exception as exc:
            readiness = {"ok": False, "status_de": str(exc)[:120]}
            step_errors.append(f"readiness:{str(exc)[:80]}")

    from execution.confirmed_live.us_day_trading_coordinator import (
        build_day_trading_playbook,
        maybe_enqueue_from_playbook,
    )

    playbook = build_day_trading_playbook(
        root,
        broker=broker,
        plan=plan,
        quote_snapshot=quote_snapshot,
        champion_guard=champion_guard,
        reevaluation=reevaluation,
    )

    enqueue_result = None
    if auto_enqueue and plan and limit_price_eur is not None:
        enqueue_result = maybe_enqueue_from_playbook(
            root,
            playbook,
            plan=plan,
            limit_price_eur=limit_price_eur,
            quote_snapshot=quote_snapshot,
        )

    health = build_snapshot_health(
        broker=broker,
        plan=plan,
        reevaluation=reevaluation,
        playbook=playbook,
        broker_warnings=broker_warnings,
        plan_warnings=plan_warnings,
        step_errors=step_errors,
        root=root,
    )

    snap = PilotTradingSnapshot(
        generated_at_utc=_utc_now(),
        session=session,
        reevaluation=reevaluation,
        deferred_summary=deferred_summary,
        playbook=playbook,
        deferred_process=deferred_process,
        readiness=readiness,
        enqueue_result=enqueue_result,
        live_trading_ops=live_trading_ops,
        health=health,
        broker=broker,
        plan_ref=str(_PLAN_EVIDENCE),
        plan_pipeline_run_id=plan.get("pipeline_run_id"),
    )
    atomic_write_json(root / _EVIDENCE_REL, snap.as_dict())

    if fail_closed and not health.get("ok"):
        raise DayTradingSnapshotError("; ".join(health.get("errors_de") or ["day_trading_unhealthy"]))

    return snap


def capture_portfolio_change_if_needed(
    root: Path,
    plan: Dict[str, Any],
    *,
    limit_price_eur: float,
) -> Dict[str, Any]:
    from execution.confirmed_live.us_equity_deferred_intents import capture_portfolio_change_intent

    return capture_portfolio_change_intent(root, plan, limit_price_eur=limit_price_eur)


def set_auto_open_armed(root: Path, *, armed: bool) -> Dict[str, Any]:
    from execution.confirmed_live.us_equity_deferred_intents import set_user_armed_auto_open

    return set_user_armed_auto_open(root, armed=armed)


def is_enabled(root: Path) -> bool:
    return bool(load_unified_policy(root).get("enabled", True))
