"""Reference vs provisional executable portfolio identity."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

REFERENCE_SYMBOLS = ["OXY", "VUSD", "WDC", "SNDK", "STX", "INTC", "MU", "CIEN"]
EXECUTABLE_SYMBOLS = ["OXY", "WDC", "STX", "INTC", "MU", "CIEN"]
OBSERVATION_ONLY = ["VUSD"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_portfolio_identity_configs(root: Path) -> Dict[str, Any]:
    root = Path(root)
    cfg = root / "paper/config"
    cfg.mkdir(parents=True, exist_ok=True)

    ref = {
        "portfolio_id": "REFERENCE_PORTFOLIO_8_POSITION_500_EUR",
        "initial_capital_eur": 500.0,
        "base_currency": "EUR",
        "position_count": 8,
        "symbols": REFERENCE_SYMBOLS,
        "fully_executed": False,
        "purpose": "target_and_comparison_allocation",
    }
    exe = {
        "portfolio_id": "PROVISIONAL_EXECUTABLE_PORTFOLIO_6_POSITION_500_EUR",
        "initial_capital_eur": 500.0,
        "base_currency": "EUR",
        "position_count": 6,
        "symbols": EXECUTABLE_SYMBOLS,
        "classification": "LIMITED_EXECUTABLE_SUBSET_PERFORMANCE",
        "excluded_from_execution": OBSERVATION_ONLY,
        "p16c_ledger_preserved": True,
        "no_retroactive_inclusion": True,
    }
    policy = {
        "portfolio_identity_policy_version": "P16D",
        "reference_portfolio_id": ref["portfolio_id"],
        "executable_portfolio_id": exe["portfolio_id"],
        "option_a_new_8_position_portfolio": {
            "trigger": "VUSD_and_SNDK_fully_validated",
            "new_portfolio_id": "REFERENCE_PORTFOLIO_8_POSITION_500_EUR_V2",
            "requires_new_forward_start": True,
        },
        "option_b_continue_6_position": {
            "trigger": "identity_or_currency_not_fully_validated",
            "performance_classification": "LIMITED_EXECUTABLE_SUBSET_PERFORMANCE",
        },
        "reserved_cash_policy": "transparent_uninvested_cash_after_cost_adjusted_allocation",
        "tracking_error_method": "absolute_eur_deviation_vs_reference_targets",
        "no_retroactive_portfolio_identity_change": True,
    }
    reserved = {
        "reserved_cash_eur_documented": True,
        "new_instrument_policy": "separate_portfolio_or_explicit_addition_event",
        "tracking_error_vs_reference_eur": None,
    }

    (cfg / "p16d_portfolio_identity_policy.json").write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
    (cfg / "p16d_reference_portfolio_8_position.json").write_text(json.dumps(ref, indent=2) + "\n", encoding="utf-8")
    (cfg / "p16d_provisional_executable_portfolio_6_position.json").write_text(json.dumps(exe, indent=2) + "\n", encoding="utf-8")
    (cfg / "p16d_reserved_cash_and_new_portfolio_policy.json").write_text(json.dumps(reserved, indent=2) + "\n", encoding="utf-8")

    return {
        "reference": ref,
        "executable": exe,
        "policy": policy,
        "reference_positions": 8,
        "executable_positions": 6,
        "observation_only": OBSERVATION_ONLY,
        "full_reference_claimed_as_executed": False,
        "generated_at_utc": _utc_now(),
    }
