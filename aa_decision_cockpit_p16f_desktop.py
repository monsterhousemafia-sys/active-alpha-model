"""P16F desktop product tab content for Decision Cockpit GUI."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def load_p16f_desktop_state(root: Path) -> Dict[str, Any]:
    root = Path(root)
    for rel in (
        "paper/p16f/p16f_desktop_runtime_summary.json",
        "paper/p16f/p16f_runtime_summary.json",
    ):
        p = root / rel
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def build_p16f_desktop_tabs(root: Path) -> Dict[str, str]:
    state = load_p16f_desktop_state(root)
    remediation = state.get("remediation") or state
    safety = state.get("safety") or remediation.get("safety_semantics") or {}
    cash = remediation.get("real_cash_state") or state.get("real_cash_state") or {}
    tickets = remediation.get("manual_tickets") or state.get("manual_tickets") or {}
    trigger = state.get("trigger") or {}
    t212 = state.get("trading212_health") or remediation.get("trading212") or {}
    paper = state.get("paper_portfolio") or {}
    gui = state.get("gui_indicators") or {}

    dashboard = [
        "Marktanalyse — P16F Desktop Product",
        f"Status: {state.get('p16f_desktop_status') or remediation.get('p16f_implementation_status', 'UNKNOWN')}",
        f"Active Champion: {safety.get('active_champion', 'R3_w075_q065_noexit')}",
        "",
        "Safety Banner:",
        "  NO AUTO PROMOTION | NO BROKER ORDERS BY CURSOR | READ-ONLY BROKER OBSERVATION",
        "",
        f"P16E Invalid Tickets Superseded: {gui.get('p16e_invalid_tickets_superseded', 0)}",
        f"P16E Execution Allowed: {gui.get('p16e_tickets_execution_allowed', False)}",
        f"Daytrading Trigger: {trigger.get('trigger_status', 'INACTIVE')}",
        f"Intraday ID0 Unlocked: {trigger.get('id0_intraday_paper_branch_unlocked', False)}",
    ]

    portfolio = [
        "=== Reference Portfolio ===",
        "8-position reference (not all executed in real pilot)",
        "",
        "=== Provisional Paper Portfolio ===",
        f"Virtual Paper Cash EUR: {paper.get('virtual_paper_cash_eur', cash.get('virtual_paper_portfolio_cash_eur', 'n/a'))}",
        f"Virtual Paper Net P/L EUR: {paper.get('virtual_paper_net_pnl_eur', 'n/a')}",
        "",
        "=== Manual Real Pilot ===",
        f"Authorized Max EUR: {safety.get('max_real_capital_eur', 500)}",
        f"Cash Reserve Required EUR: {safety.get('minimum_cash_reserve_eur', 50)}",
        f"Read-Only Broker Cash EUR: {cash.get('readonly_observed_real_broker_available_cash_eur', 'NOT_AVAILABLE')}",
        f"Available Ticket Budget EUR: {cash.get('available_real_manual_ticket_budget_eur', 0)}",
        f"Reconciled Invested EUR: {cash.get('readonly_reconciled_real_invested_eur', 0)}",
    ]

    manual_tickets = [
        "Manual Tickets — NO AUTOMATIC ORDER EXECUTION",
        "User must verify and enter orders manually in broker app.",
        "",
        f"Superseded Invalid (P16E): {gui.get('p16e_invalid_tickets_superseded', 0)}",
        f"Draft Tickets: {tickets.get('draft_tickets', 0)}",
        f"Ready for User Review: {tickets.get('ready_for_user_manual_review', 0)}",
        f"Expired: {tickets.get('expired_tickets', 0)}",
        "",
        "All P16E ready tickets superseded — DO NOT EXECUTE.",
    ]

    profit_trigger = [
        "Profit Trigger & Intraday Unlock",
        f"Trigger Threshold EUR: {trigger.get('trigger_threshold_eur', 50.0)}",
        f"Metric: {trigger.get('trigger_metric', 'READONLY_RECONCILED_REALIZED_NET_TRADING_PROFIT_EUR')}",
        f"Current Eligible Profit EUR: {trigger.get('current_eligible_realized_net_profit_eur', 0)}",
        f"Distance To Trigger EUR: {trigger.get('distance_to_trigger_eur', 50.0)}",
        f"Status: {trigger.get('trigger_status', 'INACTIVE')}",
        "",
        "Excluded from trigger:",
        "  Paper P/L, unrealized P/L, deposits, withdrawals, transfers, dividends",
    ]

    id0 = trigger.get("id0_branch") or {}
    intraday = [
        "Intraday Paper/Research Center",
        f"Strategy Class: SEPARATE_RESEARCH_CANDIDATE_NOT_CHAMPION",
        f"Status: {id0.get('status', 'LOCKED_PENDING_50_EUR_READONLY_RECONCILED_REALIZED_NET_TRADING_PROFIT')}",
        f"Paper Capital EUR: {id0.get('paper_initial_capital_eur', 500)}",
        f"Real Money: NO",
        f"Automated Order Routing: DISABLED",
        "",
        "Roadmap: ID0 (active/unlocked) → ID1 → ID2 → ID3 → ID4",
        "Champion R3_w075_q065_noexit unchanged — daily/multi-day only.",
    ]

    market_fx = [
        "Market Data & FX Monitor",
        "Provider: READONLY_YFINANCE (forward observation)",
        f"Forward batch status: {(remediation.get('forward_batch') or {}).get('data_quality_gate', 'n/a')}",
        f"FX gate: {(remediation.get('forward_batch') or {}).get('fx_runtime_gate', 'n/a')}",
    ]

    t212_tab = [
        "Trading 212 Read-Only Connection",
        f"Demo Status: {t212.get('demo_read_only_status', 'n/a')}",
        f"Live Status: {t212.get('live_read_only_status') or t212.get('live_read_only_account_observation_status', 'n/a')}",
        f"Credentials Configured: {'YES' if t212.get('credentials_configured') else 'NO'}",
        f"Write Methods Blocked: {'YES' if t212.get('write_methods_blocked') else 'NO'}",
        f"Order Endpoints Blocked: {'YES' if t212.get('order_endpoints_blocked') else 'NO'}",
        f"Secret Safety: {t212.get('secret_safety', 'PASS')}",
    ]

    audit = [
        "Audit, Logs & Safety",
        f"Real Capital Deployed By Cursor EUR: {safety.get('real_capital_deployed_by_cursor_eur', 0)}",
        f"Broker Order Submitted: {safety.get('broker_order_submitted_by_cursor', False)}",
        f"P16E Tickets Execution Allowed: {gui.get('p16e_tickets_execution_allowed', False)}",
        f"Trigger Events Logged: intraday/trigger/trigger_evidence_ledger.jsonl",
    ]

    return {
        "P16F Dashboard": "\n".join(dashboard),
        "Portfolio Center": "\n".join(portfolio),
        "Manual Tickets": "\n".join(manual_tickets),
        "Profit Trigger": "\n".join(profit_trigger),
        "Intraday Research": "\n".join(intraday),
        "Market & FX": "\n".join(market_fx),
        "Trading 212": "\n".join(t212_tab),
        "P16F Audit": "\n".join(audit),
    }
