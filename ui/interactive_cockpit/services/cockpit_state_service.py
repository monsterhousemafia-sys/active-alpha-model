"""Bridge to existing P16F/P16G backend state for interactive GUI."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from aa_decision_cockpit_p16f_desktop import load_p16f_desktop_state
from aa_runtime_guards import record_subsystem_error, truncate_error
from integrations.trading212.t212_connection_status_model import BrokerConnectionStatus
from integrations.trading212.t212_readonly_connection_service import connection_status_summary, load_cached_broker_status, sync_readonly_account
from integrations.trading212.t212_session_credential_store import get_session_state, session_configured
from paper.p16f.desktop_engine import run_p16f_desktop_product
from ui.interactive_cockpit.services.activity_audit_service import load_recent_activities, planned_next_actions
from ui.interactive_cockpit.services.scenario_planning_service import load_scenarios

logger = logging.getLogger(__name__)


def _attach_sector_reference_state(
    root: Path,
    state: Dict[str, Any],
    *,
    full_remediation: bool,
) -> None:
    """Read-only sector status for cockpit; refresh only on full remediation (S5)."""
    sector_refresh: Dict[str, Any] = {}
    if full_remediation:
        try:
            from aa_config_env import load_aa_env
            from aa_sector_reference import ensure_sector_reference_fresh

            sector_refresh = ensure_sector_reference_fresh(root, load_aa_env(root))
        except Exception as exc:
            sector_refresh = {"refreshed": False, "error": str(exc)[:200]}
            logger.warning("sector reference refresh degraded", exc_info=True)
    try:
        from aa_sector_reference import format_sector_dashboard_status

        sector_status = format_sector_dashboard_status(root)
    except Exception as exc:
        sector_status = {
            "traffic": "ROT",
            "summary_de": f"Sektoren: Status nicht lesbar — {exc}",
            "status_file": {"status": "ERROR"},
        }
    state["sector_refresh"] = sector_refresh
    state["sector_status"] = sector_status


def refresh_cockpit_state(root: Path, *, full_remediation: bool = False, force_market_prices: bool = False) -> Dict[str, Any]:
    root = Path(root)
    from aa_marktanalyse_runtime_bootstrap import ensure_marktanalyse_runtime_layout
    from market.live_quote_engine import build_pilot_gap_plan, ensure_live_quotes_fresh, merge_snapshot_into_state

    ensure_marktanalyse_runtime_layout(root)
    quote_snapshot: Dict[str, Any] = {}
    try:
        quote_snapshot = ensure_live_quotes_fresh(root, force=full_remediation or force_market_prices)
    except Exception as exc:
        quote_snapshot = {"freshness": {"status": "ERROR", "calculation_allowed": False, "reason": str(exc)[:200]}}
    try:
        if full_remediation or not (root / "paper/p16f/p16f_desktop_runtime_summary.json").is_file():
            desktop = run_p16f_desktop_product(root)
        else:
            desktop = load_p16f_desktop_state(root)
            if not desktop:
                desktop = run_p16f_desktop_product(root)

        broker: BrokerConnectionStatus = connection_status_summary(root, force_sync=full_remediation)
    except Exception as exc:
        desktop = load_p16f_desktop_state(root) or {}
        broker = load_cached_broker_status(root) or BrokerConnectionStatus()
        broker.last_error = str(exc)[:200]
        if broker.status == "NOT_CONFIGURED_SETUP_AVAILABLE_IN_GUI":
            broker.status = "DESKTOP_REFRESH_DEGRADED"
    remediation = desktop.get("remediation") or desktop
    cash = remediation.get("real_cash_state") or {}
    trigger = desktop.get("trigger") or {}
    trigger_error: str | None = None
    try:
        from intraday.trigger.managed_scope_trigger_adapter import update_managed_scope_trigger

        trigger = update_managed_scope_trigger(root, broker_connected=bool(broker.credentials_configured))
    except Exception as exc:
        trigger_error = truncate_error(exc)
        logger.warning("trigger update degraded", exc_info=True)

    from execution.confirmed_live.confirmed_execution_mode_controller import load_mode, mode_status
    from execution.confirmed_live.global_kill_switch import load_state as kill_state
    from execution.confirmed_live.managed_scope_service import load_baseline, load_managed_scope
    from execution.confirmed_live.order_draft_service import load_queue_summary

    if broker.credentials_configured and broker.cash_eur is not None:
        cash = {**cash, "readonly_observed_real_broker_available_cash_eur": broker.cash_eur, "readonly_broker_cash_verified": True}

    state = {
        "p18": {
            "phase": "P18_WINDOWS_UX_ACCESSIBILITY",
            "failure_state_panel": True,
            "keyboard_shortcuts": True,
        },
        "p17": {
            "phase": "P17_WINDOWS_RELEASE_FOUNDATION",
            "review_mode_no_live_submission": True,
            "operational_status": "INTERNAL_REVIEW_BUILD_NO_LIVE_SUBMISSION",
            "real_capital_deployed_eur": 0.0,
        },
        "p16h": {
            "core_live_mode": mode_status(root),
            "kill_switch": kill_state(root),
            "baseline": load_baseline(root),
            "managed_scope": load_managed_scope(root),
            "order_queue": load_queue_summary(root),
        },
        "desktop": desktop,
        "remediation": remediation,
        "cash": cash,
        "trigger": trigger,
        "paper": desktop.get("paper_portfolio") or {},
        "tickets": remediation.get("manual_tickets") or {},
        "gui": desktop.get("gui_indicators") or {},
        "safety": desktop.get("safety") or {},
        "broker": broker.to_dict(),
        "session_configured": session_configured(),
        "session": get_session_state().__dict__ if get_session_state() else {},
        "scenarios": load_scenarios(root),
        "activities": load_recent_activities(root, 30),
        "active_champion": "R3_w075_q065_noexit",
        "strategy_class": "DAILY_OR_MULTI_DAY_MOMENTUM",
    }
    if trigger_error:
        record_subsystem_error(
            state,
            code="TRIGGER_UPDATE_DEGRADED",
            message=trigger_error,
            subsystem="intraday_trigger",
        )
    from ui.interactive_cockpit.services.real_money_authority import apply_real_money_state

    apply_real_money_state(state)
    state["planned_actions"] = planned_next_actions(root, state)
    state["refresh_error"] = broker.last_error if broker.status == "DESKTOP_REFRESH_DEGRADED" else None
    if quote_snapshot:
        merge_snapshot_into_state(state, quote_snapshot)
        exec_prices = quote_snapshot.get("executable_prices_eur") or {}
        positions = broker.positions if broker.credentials_configured else []
        state["pilot_gap_plan"] = build_pilot_gap_plan(
            prices_eur=exec_prices, broker_positions=positions, root=root
        )

    try:
        from market.learning_pipeline import run_learning_capture_cycle

        force_eod = full_remediation or force_market_prices
        state["learning"] = run_learning_capture_cycle(
            root,
            live_snapshot=quote_snapshot if quote_snapshot else None,
            broker=broker.to_dict(),
            cash=cash,
            force_eod=force_eod,
        )
        state["learning_readiness"] = state["learning"].get("readiness") or {}
    except Exception as exc:
        logger.error("learning capture cycle failed", exc_info=True)
        state["learning_readiness"] = {"learning_collection_active": False, "error": truncate_error(exc)}
        record_subsystem_error(state, code="LEARNING_CAPTURE_FAILED", message=truncate_error(exc), subsystem="learning")

    if state.get("subsystem_errors"):
        existing = state.get("refresh_error")
        codes = ", ".join(e.get("code", "?") for e in state["subsystem_errors"][:3])
        state["refresh_error"] = f"{existing}; {codes}" if existing else codes
    _attach_sector_reference_state(root, state, full_remediation=full_remediation)
    return state


def load_draft_tickets(root: Path) -> List[Dict[str, Any]]:
    draft_dir = root / "live_pilot/manual_execution/draft_tickets"
    out = []
    if draft_dir.is_dir():
        for p in sorted(draft_dir.glob("*.json")):
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return out


def load_superseded_tickets(root: Path) -> List[Dict[str, Any]]:
    d = root / "live_pilot/manual_execution/superseded_invalid_tickets/p16e"
    out = []
    if d.is_dir():
        for p in sorted(d.glob("*.json")):
            if p.name == "supersession_manifest.json":
                continue
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return out
