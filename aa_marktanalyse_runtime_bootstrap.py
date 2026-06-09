"""Ensure writable runtime layout for Marktanalyse.exe (dev + frozen)."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Iterable

_RUNTIME_DIRS = (
    "paper/p16f",
    "paper/p16d",
    "paper/config",
    "live_pilot/manual_execution/readonly_real_account_state",
    "live_pilot/manual_execution/readonly_credentials",
    "live_pilot/manual_execution/readonly_real_positions",
    "live_pilot/manual_execution/draft_tickets",
    "live_pilot/activity",
    "live_pilot/confirmed_execution",
    "execution/confirmed_live",
    "control",
    "evidence",
)

_SEED_REL_PATHS = (
    "paper/p16f/p16f_desktop_runtime_summary.json",
    "paper/p16d/runtime_checkpoint.json",
    "paper/config/p16c_cost_adjusted_initial_allocation_500eur.json",
    "paper/config/p16d_provisional_executable_portfolio_6_position.json",
    "paper/config/p16d_reference_portfolio_8_position.json",
    "paper/config/p16d_portfolio_identity_policy.json",
    "paper/config/p16d_allowed_actions_by_instrument.json",
)


def _meipass_seed_dir() -> Path | None:
    base = getattr(sys, "_MEIPASS", None)
    if not base:
        return None
    seed = Path(base) / "frozen_runtime_seed"
    return seed if seed.is_dir() else None


def _copy_seed_file(root: Path, rel: str) -> None:
    dst = root / rel
    if dst.is_file():
        return
    seed = _meipass_seed_dir()
    if seed:
        src = seed / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if rel.endswith("p16f_desktop_runtime_summary.json"):
        dst.write_text(
            json.dumps(_minimal_desktop_summary(), indent=2) + "\n",
            encoding="utf-8",
        )


def _minimal_desktop_summary() -> dict:
    return {
        "p16f_desktop_status": "PASS_PROFESSIONAL_DESKTOP_PRODUCT_BUILT_TRIGGER_IMPLEMENTED_AWAITING_READONLY_REAL_INPUT",
        "paper_portfolio": {"virtual_paper_cash_eur": 153.7288, "virtual_paper_net_pnl_eur": 0.0},
        "trigger": {
            "trigger_status": "INACTIVE_NO_READONLY_REAL_ACCOUNT_CONNECTION",
            "trigger_threshold_eur": 50.0,
            "current_eligible_realized_net_profit_eur": 0.0,
            "distance_to_trigger_eur": 50.0,
            "id0_intraday_paper_branch_unlocked": False,
        },
        "remediation": {
            "real_cash_state": {
                "user_authorized_real_pilot_capital_eur": 500.0,
                "real_cash_reserve_required_eur": 50.0,
                "available_real_manual_ticket_budget_eur": 0.0,
                "readonly_broker_cash_verified": False,
            },
            "manual_tickets": {"draft_tickets": 0, "ready_for_user_manual_review": 0},
            "trading212": {
                "credentials_configured": False,
                "live_read_only_account_observation_status": "AWAITING_SECURE_LOCAL_CREDENTIAL_CONFIGURATION",
            },
            "forward_batch": {"executable_prices_eur": {}, "data_quality_gate": "AWAITING_REFRESH"},
        },
        "gui_indicators": {
            "p16e_invalid_tickets_superseded": 0,
            "p16e_tickets_execution_allowed": False,
            "intraday_area_visible": True,
            "intraday_area_locked_until_trigger": True,
        },
        "safety": {
            "active_champion": "R3_w075_q065_noexit",
            "max_real_capital_eur": 500.0,
            "minimum_cash_reserve_eur": 50.0,
        },
    }


def ensure_marktanalyse_runtime_layout(root: Path) -> Path:
    """Create runtime dirs and seed minimal JSON if missing."""
    root = Path(root)
    for rel in _RUNTIME_DIRS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    for rel in _SEED_REL_PATHS:
        _copy_seed_file(root, rel)
    marker = root / "control" / "marktanalyse_runtime_layout.json"
    if not marker.is_file():
        marker.write_text(
            json.dumps(
                {
                    "layout_version": 1,
                    "writable_root": str(root),
                    "frozen": bool(getattr(sys, "frozen", False)),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return root


def iter_seed_source_paths(repo_root: Path) -> Iterable[Path]:
    for rel in _SEED_REL_PATHS:
        p = repo_root / rel
        if p.is_file():
            yield p
