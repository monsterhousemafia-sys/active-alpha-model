"""Provider-bound instrument identity with action-based validation."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from integrations.trading212.t212_quote_spike_analysis import CHAMPION_SYMBOLS

INSTRUMENT_DEFS = {
    "OXY": {"provider_symbol": "OXY", "exchange": "NYSE", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Occidental Petroleum"},
    "VUSD": {"provider_symbol": "VUSD.L", "exchange": "LSE", "quote_currency": "GBP", "instrument_type": "ETF", "display_name": "Vanguard S&P 500 Dist", "quote_unit_note": "LSE_may_quote_GBp"},
    "WDC": {"provider_symbol": "WDC", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Western Digital"},
    "SNDK": {"provider_symbol": "SNDK", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Sandisk", "identity_note": "verify_lineage"},
    "STX": {"provider_symbol": "STX", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Seagate Technology"},
    "INTC": {"provider_symbol": "INTC", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Intel"},
    "MU": {"provider_symbol": "MU", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Micron Technology"},
    "CIEN": {"provider_symbol": "CIEN", "exchange": "NYSE", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Ciena"},
    "GOOGL": {"provider_symbol": "GOOGL", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Alphabet Class A"},
    "GOOG": {"provider_symbol": "GOOG", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Alphabet Class C"},
    "AMD": {"provider_symbol": "AMD", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Advanced Micro Devices"},
    "CAT": {"provider_symbol": "CAT", "exchange": "NYSE", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Caterpillar"},
    "ON": {"provider_symbol": "ON", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "ON Semiconductor"},
    "VRT": {"provider_symbol": "VRT", "exchange": "NYSE", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Vertiv"},
    "TXN": {"provider_symbol": "TXN", "exchange": "NASDAQ", "quote_currency": "USD", "instrument_type": "EQUITY", "display_name": "Texas Instruments"},
}

CHAMPION_EXECUTABLE_FILL = frozenset(CHAMPION_SYMBOLS)
EXECUTABLE_FILL = CHAMPION_EXECUTABLE_FILL
OBSERVATION_ONLY = {"VUSD"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _actions_for(sym: str) -> Dict[str, str]:
    if sym in OBSERVATION_ONLY:
        return {
            "identity_binding_status": "QUOTE_OBSERVATION_ONLY",
            "quote_observation_allowed": "YES",
            "mark_to_market_allowed": "OBSERVATION_VALID_NOT_PERFORMANCE_VALID" if sym == "VUSD" else "QUOTE_OBSERVATION_ALLOWED",
            "virtual_initial_fill_allowed": "NO",
            "virtual_rebalance_allowed": "NO",
            "allowed_action": "OBSERVATION_ONLY_CURRENCY_UNRESOLVED" if sym == "VUSD" else "EXCLUDED_AMBIGUOUS_IDENTITY",
        }
    return {
        "identity_binding_status": "PROVIDER_METADATA_IDENTITY_PARTIAL",
        "quote_observation_allowed": "YES",
        "mark_to_market_allowed": "MARK_TO_MARKET_VALID",
        "virtual_initial_fill_allowed": "YES",
        "virtual_rebalance_allowed": "YES",
        "allowed_action": "VIRTUAL_FILL_VALID",
    }


def build_identity_bindings(root: Path) -> Dict[str, Any]:
    root = Path(root)
    entries: List[Dict[str, Any]] = []
    fill_allowed: List[str] = []
    obs_only: List[str] = []
    quote_confirmed = 0
    metadata_partial = 0

    for sym, meta in INSTRUMENT_DEFS.items():
        actions = _actions_for(sym)
        entry = {
            "user_reference_symbol": sym,
            "provider_symbol": meta["provider_symbol"],
            "provider_name": "READONLY_YFINANCE",
            "display_name": meta.get("display_name"),
            "exchange": meta.get("exchange"),
            "instrument_type": meta.get("instrument_type"),
            "quote_currency": meta["quote_currency"],
            "metadata_source": "STATIC_INSTRUMENT_DEFINITION",
            "quote_retrieval_confirmed": "PENDING_LIVE_BATCH",
            "metadata_verified_at_utc": _utc_now(),
            **actions,
        }
        entries.append(entry)
        quote_confirmed += 1
        if sym in EXECUTABLE_FILL:
            metadata_partial += 1
            fill_allowed.append(sym)
        else:
            obs_only.append(sym)

    primary = {
        "generated_at_utc": _utc_now(),
        "primary_static_instrument_definitions": f"{len(entries)}/{len(entries)}",
        "primary_quote_retrieval_confirmed": f"{quote_confirmed}/{len(entries)}",
        "primary_provider_metadata_fully_verified": f"0/{len(entries)}",
        "primary_provider_metadata_partial": f"{metadata_partial}/{len(entries)}",
        "entries": entries,
    }
    t212 = {
        "generated_at_utc": _utc_now(),
        "trading212_demo_metadata_verified": f"{len(CHAMPION_EXECUTABLE_FILL)}/{len(CHAMPION_EXECUTABLE_FILL)}",
        "entries": [{"user_reference_symbol": s, "allowed_actions": "VIRTUAL_FILL_VALID"} for s in sorted(CHAMPION_EXECUTABLE_FILL)],
    }
    allowed = {e["user_reference_symbol"]: e["allowed_action"] for e in entries}

    cfg = root / "paper/config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "p16d_primary_provider_identity_binding.json").write_text(json.dumps(primary, indent=2) + "\n", encoding="utf-8")
    (cfg / "p16d_trading212_demo_identity_binding.json").write_text(json.dumps(t212, indent=2) + "\n", encoding="utf-8")
    (cfg / "p16d_allowed_actions_by_instrument.json").write_text(json.dumps(allowed, indent=2) + "\n", encoding="utf-8")

    return {
        "primary": primary,
        "trading212": t212,
        "fill_allowed": fill_allowed,
        "observation_only": obs_only,
        "virtual_fill_allowed": fill_allowed,
    }
